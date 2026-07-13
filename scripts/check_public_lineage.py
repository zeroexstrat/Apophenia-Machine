#!/usr/bin/env python3
"""Audit every reachable object in an isolated three-commit public lineage."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

try:
    from scripts.check_public_tree import (
        FALLBACK_DUMP_PATTERNS,
        PILOT_ID_PATTERNS,
        audit_paths,
    )
except ModuleNotFoundError:  # Direct execution sets scripts/ as sys.path[0].
    from check_public_tree import (
        FALLBACK_DUMP_PATTERNS,
        PILOT_ID_PATTERNS,
        audit_paths,
    )


ALLOWED_REFS = {"refs/heads/main"}
EXPECTED_HEAD = "refs/heads/main"
EXPECTED_COMMIT_COUNT = 3
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1\n"
PDF_PREAMBLE_LIMIT = 1024
PDF_SIGNATURE = b"%" + b"PDF-"
RAW_ABSOLUTE_PATTERNS = (
    re.compile(rb"/" + rb"Users/(?![\[<])[^\s`\"']+"),
    re.compile(rb"[A-Za-z]:\\" + rb"Users\\(?![\[<])[^\s`\"']+"),
)
CREDENTIAL_PATTERNS = (
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{36,255}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,255}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"sk-[A-Za-z0-9_-]{20,255}"),
    re.compile(rb"xox[baprs]-[A-Za-z0-9-]{10,255}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
)
OBJECT_ID_PATTERN = re.compile(rb"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})")
APPROVED_FIXTURE_FINDINGS = {
    # Exact reviewed P2/P3 fixture blobs. Any content change creates a new blob
    # and therefore loses the exemption automatically.
    "c5af3eb63e68be7bfb0a024616fdab8065a02bae": frozenset(
        {"absolute user path", "runtime dump", "PDF signature"}
    ),
    "e4120a9207cf6d1e17b70528b636ec54daa017b2": frozenset({"runtime dump"}),
    "794c6de2f1b20b3de51d428b48f1444c21392b3a": frozenset(
        {"absolute user path", "runtime dump"}
    ),
    "4055dacde9e470c6cea854fd6fd34303f8031bd9": frozenset(
        {
            "absolute user path",
            "pilot identifier",
            "runtime dump",
            "PDF signature",
        }
    ),
    # Exact reviewed P5 boundary-audit fixtures after adding benchmark-specific
    # source/gold rules. Historical hashes remain approved for P2-P4 lineage.
    "6d92424854f52a4cc003c212c84e6d58c0ea5f99": frozenset({"runtime dump"}),
    "766e2f5f5621487782990fc04d54ccc4cf3b5764": frozenset(
        {
            "absolute user path",
            "pilot identifier",
            "runtime dump",
            "PDF signature",
        }
    ),
    # Exact reviewed P5 blinding-hardening fixtures. These supersede the prior
    # Task 8 blobs without removing historical approvals.
    "986112ce10dca50ad28280b67cbb745ba9f94c0b": frozenset({"runtime dump"}),
    "b2f151aaa18c211075c513af48a13213dbf838ab": frozenset(
        {
            "absolute user path",
            "pilot identifier",
            "runtime dump",
            "PDF signature",
        }
    ),
    # Exact reviewed P5 fail-closed identity/rationale fixtures.
    "c667b754f6e1b5486130b1e2762237790678c983": frozenset({"runtime dump"}),
    "9dbc689ecb161e8faa932a679ae9dfa6903721ef": frozenset(
        {
            "absolute user path",
            "pilot identifier",
            "runtime dump",
            "PDF signature",
        }
    ),
}


class AuditError(RuntimeError):
    """A repository could not be audited safely."""


@dataclass(frozen=True)
class AuditReport:
    repo: str
    refs: tuple[str, ...]
    commit_count: int
    reachable_object_count: int
    main_commit: str
    main_tree: str
    forbidden_object_count: int
    forbidden_object_digest: str
    forbidden_text_count: int
    forbidden_text_digest: str
    expected_tip: str | None
    findings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "repo": self.repo,
            "refs": list(self.refs),
            "commit_count": self.commit_count,
            "reachable_object_count": self.reachable_object_count,
            "main_commit": self.main_commit,
            "main_tree": self.main_tree,
            "forbidden_object_count": self.forbidden_object_count,
            "forbidden_object_digest": self.forbidden_object_digest,
            "forbidden_text_count": self.forbidden_text_count,
            "forbidden_text_digest": self.forbidden_text_digest,
            "expected_tip": self.expected_tip,
            "findings": list(self.findings),
        }


def _clean_git_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["GIT_CONFIG_GLOBAL"] = os.devnull
    return environment


def run_git(
    repo: Path,
    *args: str,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        env=_clean_git_environment(),
        input=input_bytes,
        capture_output=True,
        check=False,
    )


def _checked_git(repo: Path, *args: str) -> bytes:
    result = run_git(repo, *args)
    if result.returncode != 0:
        verb = args[0] if args else "command"
        raise AuditError(f"git {verb} failed")
    return result.stdout


def _lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _require_no_internal_git_symlinks(git_dir: Path) -> None:
    critical_paths = (
        git_dir / "HEAD",
        git_dir / "config",
        git_dir / "index",
        git_dir / "objects",
        git_dir / "refs",
        git_dir / "info",
        git_dir / "packed-refs",
    )
    if any(path.is_symlink() for path in critical_paths):
        raise AuditError("repository uses symlinked internal Git storage")
    for storage_root in (git_dir / "objects", git_dir / "refs", git_dir / "info"):
        if not storage_root.exists():
            continue
        for root, directories, files in os.walk(storage_root, followlinks=False):
            if any((Path(root) / name).is_symlink() for name in (*directories, *files)):
                raise AuditError("repository uses symlinked internal Git storage")


def _require_standalone_repository(repo: Path) -> Path:
    try:
        repo = repo.resolve(strict=True)
    except OSError as exc:
        raise AuditError("repository path is not a directory") from exc
    if not repo.is_dir():
        raise AuditError("repository path is not a directory")
    git_dir = repo / ".git"
    if git_dir.is_symlink() or not git_dir.is_dir():
        raise AuditError("repository must be a standalone Git worktree")
    _require_no_internal_git_symlinks(git_dir)

    resolved_git = git_dir.resolve()
    actual_git = Path(
        _checked_git(repo, "rev-parse", "--absolute-git-dir").decode(
            "utf-8", "surrogateescape"
        ).strip()
    ).resolve()
    common_git = Path(
        _checked_git(repo, "rev-parse", "--git-common-dir").decode(
            "utf-8", "surrogateescape"
        ).strip()
    )
    if not common_git.is_absolute():
        common_git = (repo / common_git).resolve()
    else:
        common_git = common_git.resolve()
    if actual_git != resolved_git or common_git != resolved_git:
        raise AuditError("repository must use a local standalone Git directory")

    worktrees = _checked_git(repo, "worktree", "list", "--porcelain").splitlines()
    worktree_paths = [
        Path(line.removeprefix(b"worktree ").decode("utf-8", "surrogateescape")).resolve()
        for line in worktrees
        if line.startswith(b"worktree ")
    ]
    if worktree_paths != [repo]:
        raise AuditError("repository must have exactly one worktree")

    shallow = _checked_git(repo, "rev-parse", "--is-shallow-repository").strip()
    if shallow != b"false" or _lexists(git_dir / "shallow"):
        raise AuditError("repository must not be shallow")
    forbidden_state = (
        git_dir / "info" / "grafts",
        git_dir / "objects" / "info" / "alternates",
        git_dir / "objects" / "info" / "http-alternates",
    )
    if any(_lexists(path) for path in forbidden_state):
        raise AuditError("repository uses external or rewritten object state")
    if any((git_dir / "objects" / "pack").glob("*.promisor")):
        raise AuditError("repository uses promisor object state")

    config = run_git(repo, "config", "--name-only", "--list")
    if config.returncode != 0:
        raise AuditError("git config failed")
    sensitive_config = re.compile(
        rb"^(?:extensions\.partialclone|remote\..*\.(?:promisor|partialclonefilter))$",
        re.IGNORECASE,
    )
    if any(sensitive_config.match(line.strip()) for line in config.stdout.splitlines()):
        raise AuditError("repository uses partial-clone or promisor configuration")
    fsck_config = re.compile(
        rb"^(?:fsck\.|receive\.fsck\.|fetch\.fsck\.|transfer\.fsckobjects$)",
        re.IGNORECASE,
    )
    if any(fsck_config.match(line.strip()) for line in config.stdout.splitlines()):
        raise AuditError("repository uses local fsck configuration")

    fsck = run_git(repo, "--no-replace-objects", "fsck", "--full", "--strict")
    if fsck.returncode != 0:
        raise AuditError("git fsck failed")
    return repo


def _ref_snapshot(repo: Path) -> tuple[tuple[str, str], ...]:
    output = _checked_git(
        repo, "for-each-ref", "--format=%(refname)%00%(objectname)"
    )
    snapshot: list[tuple[str, str]] = []
    for line in output.splitlines():
        if not line:
            continue
        try:
            raw_name, raw_object = line.split(b"\0", 1)
        except ValueError as exc:
            raise AuditError("Git ref inventory is malformed") from exc
        snapshot.append(
            (
                raw_name.decode("utf-8", "surrogateescape"),
                raw_object.decode("ascii"),
            )
        )
    return tuple(snapshot)


def list_refs(repo: Path) -> tuple[str, ...]:
    return tuple(name for name, _object_id in _ref_snapshot(repo))


def reachable_objects(repo: Path, tips: tuple[str, ...] | None = None) -> set[str]:
    selected_tips = tips or tuple(object_id for _name, object_id in _ref_snapshot(repo))
    output = _checked_git(
        repo,
        "--no-replace-objects",
        "rev-list",
        "--objects",
        "--no-object-names",
        *selected_tips,
    )
    return {line.decode("ascii") for line in output.splitlines() if line}


def commit_tree_entries(repo: Path, commit: str) -> dict[str, tuple[str, str, str]]:
    output = _checked_git(
        repo, "--no-replace-objects", "ls-tree", "-r", "-z", "--full-tree", commit
    )
    entries: dict[str, tuple[str, str, str]] = {}
    for record in output.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, object_id = metadata.split(b" ", 2)
        except ValueError as exc:
            raise AuditError(f"malformed tree entry in commit {commit}") from exc
        path = raw_path.decode("utf-8", "surrogateescape")
        entries[path] = (
            mode.decode("ascii"),
            object_type.decode("ascii"),
            object_id.decode("ascii"),
        )
    return entries


def read_blob(repo: Path, object_id: str) -> bytes:
    return _checked_git(repo, "--no-replace-objects", "cat-file", "blob", object_id)


def _read_commit(repo: Path, object_id: str) -> bytes:
    return _checked_git(repo, "--no-replace-objects", "cat-file", "commit", object_id)


def _finding(commit: str, path: str, object_id: str, detail: str) -> str:
    return f"commit {commit} path {path} object {object_id}: {detail}"


def _sensitive_details(
    data: bytes,
    forbidden_text: tuple[bytes, ...],
) -> tuple[str, ...]:
    details: list[str] = []
    if any(pattern.search(data) for pattern in RAW_ABSOLUTE_PATTERNS):
        details.append("absolute user path")
    if any(pattern.search(data) for pattern in PILOT_ID_PATTERNS):
        details.append("pilot identifier")
    if any(pattern.search(data) for pattern in FALLBACK_DUMP_PATTERNS):
        details.append("runtime dump")
    if any(marker and marker in data for marker in forbidden_text):
        details.append("forbidden text")
    if any(pattern.search(data) for pattern in CREDENTIAL_PATTERNS):
        details.append("credential pattern")
    return tuple(details)


def _commit_parents(raw_commit: bytes) -> tuple[str, ...]:
    header = raw_commit.split(b"\n\n", 1)[0]
    return tuple(
        line.split(b" ", 1)[1].decode("ascii")
        for line in header.splitlines()
        if line.startswith(b"parent ")
    )


def _deduplicate(items: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


def _object_policy_digest(objects: set[str]) -> str:
    payload = "".join(f"{value}\n" for value in sorted(objects)).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _text_policy_digest(markers: tuple[bytes, ...]) -> str:
    digest = hashlib.sha256()
    for marker in markers:
        digest.update(len(marker).to_bytes(8, "big"))
        digest.update(marker)
    return digest.hexdigest()


def audit_repository(
    repo: Path,
    forbidden_objects: set[str] | None = None,
    forbidden_text: tuple[bytes, ...] = (),
    *,
    expected_tip: str | None = None,
) -> AuditReport:
    repo = _require_standalone_repository(repo)
    if expected_tip is not None:
        try:
            encoded_expected_tip = expected_tip.encode("ascii", "strict")
        except UnicodeEncodeError as exc:
            raise AuditError("expected tip is not a valid object ID") from exc
        if OBJECT_ID_PATTERN.fullmatch(encoded_expected_tip) is None:
            raise AuditError("expected tip is not a valid object ID")
    policy_objects = forbidden_objects or set()
    frozen_refs = _ref_snapshot(repo)
    refs = tuple(name for name, _object_id in frozen_refs)
    ref_map = dict(frozen_refs)
    findings = [f"unexpected ref: {ref}" for ref in refs if ref not in ALLOWED_REFS]
    if EXPECTED_HEAD not in refs:
        findings.append(f"missing ref: {EXPECTED_HEAD}")

    symbolic_head = run_git(repo, "symbolic-ref", "-q", "HEAD")
    frozen_head = symbolic_head.stdout.strip() if symbolic_head.returncode == 0 else b""
    if frozen_head != EXPECTED_HEAD.encode():
        findings.append("HEAD must be refs/heads/main")

    main_commit = ref_map.get(EXPECTED_HEAD, "")
    if expected_tip is not None and main_commit != expected_tip:
        findings.append("main tip does not match expected tip")
    frozen_tips = tuple(object_id for _name, object_id in frozen_refs)
    reachable = reachable_objects(repo, frozen_tips)
    for object_id in sorted(reachable & policy_objects):
        findings.append(f"forbidden reachable object: {object_id}")

    commit_output = _checked_git(
        repo,
        "--no-replace-objects",
        "rev-list",
        "--reverse",
        "--topo-order",
        *frozen_tips,
    )
    commits = tuple(line.decode("ascii") for line in commit_output.splitlines() if line)
    raw_commits = {commit: _read_commit(repo, commit) for commit in commits}
    if len(commits) != EXPECTED_COMMIT_COUNT:
        findings.append("lineage must contain exactly three commits")
    elif not (
        _commit_parents(raw_commits[commits[0]]) == ()
        and _commit_parents(raw_commits[commits[1]]) == (commits[0],)
        and _commit_parents(raw_commits[commits[2]]) == (commits[1],)
    ):
        findings.append("lineage must have strict linear topology")

    for commit, raw_commit in raw_commits.items():
        for detail in _sensitive_details(raw_commit, forbidden_text):
            findings.append(f"commit {commit}: {detail}")

    blob_cache: dict[str, bytes] = {}
    for commit in commits:
        entries = commit_tree_entries(repo, commit)

        def tree_bytes(path: str) -> bytes:
            _mode, object_type, object_id = entries[path]
            if object_type != "blob":
                return b""
            if object_id not in blob_cache:
                blob_cache[object_id] = read_blob(repo, object_id)
            return blob_cache[object_id]

        audited_paths = sorted(entries)
        for path_finding in audit_paths(audited_paths, tree_bytes):
            path, detail = path_finding.rsplit(": ", 1)
            _mode, _object_type, object_id = entries[path]
            findings.append(_finding(commit, path, object_id, detail))

        for path, (mode, object_type, object_id) in sorted(entries.items()):
            path_bytes = path.encode("utf-8", "surrogateescape")
            for detail in _sensitive_details(path_bytes, forbidden_text):
                findings.append(_finding(commit, path, object_id, f"filename {detail}"))
            if mode == "160000":
                findings.append(_finding(commit, path, object_id, "gitlink"))
                continue
            if object_type != "blob":
                continue
            data = tree_bytes(path)
            if data.startswith(LFS_POINTER_PREFIX):
                findings.append(_finding(commit, path, object_id, "LFS pointer"))
            approved_findings = APPROVED_FIXTURE_FINDINGS.get(object_id, frozenset())
            for detail in _sensitive_details(data, forbidden_text):
                if detail in approved_findings:
                    continue
                findings.append(_finding(commit, path, object_id, detail))
            if (
                PDF_SIGNATURE in data[: PDF_PREAMBLE_LIMIT + len(PDF_SIGNATURE)]
                and "PDF signature" not in approved_findings
            ):
                findings.append(_finding(commit, path, object_id, "PDF signature"))

    if _ref_snapshot(repo) != frozen_refs:
        raise AuditError("repository refs changed during audit")
    final_head = run_git(repo, "symbolic-ref", "-q", "HEAD")
    final_head_value = final_head.stdout.strip() if final_head.returncode == 0 else b""
    if final_head_value != frozen_head:
        raise AuditError("repository HEAD changed during audit")
    main_tree = (
        _checked_git(
            repo, "--no-replace-objects", "rev-parse", f"{main_commit}^{{tree}}"
        ).decode("ascii").strip()
        if main_commit
        else ""
    )

    return AuditReport(
        repo=".",
        refs=refs,
        commit_count=len(commits),
        reachable_object_count=len(reachable),
        main_commit=main_commit,
        main_tree=main_tree,
        forbidden_object_count=len(policy_objects),
        forbidden_object_digest=_object_policy_digest(policy_objects),
        forbidden_text_count=len(forbidden_text),
        forbidden_text_digest=_text_policy_digest(forbidden_text),
        expected_tip=expected_tip,
        findings=_deduplicate(findings),
    )


def _read_input_file(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise AuditError("input file could not be read") from exc


def _load_forbidden_objects(path: Path | None) -> set[str]:
    if path is None:
        return set()
    objects: set[str] = set()
    for raw_line in _read_input_file(path).splitlines():
        object_id = raw_line.strip()
        if not object_id:
            continue
        if OBJECT_ID_PATTERN.fullmatch(object_id) is None:
            raise AuditError("forbidden object file contains a malformed object ID")
        objects.add(object_id.decode("ascii").lower())
    return objects


def _load_forbidden_text(path: Path | None) -> tuple[bytes, ...]:
    if path is None:
        return ()
    return tuple(line for line in _read_input_file(path).splitlines() if line)


def _prepare_json_output(repo: Path, path: Path) -> tuple[Path, str]:
    if _lexists(path):
        raise AuditError("JSON output must not already exist")
    try:
        repo_resolved = repo.resolve(strict=True)
        parent = path.parent.resolve(strict=True)
    except OSError as exc:
        raise AuditError("JSON output parent is unavailable") from exc
    if not parent.is_dir():
        raise AuditError("JSON output parent is unavailable")
    if parent == repo_resolved or repo_resolved in parent.parents:
        raise AuditError("JSON output must be outside the audited repository")
    return parent, path.name


def _write_json(parent: Path, name: str, report: AuditReport) -> None:
    payload = (json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n").encode()
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{name}.", suffix=".tmp", dir=parent
        )
        temporary = Path(temporary_name)
        os.fchmod(descriptor, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short JSON write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.link(temporary, parent / name)
        temporary.unlink()
        temporary = None
    except OSError as exc:
        raise AuditError("JSON output could not be written") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit all reachable refs and historical trees in a Git repository."
    )
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--forbidden-object-file", type=Path)
    parser.add_argument("--forbidden-text-file", type=Path)
    parser.add_argument("--expected-tip", required=True)
    parser.add_argument("--json-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        json_target = (
            _prepare_json_output(args.repo, args.json_output)
            if args.json_output is not None
            else None
        )
        forbidden_objects = _load_forbidden_objects(args.forbidden_object_file)
        forbidden_text = _load_forbidden_text(args.forbidden_text_file)
        report = audit_repository(
            args.repo,
            forbidden_objects,
            forbidden_text,
            expected_tip=args.expected_tip,
        )
        if json_target is not None:
            _write_json(*json_target, report)
    except AuditError as exc:
        print(f"Public lineage audit: ERROR: {exc}", file=sys.stderr)
        return 2

    status = "FAIL" if report.findings else "PASS"
    print(
        f"Public lineage audit: {status} "
        f"refs={len(report.refs)} commits={report.commit_count} "
        f"reachable_objects={report.reachable_object_count}"
    )
    for finding in report.findings:
        print(f"- {finding}")
    return 1 if report.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
