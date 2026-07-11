#!/usr/bin/env python3
"""Reconstruct exact public snapshots without importing private Git ancestry."""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath


class LineageError(RuntimeError):
    """A clean lineage could not be reconstructed safely."""


EXPECTED_BUILD_MESSAGES = (
    "Sanitized public baseline",
    "Wheel resources and workspace initialization",
    "Clean public Git lineage",
)


@dataclass(frozen=True)
class Snapshot:
    ref: str
    message: str


@dataclass(frozen=True)
class CommitProof:
    source_ref: str
    source_commit: str
    source_tree: str
    clean_commit: str
    clean_tree: str
    manifest: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "source_ref": self.source_ref,
            "source_commit": self.source_commit,
            "source_tree": self.source_tree,
            "clean_commit": self.clean_commit,
            "clean_tree": self.clean_tree,
            "entry_count": len(self.manifest),
            "manifest": list(self.manifest),
        }


@dataclass(frozen=True)
class _PreparedSnapshot:
    source_ref: str
    source_commit: str
    source_tree: str
    source_manifest: tuple[dict[str, str], ...]
    archive_data: bytes


@dataclass
class _ProofReservation:
    path: Path
    temporary: Path
    descriptor: int
    device: int
    inode: int

    def matches(self, candidate: Path) -> bool:
        try:
            current = candidate.stat(follow_symlinks=False)
        except OSError:
            return False
        return (current.st_dev, current.st_ino) == (self.device, self.inode)

    def finish(self) -> None:
        if self.descriptor >= 0:
            os.close(self.descriptor)
            self.descriptor = -1

    def abort(self) -> None:
        self.finish()
        for candidate in (self.path, self.temporary):
            if self.matches(candidate):
                try:
                    candidate.unlink()
                except FileNotFoundError:
                    pass


@dataclass(frozen=True)
class _DirectoryIdentity:
    device: int
    inode: int


def _clean_git_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            env=_clean_git_environment(),
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise LineageError("unable to run git") from exc


def _checked_git(repo: Path, *args: str) -> bytes:
    result = _run_git(repo, *args)
    if result.returncode != 0:
        operation = next((arg for arg in args if not arg.startswith("-")), "command")
        raise LineageError(f"git {operation} failed")
    return result.stdout


def _decoded_line(value: bytes) -> str:
    return value.decode("utf-8", "surrogateescape").strip()


def _git_directory_paths(repo: Path) -> tuple[Path, Path]:
    actual = _run_git(repo, "--no-replace-objects", "rev-parse", "--absolute-git-dir")
    common = _run_git(repo, "--no-replace-objects", "rev-parse", "--git-common-dir")
    if actual.returncode != 0 or common.returncode != 0:
        raise LineageError("Git directory state could not be read")

    def absolute_path(raw: bytes) -> Path:
        path = Path(_decoded_line(raw))
        return path if path.is_absolute() else Path(os.path.abspath(repo / path))

    return absolute_path(actual.stdout), absolute_path(common.stdout)


def _require_no_internal_git_symlinks(
    git_dirs: Sequence[Path],
    *,
    owner: str,
) -> None:
    for git_dir in dict.fromkeys(git_dirs):
        critical_paths = (
            git_dir / "HEAD",
            git_dir / "config",
            git_dir / "index",
            git_dir / "commondir",
            git_dir / "objects",
            git_dir / "refs",
            git_dir / "info",
            git_dir / "packed-refs",
        )
        if any(path.is_symlink() for path in critical_paths):
            raise LineageError(f"{owner} uses symlinked internal Git storage")
        for storage_root in (git_dir / "objects", git_dir / "refs", git_dir / "info"):
            if not storage_root.exists():
                continue
            for root, directories, files in os.walk(storage_root, followlinks=False):
                if any(
                    (Path(root) / name).is_symlink()
                    for name in (*directories, *files)
                ):
                    raise LineageError(
                        f"{owner} uses symlinked internal Git storage"
                    )


def _require_clean_source(source: Path) -> None:
    if not source.is_dir():
        raise LineageError("source path is not a directory")
    if (source / ".git").is_symlink():
        raise LineageError("source uses symlinked internal Git storage")
    inside = _run_git(
        source,
        "--no-replace-objects",
        "rev-parse",
        "--is-inside-work-tree",
    )
    if inside.returncode != 0 or inside.stdout.strip() != b"true":
        raise LineageError("source path is not a Git worktree")
    actual_git_dir, common_git_dir = _git_directory_paths(source)
    _require_no_internal_git_symlinks(
        (actual_git_dir, common_git_dir),
        owner="source",
    )
    replacements = _run_git(
        source,
        "for-each-ref",
        "--format=%(refname)",
        "refs/replace",
    )
    if replacements.returncode != 0:
        raise LineageError("source reference state could not be read")
    shallow = _run_git(
        source,
        "--no-replace-objects",
        "rev-parse",
        "--is-shallow-repository",
    )
    forbidden_state = (
        common_git_dir / "shallow",
        common_git_dir / "info" / "grafts",
        common_git_dir / "objects" / "info" / "alternates",
        common_git_dir / "objects" / "info" / "http-alternates",
    )
    if (
        replacements.stdout
        or shallow.returncode != 0
        or shallow.stdout.strip() != b"false"
        or any(os.path.lexists(path) for path in forbidden_state)
        or any((common_git_dir / "objects" / "pack").glob("*.promisor"))
    ):
        raise LineageError(
            "source uses external, rewritten, or incomplete object state"
        )
    config = _run_git(source, "config", "--name-only", "--list")
    if config.returncode != 0:
        raise LineageError("source configuration could not be read")
    sensitive_config = (
        "extensions.partialclone",
        ".promisor",
        ".partialclonefilter",
    )
    if any(
        any(marker in _decoded_line(line).casefold() for marker in sensitive_config)
        for line in config.stdout.splitlines()
    ):
        raise LineageError("source uses partial-clone or promisor configuration")
    status = _run_git(
        source,
        "--no-replace-objects",
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if status.returncode != 0:
        raise LineageError("source status could not be read")
    if status.stdout:
        raise LineageError("source worktree is not clean")


def _source_identity(source: Path) -> tuple[str, str]:
    values: list[str] = []
    for key in ("user.name", "user.email"):
        result = _run_git(source, "config", "--get", key)
        value = _decoded_line(result.stdout) if result.returncode == 0 else ""
        if not value:
            raise LineageError(f"source {key} is not configured")
        values.append(value)
    return values[0], values[1]


def _resolve_snapshot(source: Path, ref: str) -> tuple[str, str]:
    if not ref:
        raise LineageError("source ref is empty")
    resolved = _run_git(
        source,
        "--no-replace-objects",
        "rev-parse",
        "--verify",
        "--end-of-options",
        f"{ref}^{{commit}}",
    )
    if resolved.returncode != 0:
        raise LineageError("source ref does not resolve to a commit")
    source_commit = _decoded_line(resolved.stdout)
    source_tree = _decoded_line(
        _checked_git(
            source,
            "--no-replace-objects",
            "rev-parse",
            f"{source_commit}^{{tree}}",
        )
    )
    return source_commit, source_tree


def _tree_manifest(repo: Path, treeish: str) -> tuple[dict[str, str], ...]:
    output = _checked_git(
        repo,
        "--no-replace-objects",
        "ls-tree",
        "-r",
        "-z",
        "--full-tree",
        treeish,
    )
    entries: list[dict[str, str]] = []
    for record in output.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, object_id = metadata.split(b" ", 2)
        except ValueError as exc:
            raise LineageError("tree manifest is malformed") from exc
        entries.append(
            {
                "path": raw_path.decode("utf-8", "surrogateescape"),
                "mode": mode.decode("ascii"),
                "type": object_type.decode("ascii"),
                "object_id": object_id.decode("ascii"),
            }
        )
    return tuple(sorted(entries, key=lambda entry: entry["path"]))


def _source_protected_roots(source: Path) -> tuple[Path, ...]:
    actual_git_dir, common_git_dir = _git_directory_paths(source)
    worktrees = _checked_git(source, "worktree", "list", "--porcelain")
    roots = [actual_git_dir.resolve(), common_git_dir.resolve()]
    roots.extend(
        Path(_decoded_line(line.removeprefix(b"worktree "))).resolve()
        for line in worktrees.splitlines()
        if line.startswith(b"worktree ")
    )
    return tuple(dict.fromkeys(roots))


def _path_is_in_source_storage(source: Path, candidate: Path) -> bool:
    candidate_resolved = candidate.resolve()
    return any(
        candidate_resolved == root or root in candidate_resolved.parents
        for root in _source_protected_roots(source)
    )


def _safe_destination_path(destination: Path) -> Path:
    absolute = Path(os.path.abspath(destination))
    if absolute.is_symlink():
        raise LineageError("destination must be absent or empty")
    return absolute


def _destination_identity(destination: Path) -> _DirectoryIdentity:
    try:
        metadata = destination.stat(follow_symlinks=False)
    except OSError as exc:
        raise LineageError("destination path changed during operation") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise LineageError("destination path changed during operation")
    return _DirectoryIdentity(metadata.st_dev, metadata.st_ino)


def _require_destination_identity(
    destination: Path,
    expected: _DirectoryIdentity,
) -> None:
    if _destination_identity(destination) != expected:
        raise LineageError("destination path changed during operation")


def _initialize_destination(
    source: Path,
    destination: Path,
    identity: tuple[str, str],
) -> _DirectoryIdentity:
    if _path_is_in_source_storage(source, destination):
        raise LineageError("destination must be outside the source worktree")
    if destination.is_symlink():
        raise LineageError("destination must be absent or empty")
    created = False
    if destination.exists():
        if not destination.is_dir() or any(destination.iterdir()):
            raise LineageError("destination must be absent or empty")
    else:
        try:
            destination.mkdir(parents=True)
            created = True
        except OSError as exc:
            raise LineageError("destination could not be created") from exc
    directory_identity = _destination_identity(destination)
    try:
        _checked_git(destination, "-c", "init.templateDir=", "init", "-b", "main")
        name, email = identity
        settings = (
            ("user.name", name),
            ("user.email", email),
            ("commit.gpgSign", "false"),
            ("core.autocrlf", "false"),
            ("core.fileMode", "true"),
            ("core.symlinks", "true"),
        )
        for key, value in settings:
            _checked_git(destination, "config", "--local", key, value)
        hooks = destination / ".git" / "azoth-hooks"
        hooks.mkdir()
        _checked_git(destination, "config", "--local", "core.hooksPath", str(hooks))
        _require_destination_identity(destination, directory_identity)
        return directory_identity
    except Exception as operation_error:
        try:
            _clear_all_destination_content(destination, directory_identity)
            if created:
                destination.rmdir()
        except (LineageError, OSError) as rollback_error:
            raise LineageError("build rollback failed") from rollback_error
        raise operation_error


def _require_destination_repository(destination: Path) -> None:
    git_dir = destination / ".git"
    if (
        not destination.is_dir()
        or git_dir.is_symlink()
        or not git_dir.is_dir()
    ):
        raise LineageError("destination is not a Git repository")
    _require_no_internal_git_symlinks((git_dir,), owner="destination")
    top_level = _run_git(destination, "rev-parse", "--show-toplevel")
    if top_level.returncode != 0:
        raise LineageError("destination is not a Git repository")
    if Path(_decoded_line(top_level.stdout)).resolve() != destination.resolve():
        raise LineageError("destination is not the Git worktree root")
    actual_git_dir = _run_git(destination, "rev-parse", "--absolute-git-dir")
    common_git_dir = _run_git(destination, "rev-parse", "--git-common-dir")
    if actual_git_dir.returncode != 0 or common_git_dir.returncode != 0:
        raise LineageError("destination is not a Git repository")

    def resolved_git_path(value: bytes) -> Path:
        path = Path(_decoded_line(value))
        if not path.is_absolute():
            path = destination / path
        return path.resolve()

    expected_git_dir = git_dir.resolve()
    if (
        resolved_git_path(actual_git_dir.stdout) != expected_git_dir
        or resolved_git_path(common_git_dir.stdout) != expected_git_dir
    ):
        raise LineageError("destination is not a Git repository")
    branch = _run_git(destination, "symbolic-ref", "--short", "HEAD")
    if branch.returncode != 0 or branch.stdout.strip() != b"main":
        raise LineageError("destination HEAD must be main")

    worktree_output = _checked_git(
        destination, "worktree", "list", "--porcelain"
    )
    worktree_paths = [
        Path(_decoded_line(line.removeprefix(b"worktree "))).resolve()
        for line in worktree_output.splitlines()
        if line.startswith(b"worktree ")
    ]
    if worktree_paths != [destination.resolve()]:
        raise LineageError("destination must have exactly one worktree")

    shallow = _checked_git(
        destination, "rev-parse", "--is-shallow-repository"
    ).strip()
    if shallow != b"false" or os.path.lexists(git_dir / "shallow"):
        raise LineageError("destination must not be shallow")
    forbidden_state = (
        git_dir / "info" / "grafts",
        git_dir / "objects" / "info" / "alternates",
        git_dir / "objects" / "info" / "http-alternates",
    )
    if any(os.path.lexists(path) for path in forbidden_state):
        raise LineageError("destination uses external or rewritten object state")
    if any((git_dir / "objects" / "pack").glob("*.promisor")):
        raise LineageError("destination uses promisor object state")
    config = _run_git(
        destination, "config", "--local", "--name-only", "--list"
    )
    if config.returncode != 0:
        raise LineageError("destination configuration could not be read")
    sensitive_config = (
        "extensions.partialclone",
        ".promisor",
        ".partialclonefilter",
    )
    if any(
        any(marker in _decoded_line(line).casefold() for marker in sensitive_config)
        for line in config.stdout.splitlines()
    ):
        raise LineageError("destination uses partial-clone or promisor configuration")


def _require_clean_destination(destination: Path) -> None:
    status = _checked_git(
        destination,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if status:
        raise LineageError("destination worktree is not clean")


def _require_no_ignored_destination(destination: Path) -> None:
    status = _checked_git(
        destination,
        "status",
        "--porcelain=v1",
        "--ignored",
        "--untracked-files=all",
    )
    if any(line.startswith(b"!!") for line in status.splitlines()):
        raise LineageError("destination contains ignored material")


def _archive_parts(name: str) -> tuple[str, ...]:
    posix = PurePosixPath(name)
    windows = PureWindowsPath(name)
    if (
        not name
        or "\\" in name
        or posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or not posix.parts
        or any(part == ".." for part in posix.parts)
        or posix.parts[0].casefold() == ".git"
    ):
        raise LineageError("unsafe archive path")
    return posix.parts


def _validated_archive(
    archive_data: bytes,
) -> tuple[tarfile.TarFile, tuple[tuple[tarfile.TarInfo, tuple[str, ...]], ...]]:
    archive: tarfile.TarFile | None = None
    try:
        archive = tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:")
        members = tuple((member, _archive_parts(member.name)) for member in archive)
        member_graph: dict[tuple[str, ...], tarfile.TarInfo] = {}
        for member, parts in members:
            if member.issparse() or member.sparse is not None or any(
                key.casefold().startswith("gnu.sparse.")
                for key in member.pax_headers
            ):
                raise LineageError("source archive contains a sparse member")
            if not (member.isdir() or member.isreg() or member.issym()):
                raise LineageError(
                    "source archive contains an unsafe member type"
                )
            if parts in member_graph:
                raise LineageError("archive paths conflict")
            member_graph[parts] = member
        for parts in member_graph:
            for parent_length in range(1, len(parts)):
                parent = member_graph.get(parts[:parent_length])
                if parent is not None and not parent.isdir():
                    raise LineageError("archive paths conflict")
        for member, _parts in members:
            if not member.isreg():
                continue
            source_file = archive.extractfile(member)
            if source_file is None:
                raise LineageError("source archive member could not be read")
            bytes_read = 0
            with source_file:
                while chunk := source_file.read(1024 * 1024):
                    bytes_read += len(chunk)
            if bytes_read != member.size:
                raise LineageError("source archive member could not be read")
    except LineageError:
        if archive is not None:
            archive.close()
        raise
    except (OSError, tarfile.TarError, UnicodeError) as exc:
        if archive is not None:
            archive.close()
        raise LineageError("source archive is invalid") from exc
    return archive, members


def _preflight_snapshot(source: Path, ref: str) -> _PreparedSnapshot:
    source_commit, source_tree = _resolve_snapshot(source, ref)
    source_manifest = _tree_manifest(source, source_tree)
    archived = _run_git(
        source,
        "--no-replace-objects",
        "archive",
        "--format=tar",
        source_commit,
    )
    if archived.returncode != 0:
        raise LineageError("git archive failed")
    archive, _members = _validated_archive(archived.stdout)
    archive.close()
    return _PreparedSnapshot(
        source_ref=ref,
        source_commit=source_commit,
        source_tree=source_tree,
        source_manifest=source_manifest,
        archive_data=archived.stdout,
    )


def _clear_destination(
    destination: Path,
    expected_identity: _DirectoryIdentity,
) -> None:
    _require_destination_identity(destination, expected_identity)
    try:
        for entry in os.scandir(destination):
            if entry.name == ".git":
                continue
            path = Path(entry.path)
            if entry.is_dir(follow_symlinks=False):
                shutil.rmtree(path)
            else:
                path.unlink()
    except OSError as exc:
        raise LineageError("destination worktree could not be cleared") from exc


def _clear_all_destination_content(
    destination: Path,
    expected_identity: _DirectoryIdentity,
) -> None:
    if not destination.exists():
        return
    _require_destination_identity(destination, expected_identity)
    try:
        for entry in os.scandir(destination):
            path = Path(entry.path)
            if entry.is_dir(follow_symlinks=False):
                shutil.rmtree(path)
            else:
                path.unlink()
    except OSError as exc:
        raise LineageError("build rollback failed") from exc


def _rollback_build(
    destination: Path,
    existed_empty: bool,
    expected_identity: _DirectoryIdentity,
) -> None:
    _clear_all_destination_content(destination, expected_identity)
    if not existed_empty and destination.exists():
        try:
            destination.rmdir()
        except OSError as exc:
            raise LineageError("build rollback failed") from exc


def _prepare_parent(destination: Path, parts: tuple[str, ...]) -> Path:
    current = destination
    for part in parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise LineageError("archive path traverses a symlink")
        if current.exists():
            if not current.is_dir():
                raise LineageError("archive paths conflict")
        else:
            current.mkdir()
    return destination.joinpath(*parts)


def _extract_archive(
    archive: tarfile.TarFile,
    members: tuple[tuple[tarfile.TarInfo, tuple[str, ...]], ...],
    destination: Path,
) -> None:
    try:
        for member, parts in members:
            target = _prepare_parent(destination, parts)
            if member.isdir():
                if target.is_symlink() or (target.exists() and not target.is_dir()):
                    raise LineageError("archive paths conflict")
                target.mkdir(exist_ok=True)
                continue
            if target.exists() or target.is_symlink():
                raise LineageError("archive paths conflict")
            if member.issym():
                target.symlink_to(member.linkname)
                continue
            source_file = archive.extractfile(member)
            if source_file is None:
                raise LineageError("source archive member could not be read")
            with source_file, target.open("xb") as output:
                shutil.copyfileobj(source_file, output)
            target.chmod(member.mode & 0o777)
    except LineageError:
        raise
    except OSError as exc:
        raise LineageError("source archive could not be extracted") from exc


def _materialize_prepared_snapshot(
    destination: Path,
    prepared: _PreparedSnapshot,
    *,
    expected_identity: _DirectoryIdentity | None = None,
) -> None:
    _require_destination_repository(destination)
    active_identity = expected_identity or _destination_identity(destination)
    _require_destination_identity(destination, active_identity)
    _require_clean_destination(destination)
    archive, members = _validated_archive(prepared.archive_data)
    try:
        _clear_destination(destination, active_identity)
        _require_destination_identity(destination, active_identity)
        _extract_archive(archive, members, destination)
    finally:
        archive.close()


def materialize_snapshot(
    source: Path,
    destination: Path,
    ref: str,
) -> tuple[str, str]:
    source = source.resolve()
    destination = _safe_destination_path(destination)
    _require_clean_source(source)
    if _path_is_in_source_storage(source, destination):
        raise LineageError("destination must be outside the source worktree")
    prepared = _preflight_snapshot(source, ref)
    _materialize_prepared_snapshot(destination, prepared)
    return prepared.source_commit, prepared.source_tree


def _refs(destination: Path) -> tuple[str, ...]:
    output = _checked_git(destination, "for-each-ref", "--format=%(refname)")
    return tuple(_decoded_line(line) for line in output.splitlines() if line)


def _commits(destination: Path) -> tuple[str, ...]:
    output = _checked_git(destination, "rev-list", "--reverse", "main")
    return tuple(_decoded_line(line) for line in output.splitlines() if line)


def _verify_destination(destination: Path, expected_count: int) -> tuple[str, ...]:
    _require_destination_repository(destination)
    refs = _refs(destination)
    if refs != ("refs/heads/main",):
        raise LineageError("destination must have exactly one main branch")
    commits = _commits(destination)
    if len(commits) != expected_count:
        raise LineageError(
            f"destination must have exactly {expected_count} commits"
        )
    _require_clean_destination(destination)
    _checked_git(destination, "fsck", "--full", "--strict")
    return commits


def _require_strict_three_commit_topology(
    destination: Path,
    commits: tuple[str, ...],
) -> None:
    expected_parents = ((), (commits[0],), (commits[1],))
    actual_parents = tuple(
        tuple(
            _decoded_line(
                _checked_git(destination, "show", "-s", "--format=%P", commit)
            ).split()
        )
        for commit in commits
    )
    if actual_parents != expected_parents:
        raise LineageError("destination must have a strict linear topology")


def _commit_prepared_snapshot(
    destination: Path,
    snapshot: Snapshot,
    prepared: _PreparedSnapshot,
    *,
    amend: bool = False,
    expected_identity: _DirectoryIdentity | None = None,
) -> CommitProof:
    if not snapshot.message:
        raise LineageError("snapshot message is empty")
    _materialize_prepared_snapshot(
        destination,
        prepared,
        expected_identity=expected_identity,
    )
    if expected_identity is not None:
        _require_destination_identity(destination, expected_identity)
    _checked_git(destination, "add", "-A")
    commit_args = ["commit"]
    if amend:
        commit_args.append("--amend")
    commit_args.extend(
        [
            "--allow-empty",
            "--no-gpg-sign",
            "--cleanup=verbatim",
            "-m",
            snapshot.message,
        ]
    )
    _checked_git(destination, *commit_args)
    clean_commit = _decoded_line(_checked_git(destination, "rev-parse", "HEAD"))
    clean_tree = _decoded_line(
        _checked_git(destination, "rev-parse", "HEAD^{tree}")
    )
    clean_manifest = _tree_manifest(destination, clean_tree)
    if clean_tree != prepared.source_tree:
        raise LineageError("reconstructed tree does not match source tree")
    if clean_manifest != prepared.source_manifest:
        raise LineageError("reconstructed manifest does not match source manifest")
    expected_count = len(_commits(destination))
    _verify_destination(destination, expected_count)
    return CommitProof(
        source_ref=snapshot.ref,
        source_commit=prepared.source_commit,
        source_tree=prepared.source_tree,
        clean_commit=clean_commit,
        clean_tree=clean_tree,
        manifest=clean_manifest,
    )


def commit_snapshot(
    source: Path,
    destination: Path,
    snapshot: Snapshot,
    *,
    amend: bool = False,
) -> CommitProof:
    if amend:
        raise LineageError("amend requires candidate identity verification")
    source = source.resolve()
    destination = _safe_destination_path(destination)
    _require_clean_source(source)
    if _path_is_in_source_storage(source, destination):
        raise LineageError("destination must be outside the source worktree")
    if not snapshot.message:
        raise LineageError("snapshot message is empty")
    prepared = _preflight_snapshot(source, snapshot.ref)
    return _commit_prepared_snapshot(
        destination,
        snapshot,
        prepared,
        amend=amend,
    )


def _require_approved_build_identity(
    source: Path,
    snapshots: tuple[Snapshot, ...],
    prepared: tuple[_PreparedSnapshot, ...],
    *,
    expected_first_commit: str | None,
    expected_first_tree: str | None,
    expected_second_commit: str | None,
    expected_second_tree: str | None,
) -> None:
    expected_values = (
        expected_first_commit,
        expected_first_tree,
        expected_second_commit,
        expected_second_tree,
    )
    if not any(value is not None for value in expected_values):
        return
    if not all(value for value in expected_values):
        raise LineageError("approved build identity is incomplete")
    if len(snapshots) != 3 or len(prepared) != 3:
        raise LineageError("approved build identity requires three snapshots")
    if tuple(snapshot.message for snapshot in snapshots) != EXPECTED_BUILD_MESSAGES:
        raise LineageError("public lineage commit messages do not match")
    source_commits = tuple(item.source_commit for item in prepared)
    if len(set(source_commits)) != 3:
        raise LineageError("source snapshots must be distinct")
    approved_identity = (
        prepared[0].source_commit,
        prepared[0].source_tree,
        prepared[1].source_commit,
        prepared[1].source_tree,
    )
    if approved_identity != expected_values:
        raise LineageError("approved build identity does not match")
    for older, newer in zip(source_commits, source_commits[1:]):
        ancestry = _run_git(
            source,
            "--no-replace-objects",
            "merge-base",
            "--is-ancestor",
            older,
            newer,
        )
        if ancestry.returncode == 1:
            raise LineageError("source snapshots are not in ancestry order")
        if ancestry.returncode != 0:
            raise LineageError("source ancestry could not be verified")


def build_lineage(
    source: Path,
    destination: Path,
    snapshots: Sequence[Snapshot],
    *,
    expected_first_commit: str | None = None,
    expected_first_tree: str | None = None,
    expected_second_commit: str | None = None,
    expected_second_tree: str | None = None,
    _finalizer: Callable[[tuple[CommitProof, ...]], None] | None = None,
) -> tuple[CommitProof, ...]:
    source = source.resolve()
    destination = _safe_destination_path(destination)
    ordered_snapshots = tuple(snapshots)
    if not ordered_snapshots:
        raise LineageError("at least one snapshot is required")
    _require_clean_source(source)
    identity = _source_identity(source)
    for snapshot in ordered_snapshots:
        if not snapshot.message:
            raise LineageError("snapshot message is empty")
    prepared_snapshots = tuple(
        _preflight_snapshot(source, snapshot.ref)
        for snapshot in ordered_snapshots
    )
    _require_approved_build_identity(
        source,
        ordered_snapshots,
        prepared_snapshots,
        expected_first_commit=expected_first_commit,
        expected_first_tree=expected_first_tree,
        expected_second_commit=expected_second_commit,
        expected_second_tree=expected_second_tree,
    )
    if _path_is_in_source_storage(source, destination):
        raise LineageError("destination must be outside the source worktree")
    if destination.is_symlink():
        raise LineageError("destination must be absent or empty")
    existed_empty = destination.exists()
    if existed_empty and (
        not destination.is_dir() or any(destination.iterdir())
    ):
        raise LineageError("destination must be absent or empty")
    destination_identity: _DirectoryIdentity | None = None
    try:
        destination_identity = _initialize_destination(source, destination, identity)
        proofs = tuple(
            _commit_prepared_snapshot(
                destination,
                snapshot,
                prepared,
                expected_identity=destination_identity,
            )
            for snapshot, prepared in zip(ordered_snapshots, prepared_snapshots)
        )
        _verify_destination(destination, len(ordered_snapshots))
        if _finalizer is not None:
            _finalizer(proofs)
        return proofs
    except Exception as operation_error:
        try:
            if destination_identity is not None:
                _rollback_build(destination, existed_empty, destination_identity)
        except LineageError as rollback_error:
            raise rollback_error from operation_error
        raise


def _rollback_amend(
    destination: Path,
    original_tip: str,
    expected_identity: _DirectoryIdentity,
) -> None:
    _require_destination_identity(destination, expected_identity)
    reset = _run_git(destination, "reset", "--hard", original_tip)
    clean = _run_git(destination, "clean", "-ffdx")
    if reset.returncode != 0 or clean.returncode != 0:
        raise LineageError("amend rollback failed")
    current = _run_git(destination, "rev-parse", "HEAD")
    status = _run_git(
        destination, "status", "--porcelain=v1", "--untracked-files=all"
    )
    if (
        current.returncode != 0
        or _decoded_line(current.stdout) != original_tip
        or status.returncode != 0
        or status.stdout
    ):
        raise LineageError("amend rollback failed")
    commits = _verify_destination(destination, 3)
    _require_strict_three_commit_topology(destination, commits)


def amend_tip(
    source: Path,
    destination: Path,
    snapshot: Snapshot,
    *,
    expected_tip: str,
    expected_first_tree: str,
    expected_second_tree: str,
    expected_source_commit: str | None = None,
    expected_source_tree: str | None = None,
    _finalizer: Callable[[tuple[CommitProof, ...]], None] | None = None,
) -> CommitProof:
    source = source.resolve()
    destination = _safe_destination_path(destination)
    _require_clean_source(source)
    if _path_is_in_source_storage(source, destination):
        raise LineageError("destination must be outside the source worktree")
    destination_identity = _destination_identity(destination)
    before = _verify_destination(destination, 3)
    _require_destination_identity(destination, destination_identity)
    _require_strict_three_commit_topology(destination, before)
    _require_no_ignored_destination(destination)
    actual_identity = (
        before[2],
        _decoded_line(
            _checked_git(destination, "rev-parse", f"{before[0]}^{{tree}}")
        ),
        _decoded_line(
            _checked_git(destination, "rev-parse", f"{before[1]}^{{tree}}")
        ),
    )
    if actual_identity != (
        expected_tip,
        expected_first_tree,
        expected_second_tree,
    ):
        raise LineageError("destination candidate identity does not match")
    if snapshot.message != EXPECTED_BUILD_MESSAGES[2]:
        raise LineageError("public lineage commit messages do not match")
    prepared = _preflight_snapshot(source, snapshot.ref)
    if (expected_source_commit is None) != (expected_source_tree is None):
        raise LineageError("expected source identity is incomplete")
    if expected_source_commit is not None and (
        prepared.source_commit,
        prepared.source_tree,
    ) != (expected_source_commit, expected_source_tree):
        raise LineageError("expected source identity does not match")
    try:
        proof = _commit_prepared_snapshot(
            destination,
            snapshot,
            prepared,
            amend=True,
            expected_identity=destination_identity,
        )
        after = _verify_destination(destination, 3)
        _require_strict_three_commit_topology(destination, after)
        if after[:2] != before[:2]:
            raise LineageError("amend changed commits before the tip")
        if after[2] == before[2]:
            raise LineageError("amend did not change the tip commit")
        if _finalizer is not None:
            _finalizer((proof,))
        return proof
    except Exception as operation_error:
        try:
            _rollback_amend(destination, before[2], destination_identity)
        except LineageError as rollback_error:
            raise rollback_error from operation_error
        raise


def _parse_snapshot(value: str) -> Snapshot:
    ref, separator, message = value.partition("::")
    if not separator or not ref.strip() or not message.strip():
        raise argparse.ArgumentTypeError("snapshot must be REF::MESSAGE")
    return Snapshot(ref=ref, message=message)


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--json-output", required=True, type=Path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reconstruct exact public Git snapshots in a clean lineage."
    )
    commands = parser.add_subparsers(dest="mode", required=True)
    build = commands.add_parser("build", help="build a new clean lineage")
    _add_common_arguments(build)
    build.add_argument(
        "--snapshot",
        required=True,
        action="append",
        type=_parse_snapshot,
    )
    build.add_argument("--expected-first-commit")
    build.add_argument("--expected-first-tree")
    build.add_argument("--expected-second-commit")
    build.add_argument("--expected-second-tree")
    amend = commands.add_parser("amend", help="replace only the third commit")
    _add_common_arguments(amend)
    amend.add_argument("--snapshot", required=True, type=_parse_snapshot)
    amend.add_argument("--expected-tip", required=True)
    amend.add_argument("--expected-first-tree", required=True)
    amend.add_argument("--expected-second-tree", required=True)
    amend.add_argument("--expected-source-commit", required=True)
    amend.add_argument("--expected-source-tree", required=True)
    return parser


def _reserve_proof_output(
    source: Path,
    destination: Path,
    json_output: Path,
) -> _ProofReservation:
    if os.path.lexists(json_output):
        raise LineageError(
            "JSON proof must be absent, non-symlink, and outside the source and destination"
        )
    try:
        parent = json_output.parent.resolve(strict=True)
    except OSError as exc:
        raise LineageError("JSON proof parent is unavailable") from exc
    if not parent.is_dir():
        raise LineageError("JSON proof parent is unavailable")
    output = parent / json_output.name
    destination_resolved = destination.resolve()
    if (
        output == destination_resolved
        or destination_resolved in output.parents
        or _path_is_in_source_storage(source.resolve(), output)
    ):
        raise LineageError(
            "JSON proof must be absent, non-symlink, and outside the source and destination"
        )
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{output.name}.",
            suffix=".tmp",
            dir=parent,
        )
        temporary = Path(temporary_name)
        os.fchmod(descriptor, 0o600)
        metadata = os.fstat(descriptor)
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        raise LineageError("JSON proof could not be reserved") from exc
    return _ProofReservation(
        path=output,
        temporary=temporary,
        descriptor=descriptor,
        device=metadata.st_dev,
        inode=metadata.st_ino,
    )


def _write_reserved_proofs(
    reservation: _ProofReservation,
    proofs: Sequence[CommitProof],
) -> None:
    payload = {
        "proofs": [proof.to_dict() for proof in proofs],
    }
    try:
        if not reservation.matches(reservation.temporary):
            raise OSError("reserved proof path changed")
        encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
        os.lseek(reservation.descriptor, 0, os.SEEK_SET)
        os.ftruncate(reservation.descriptor, 0)
        view = memoryview(encoded)
        while view:
            written = os.write(reservation.descriptor, view)
            if written <= 0:
                raise OSError("short proof write")
            view = view[written:]
        os.fsync(reservation.descriptor)
        if not reservation.matches(reservation.temporary):
            raise OSError("reserved proof path changed")
        os.link(reservation.temporary, reservation.path)
        if not reservation.matches(reservation.path):
            raise OSError("published proof path changed")
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_descriptor = os.open(reservation.path.parent, directory_flags)
        try:
            os.fsync(directory_descriptor)
            reservation.temporary.unlink()
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as exc:
        raise LineageError("JSON proof could not be written") from exc


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.mode == "build" and len(args.snapshot) != 3:
        parser.error("build requires exactly three --snapshot arguments")
    if args.mode == "build" and not all(
        (
            args.expected_first_commit,
            args.expected_first_tree,
            args.expected_second_commit,
            args.expected_second_tree,
        )
    ):
        parser.error("build requires explicit approved source identity")
    reservation: _ProofReservation | None = None
    try:
        reservation = _reserve_proof_output(
            args.source,
            args.destination,
            args.json_output,
        )
        finalizer = lambda proofs: _write_reserved_proofs(reservation, proofs)
        if args.mode == "build":
            proofs = build_lineage(
                args.source,
                args.destination,
                args.snapshot,
                expected_first_commit=args.expected_first_commit,
                expected_first_tree=args.expected_first_tree,
                expected_second_commit=args.expected_second_commit,
                expected_second_tree=args.expected_second_tree,
                _finalizer=finalizer,
            )
        else:
            proofs = (
                amend_tip(
                    args.source,
                    args.destination,
                    args.snapshot,
                    expected_tip=args.expected_tip,
                    expected_first_tree=args.expected_first_tree,
                    expected_second_tree=args.expected_second_tree,
                    expected_source_commit=args.expected_source_commit,
                    expected_source_tree=args.expected_source_tree,
                    _finalizer=finalizer,
                ),
            )
        reservation.finish()
    except LineageError as exc:
        if reservation is not None:
            reservation.abort()
        print(f"Public lineage reconstruction: ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Public lineage reconstruction: PASS proofs={len(proofs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
