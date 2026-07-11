"""Exact clean-lineage reconstruction boundaries."""

from __future__ import annotations

import io
import json
import os
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

import scripts.reconstruct_public_lineage as reconstructor
from scripts.reconstruct_public_lineage import (
    LineageError,
    Snapshot,
    amend_tip,
    build_lineage,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "reconstruct_public_lineage.py"


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


def commit_files(repo: Path, message: str, files: dict[str, bytes | None]) -> str:
    for relative_path, content in files.items():
        path = repo / relative_path
        if content is None:
            path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    git(repo, "add", "-A")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def make_source_history(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    source = tmp_path / "source"
    source.mkdir(parents=True)
    git(source, "init", "-b", "private-main")
    git(source, "config", "user.name", "Azoth Test")
    git(source, "config", "user.email", "azoth@example.invalid")
    private_root = commit_files(
        source,
        "private pilot",
        {"private-corpus.txt": b"must never be public\n"},
    )
    p2 = commit_files(
        source,
        "private p2",
        {"private-corpus.txt": None, "README.md": b"baseline\n"},
    )
    p3 = commit_files(source, "private p3", {"azoth.py": b"print('azoth')\n"})
    p4 = commit_files(source, "private p4", {"ROADMAP.md": b"clean lineage\n"})
    git(source, "branch", "legacy", private_root)
    git(source, "tag", "private-v0", private_root)
    return source, {
        "private_root": private_root,
        "p2": p2,
        "p3": p3,
        "p4": p4,
    }


def candidate_identity(destination: Path) -> dict[str, str]:
    commits = git(destination, "rev-list", "--reverse", "main").stdout.splitlines()
    assert len(commits) == 3
    return {
        "expected_tip": commits[2],
        "expected_first_tree": git(
            destination, "rev-parse", f"{commits[0]}^{{tree}}"
        ).stdout.strip(),
        "expected_second_tree": git(
            destination, "rev-parse", f"{commits[1]}^{{tree}}"
        ).stdout.strip(),
    }


def build_identity_arguments(source: Path, refs: dict[str, str]) -> list[str]:
    return [
        "--expected-first-commit",
        refs["p2"],
        "--expected-first-tree",
        git(
            source,
            "--no-replace-objects",
            "rev-parse",
            f"{refs['p2']}^{{tree}}",
        ).stdout.strip(),
        "--expected-second-commit",
        refs["p3"],
        "--expected-second-tree",
        git(
            source,
            "--no-replace-objects",
            "rev-parse",
            f"{refs['p3']}^{{tree}}",
        ).stdout.strip(),
    ]


def source_snapshot_identity_arguments(source: Path, ref: str) -> list[str]:
    commit = git(
        source,
        "--no-replace-objects",
        "rev-parse",
        f"{ref}^{{commit}}",
    ).stdout.strip()
    tree = git(
        source,
        "--no-replace-objects",
        "rev-parse",
        f"{commit}^{{tree}}",
    ).stdout.strip()
    return [
        "--expected-source-commit",
        commit,
        "--expected-source-tree",
        tree,
    ]


def amend_candidate(
    source: Path,
    destination: Path,
    snapshot: Snapshot,
):
    return amend_tip(
        source,
        destination,
        snapshot,
        **candidate_identity(destination),
    )


def make_archive(members: tuple[tuple[str, str], ...]) -> bytes:
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w") as archive:
        for name, kind in members:
            member = tarfile.TarInfo(name)
            if kind == "file":
                content = f"{name}\n".encode()
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
            elif kind == "directory":
                member.type = tarfile.DIRTYPE
                archive.addfile(member)
            elif kind == "symlink":
                member.type = tarfile.SYMTYPE
                member.linkname = "target"
                archive.addfile(member)
            elif kind == "fifo":
                member.type = tarfile.FIFOTYPE
                archive.addfile(member)
            else:
                raise AssertionError(f"unsupported test archive member kind: {kind}")
    return payload.getvalue()


def test_builds_three_commit_lineage_with_exact_tree_parity(tmp_path: Path) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    proofs = build_lineage(
        source,
        destination,
        (
            Snapshot(refs["p2"], "Sanitized public baseline"),
            Snapshot(refs["p3"], "Wheel resources and workspace initialization"),
            Snapshot(refs["p4"], "Clean public Git lineage"),
        ),
    )
    assert len(proofs) == 3
    assert git(destination, "rev-list", "--count", "main").stdout.strip() == "3"
    assert [proof.source_tree for proof in proofs] == [
        proof.clean_tree for proof in proofs
    ]
    assert git(
        destination, "for-each-ref", "--format=%(refname)"
    ).stdout.splitlines() == ["refs/heads/main"]
    assert git(destination, "log", "--reverse", "--format=%s").stdout.splitlines() == [
        "Sanitized public baseline",
        "Wheel resources and workspace initialization",
        "Clean public Git lineage",
    ]
    assert git(destination, "config", "--local", "user.name").stdout.strip() == (
        "Azoth Test"
    )
    assert git(destination, "config", "--local", "user.email").stdout.strip() == (
        "azoth@example.invalid"
    )
    assert git(destination, "status", "--porcelain=v1").stdout == ""


def test_build_accepts_existing_empty_destination(tmp_path: Path) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    destination.mkdir()

    proofs = build_lineage(
        source,
        destination,
        (Snapshot(refs["p2"], "Sanitized public baseline"),),
    )

    assert len(proofs) == 1
    assert proofs[0].source_tree == proofs[0].clean_tree


def test_rejects_destination_that_already_contains_a_file(tmp_path: Path) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("do not overwrite\n", encoding="utf-8")

    with pytest.raises(LineageError, match="destination must be absent or empty"):
        build_lineage(
            source,
            destination,
            (Snapshot(refs["p2"], "Sanitized public baseline"),),
        )

    assert marker.read_text(encoding="utf-8") == "do not overwrite\n"


@pytest.mark.parametrize("dirty_kind", ["tracked", "untracked"])
def test_rejects_dirty_source_worktree(tmp_path: Path, dirty_kind: str) -> None:
    source, refs = make_source_history(tmp_path)
    if dirty_kind == "tracked":
        (source / "README.md").write_text("changed\n", encoding="utf-8")
    else:
        (source / "scratch.txt").write_text("untracked\n", encoding="utf-8")
    destination = tmp_path / "clean"

    with pytest.raises(LineageError, match="source worktree is not clean"):
        build_lineage(
            source,
            destination,
            (Snapshot(refs["p2"], "Sanitized public baseline"),),
        )

    assert not destination.exists()


@pytest.mark.parametrize(
    "state_kind",
    ["replace", "graft", "alternate", "shallow", "promisor"],
)
def test_rejects_rewritten_or_incomplete_source_state_before_mutation(
    tmp_path: Path,
    state_kind: str,
) -> None:
    source, refs = make_source_history(tmp_path / "source-parent")
    git_dir = source / ".git"
    if state_kind == "replace":
        git(source, "replace", refs["p2"], refs["p3"])
    elif state_kind == "graft":
        grafts = git_dir / "info" / "grafts"
        grafts.parent.mkdir(parents=True, exist_ok=True)
        grafts.write_text(refs["p4"] + "\n", encoding="ascii")
    elif state_kind == "alternate":
        donor, _donor_refs = make_source_history(tmp_path / "donor-parent")
        alternates = git_dir / "objects" / "info" / "alternates"
        alternates.write_text(
            str(donor / ".git" / "objects") + "\n",
            encoding="utf-8",
        )
    elif state_kind == "shallow":
        (git_dir / "shallow").write_text(refs["p4"] + "\n", encoding="ascii")
    else:
        git(source, "config", "remote.origin.promisor", "true")
    destination = tmp_path / "clean"

    with pytest.raises(LineageError, match="rewritten|incomplete|promisor|shallow"):
        build_lineage(
            source,
            destination,
            (Snapshot(refs["p2"], "Sanitized public baseline"),),
        )

    assert not destination.exists()


def test_rejects_symlinked_source_git_storage_before_mutation(tmp_path: Path) -> None:
    source, refs = make_source_history(tmp_path)
    pack = source / ".git" / "objects" / "pack"
    external = tmp_path / "external-pack"
    external.mkdir()
    pack.rmdir()
    pack.symlink_to(external, target_is_directory=True)
    destination = tmp_path / "clean"

    with pytest.raises(LineageError, match="internal Git storage"):
        build_lineage(
            source,
            destination,
            (Snapshot(refs["p2"], "Sanitized public baseline"),),
        )

    assert not destination.exists()


def test_rejects_symlinked_source_git_directory_before_mutation(tmp_path: Path) -> None:
    source, refs = make_source_history(tmp_path)
    external_git = tmp_path / "external-git"
    (source / ".git").rename(external_git)
    (source / ".git").symlink_to(external_git, target_is_directory=True)
    destination = tmp_path / "clean"

    with pytest.raises(LineageError, match="internal Git storage"):
        build_lineage(
            source,
            destination,
            (Snapshot(refs["p2"], "Sanitized public baseline"),),
        )

    assert not destination.exists()


def test_rejects_linked_source_worktree_promisor_configuration(
    tmp_path: Path,
) -> None:
    source, refs = make_source_history(tmp_path / "primary-parent")
    linked = tmp_path / "linked-source"
    git(source, "config", "extensions.worktreeConfig", "true")
    git(source, "worktree", "add", "--detach", str(linked), refs["p4"])
    git(linked, "config", "--worktree", "remote.origin.promisor", "true")
    git(
        linked,
        "config",
        "--worktree",
        "remote.origin.partialCloneFilter",
        "blob:none",
    )
    destination = tmp_path / "clean"

    with pytest.raises(LineageError, match="promisor"):
        build_lineage(
            linked,
            destination,
            (Snapshot(refs["p2"], "Sanitized public baseline"),),
        )

    assert not destination.exists()


def test_rejects_source_ref_that_is_not_a_commit(tmp_path: Path) -> None:
    source, _refs = make_source_history(tmp_path)
    blob = git(source, "rev-parse", "HEAD:README.md").stdout.strip()

    with pytest.raises(LineageError, match="source ref does not resolve to a commit"):
        build_lineage(
            source,
            tmp_path / "clean",
            (Snapshot(blob, "Sanitized public baseline"),),
        )


@pytest.mark.parametrize("destination_exists", [False, True])
def test_build_preflights_last_snapshot_ref_before_destination_mutation(
    tmp_path: Path,
    destination_exists: bool,
) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    if destination_exists:
        destination.mkdir()

    with pytest.raises(LineageError, match="source ref does not resolve to a commit"):
        build_lineage(
            source,
            destination,
            (
                Snapshot(refs["p2"], "Sanitized public baseline"),
                Snapshot(refs["p3"], "Wheel resources and workspace initialization"),
                Snapshot("missing-ref", "Clean public Git lineage"),
            ),
        )

    if destination_exists:
        assert list(destination.iterdir()) == []
    else:
        assert not destination.exists()


@pytest.mark.parametrize("bad_index", [0, 1, 2])
@pytest.mark.parametrize("destination_exists", [False, True])
def test_build_preflights_every_archive_before_destination_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bad_index: int,
    destination_exists: bool,
) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    if destination_exists:
        destination.mkdir()
    real_run = subprocess.run
    archive_index = 0

    def run_with_invalid_archive(*args: object, **kwargs: object) -> object:
        nonlocal archive_index
        command = args[0]
        if command[:4] == ["git", "--no-replace-objects", "archive", "--format=tar"]:
            current_index = archive_index
            archive_index += 1
            if current_index == bad_index:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=b"not a tar archive",
                    stderr=b"",
                )
        return real_run(*args, **kwargs)

    monkeypatch.setattr(reconstructor.subprocess, "run", run_with_invalid_archive)

    with pytest.raises(LineageError, match="source archive is invalid"):
        build_lineage(
            source,
            destination,
            (
                Snapshot(refs["p2"], "Sanitized public baseline"),
                Snapshot(refs["p3"], "Wheel resources and workspace initialization"),
                Snapshot(refs["p4"], "Clean public Git lineage"),
            ),
        )

    if destination_exists:
        assert list(destination.iterdir()) == []
    else:
        assert not destination.exists()


@pytest.mark.parametrize(
    "member_name",
    ["../escape.txt", ".git/azoth-hooks/pre-commit"],
)
def test_rejects_unsafe_archive_member_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    member_name: str,
) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    payload = io.BytesIO()
    content = b"escape\n"
    with tarfile.open(fileobj=payload, mode="w") as archive:
        member = tarfile.TarInfo(member_name)
        member.size = len(content)
        archive.addfile(member, io.BytesIO(content))

    real_run = subprocess.run

    def run_with_unsafe_archive(*args: object, **kwargs: object) -> object:
        command = args[0]
        if command[:4] == ["git", "--no-replace-objects", "archive", "--format=tar"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=payload.getvalue(),
                stderr=b"",
            )
        return real_run(*args, **kwargs)

    monkeypatch.setattr(reconstructor.subprocess, "run", run_with_unsafe_archive)

    with pytest.raises(LineageError, match="unsafe archive path"):
        build_lineage(
            source,
            destination,
            (Snapshot(refs["p2"], "Sanitized public baseline"),),
        )

    assert not (tmp_path / "escape.txt").exists()
    assert not destination.exists()


def test_build_preflights_unsafe_archive_member_type_before_destination_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    payload = make_archive((("unsafe-pipe", "fifo"),))
    real_run = subprocess.run

    def run_with_unsafe_member(*args: object, **kwargs: object) -> object:
        command = args[0]
        if command[:4] == ["git", "--no-replace-objects", "archive", "--format=tar"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=payload,
                stderr=b"",
            )
        return real_run(*args, **kwargs)

    monkeypatch.setattr(reconstructor.subprocess, "run", run_with_unsafe_member)

    with pytest.raises(LineageError, match="unsafe member type"):
        build_lineage(
            source,
            destination,
            (Snapshot(refs["p2"], "Sanitized public baseline"),),
        )

    assert not destination.exists()


@pytest.mark.parametrize(
    "members",
    [
        (("duplicate", "file"), ("duplicate", "file")),
        (("parent", "file"), ("parent/child", "file")),
        (("parent/child", "file"), ("parent", "file")),
        (("parent", "symlink"), ("parent/child", "file")),
        (("parent/child", "file"), ("parent", "symlink")),
        (("collision", "file"), ("collision", "directory")),
    ],
    ids=[
        "duplicate-path",
        "file-parent-first",
        "file-parent-last",
        "symlink-parent-first",
        "symlink-parent-last",
        "file-directory-collision",
    ],
)
def test_rejects_archive_member_graph_conflicts_before_clearing_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    members: tuple[tuple[str, str], ...],
) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    build_lineage(
        source,
        destination,
        (Snapshot(refs["p2"], "Sanitized public baseline"),),
    )
    original_head = git(destination, "rev-parse", "HEAD").stdout.strip()
    original_readme = (destination / "README.md").read_bytes()
    payload = make_archive(members)
    real_run = subprocess.run

    def run_with_conflicting_archive(*args: object, **kwargs: object) -> object:
        command = args[0]
        if command[:4] == ["git", "--no-replace-objects", "archive", "--format=tar"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=payload,
                stderr=b"",
            )
        return real_run(*args, **kwargs)

    monkeypatch.setattr(reconstructor.subprocess, "run", run_with_conflicting_archive)

    with pytest.raises(
        LineageError,
        match="archive paths conflict|archive path traverses a symlink",
    ):
        reconstructor.materialize_snapshot(source, destination, refs["p3"])

    assert git(destination, "rev-parse", "HEAD").stdout.strip() == original_head
    assert (destination / "README.md").exists()
    assert (destination / "README.md").read_bytes() == original_readme
    assert git(destination, "status", "--porcelain=v1").stdout == ""


def test_rejects_destination_symlink_without_following_it(tmp_path: Path) -> None:
    source, refs = make_source_history(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    destination = tmp_path / "clean"
    destination.symlink_to(target, target_is_directory=True)

    with pytest.raises(LineageError, match="destination must be absent or empty"):
        build_lineage(
            source,
            destination,
            (Snapshot(refs["p2"], "Sanitized public baseline"),),
        )

    assert list(target.iterdir()) == []


def test_preserves_executable_and_symlink_modes_with_exact_tree_id(
    tmp_path: Path,
) -> None:
    source, _refs = make_source_history(tmp_path)
    executable = source / "bin" / "run.sh"
    executable.parent.mkdir()
    executable.write_bytes(b"#!/bin/sh\necho azoth\n")
    executable.chmod(0o755)
    (source / "run-link").symlink_to("bin/run.sh")
    mode_ref = commit_files(source, "private modes", {})
    destination = tmp_path / "clean"

    proof = build_lineage(
        source,
        destination,
        (Snapshot(mode_ref, "Sanitized public baseline"),),
    )[0]

    assert proof.source_tree == proof.clean_tree
    entries = git(destination, "ls-tree", "-r", "HEAD").stdout.splitlines()
    assert any(
        line.startswith("100755 blob ") and line.endswith("\tbin/run.sh")
        for line in entries
    )
    assert any(line.startswith("120000 blob ") and line.endswith("\trun-link") for line in entries)


def test_does_not_import_source_ancestors_branches_or_tags(tmp_path: Path) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"

    build_lineage(
        source,
        destination,
        (
            Snapshot(refs["p2"], "Sanitized public baseline"),
            Snapshot(refs["p3"], "Wheel resources and workspace initialization"),
            Snapshot(refs["p4"], "Clean public Git lineage"),
        ),
    )

    assert git(
        destination, "for-each-ref", "--format=%(refname)"
    ).stdout.splitlines() == ["refs/heads/main"]
    assert run_git(
        destination, "cat-file", "-e", f"{refs['private_root']}^{{commit}}"
    ).returncode != 0
    assert run_git(destination, "cat-file", "-e", f"{refs['p2']}^{{commit}}").returncode != 0
    assert not (destination / "private-corpus.txt").exists()


def test_amend_tip_preserves_first_two_commits_and_replaces_only_tip(
    tmp_path: Path,
) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    build_lineage(
        source,
        destination,
        (
            Snapshot(refs["p2"], "Sanitized public baseline"),
            Snapshot(refs["p3"], "Wheel resources and workspace initialization"),
            Snapshot(refs["p4"], "Clean public Git lineage"),
        ),
    )
    updated_ref = commit_files(
        source,
        "private p4 evidence",
        {"ROADMAP.md": b"clean lineage\ncutover evidence\n"},
    )

    before = git(destination, "rev-list", "--reverse", "main").stdout.splitlines()
    proof = amend_candidate(
        source,
        destination,
        Snapshot(updated_ref, "Clean public Git lineage"),
    )
    after = git(destination, "rev-list", "--reverse", "main").stdout.splitlines()
    assert after[:2] == before[:2]
    assert after[2] != before[2]
    assert proof.source_tree == proof.clean_tree
    assert proof.clean_commit == after[2]
    assert git(destination, "rev-list", "--count", "main").stdout.strip() == "3"
    assert git(destination, "status", "--porcelain=v1").stdout == ""


def test_amend_rejects_unapproved_final_message_before_mutation(
    tmp_path: Path,
) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    build_lineage(
        source,
        destination,
        (
            Snapshot(refs["p2"], "Sanitized public baseline"),
            Snapshot(refs["p3"], "Wheel resources and workspace initialization"),
            Snapshot(refs["p4"], "Clean public Git lineage"),
        ),
    )
    identity = candidate_identity(destination)
    original_tip = identity["expected_tip"]
    updated_ref = commit_files(
        source,
        "private update",
        {"ROADMAP.md": b"updated\n"},
    )

    with pytest.raises(LineageError, match="commit messages"):
        amend_tip(
            source,
            destination,
            Snapshot(updated_ref, "Unapproved final message"),
            **identity,
        )

    assert git(destination, "rev-parse", "HEAD").stdout.strip() == original_tip


def test_amend_tip_rejects_destination_with_an_extra_ref(tmp_path: Path) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    build_lineage(
        source,
        destination,
        (
            Snapshot(refs["p2"], "Sanitized public baseline"),
            Snapshot(refs["p3"], "Wheel resources and workspace initialization"),
            Snapshot(refs["p4"], "Clean public Git lineage"),
        ),
    )
    original_tip = git(destination, "rev-parse", "HEAD").stdout.strip()
    git(destination, "branch", "unexpected", "HEAD~1")
    updated_ref = commit_files(source, "private update", {"ROADMAP.md": b"updated\n"})

    with pytest.raises(LineageError, match="exactly one main branch"):
        amend_candidate(
            source,
            destination,
            Snapshot(updated_ref, "Clean public Git lineage"),
        )

    assert git(destination, "rev-parse", "HEAD").stdout.strip() == original_tip


def test_amend_tip_rejects_merge_topology_before_mutation(tmp_path: Path) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    build_lineage(
        source,
        destination,
        (
            Snapshot(refs["p2"], "Sanitized public baseline"),
            Snapshot(refs["p3"], "Wheel resources and workspace initialization"),
            Snapshot(refs["p4"], "Clean public Git lineage"),
        ),
    )
    commits = git(destination, "rev-list", "--reverse", "main").stdout.splitlines()
    tip_tree = git(destination, "rev-parse", "HEAD^{tree}").stdout.strip()
    merge_tip = git(
        destination,
        "commit-tree",
        tip_tree,
        "-p",
        commits[1],
        "-p",
        commits[0],
        "-m",
        "merge tip",
    ).stdout.strip()
    git(destination, "update-ref", "refs/heads/main", merge_tip, commits[2])
    original_roadmap = (destination / "ROADMAP.md").read_bytes()
    updated_ref = commit_files(source, "private update", {"ROADMAP.md": b"updated\n"})

    with pytest.raises(LineageError, match="strict linear topology"):
        amend_candidate(
            source,
            destination,
            Snapshot(updated_ref, "Clean public Git lineage"),
        )

    assert git(destination, "rev-parse", "HEAD").stdout.strip() == merge_tip
    assert (destination / "ROADMAP.md").read_bytes() == original_roadmap
    assert git(destination, "status", "--porcelain=v1").stdout == ""


def test_amend_tip_rejects_linked_worktree_destination_before_mutation(
    tmp_path: Path,
) -> None:
    source, refs = make_source_history(tmp_path)
    primary = tmp_path / "primary"
    build_lineage(
        source,
        primary,
        (
            Snapshot(refs["p2"], "Sanitized public baseline"),
            Snapshot(refs["p3"], "Wheel resources and workspace initialization"),
            Snapshot(refs["p4"], "Clean public Git lineage"),
        ),
    )
    git(primary, "switch", "--detach")
    destination = tmp_path / "linked"
    git(primary, "worktree", "add", str(destination), "main")
    assert (destination / ".git").is_file()
    original_tip = git(destination, "rev-parse", "HEAD").stdout.strip()
    original_roadmap = (destination / "ROADMAP.md").read_bytes()
    updated_ref = commit_files(source, "private update", {"ROADMAP.md": b"updated\n"})

    with pytest.raises(LineageError, match="destination is not a Git repository"):
        amend_candidate(
            source,
            destination,
            Snapshot(updated_ref, "Clean public Git lineage"),
        )

    assert git(destination, "rev-parse", "HEAD").stdout.strip() == original_tip
    assert (destination / "ROADMAP.md").read_bytes() == original_roadmap
    assert git(destination, "status", "--porcelain=v1").stdout == ""


def test_build_ignores_ambient_git_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, refs = make_source_history(tmp_path / "target")
    decoy, _decoy_refs = make_source_history(tmp_path / "decoy")
    destination = tmp_path / "clean"
    monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))

    proofs = build_lineage(
        source,
        destination,
        (Snapshot(refs["p2"], "Sanitized public baseline"),),
    )

    assert len(proofs) == 1
    assert proofs[0].source_commit == refs["p2"]


def test_build_accepts_a_clean_linked_source_worktree(tmp_path: Path) -> None:
    source, refs = make_source_history(tmp_path / "primary-parent")
    linked = tmp_path / "linked-source"
    git(
        source,
        "worktree",
        "add",
        "--detach",
        str(linked),
        refs["p4"],
    )
    destination = tmp_path / "clean"

    proofs = build_lineage(
        linked,
        destination,
        (Snapshot(refs["p2"], "Sanitized public baseline"),),
    )

    assert proofs[0].source_commit == refs["p2"]
    assert proofs[0].source_tree == proofs[0].clean_tree


def test_linked_source_rejects_destination_inside_common_git_directory(
    tmp_path: Path,
) -> None:
    source, refs = make_source_history(tmp_path / "primary-parent")
    linked = tmp_path / "linked-source"
    git(source, "worktree", "add", "--detach", str(linked), refs["p4"])
    destination = source / ".git" / "candidate"

    with pytest.raises(LineageError, match="outside the source"):
        build_lineage(
            linked,
            destination,
            (Snapshot(refs["p2"], "Sanitized public baseline"),),
        )

    assert not destination.exists()


def test_linked_source_rejects_amend_candidate_inside_common_git_directory(
    tmp_path: Path,
) -> None:
    source, refs = make_source_history(tmp_path / "primary-parent")
    linked = tmp_path / "linked-source"
    git(source, "worktree", "add", "--detach", str(linked), refs["p4"])
    outside_candidate = tmp_path / "outside-candidate"
    build_lineage(
        linked,
        outside_candidate,
        (
            Snapshot(refs["p2"], "Sanitized public baseline"),
            Snapshot(refs["p3"], "Wheel resources and workspace initialization"),
            Snapshot(refs["p4"], "Clean public Git lineage"),
        ),
    )
    nested_candidate = source / ".git" / "candidate"
    outside_candidate.rename(nested_candidate)
    identity = candidate_identity(nested_candidate)
    updated_ref = commit_files(
        source,
        "private update",
        {"ROADMAP.md": b"updated\n"},
    )

    with pytest.raises(LineageError, match="outside the source"):
        amend_tip(
            linked,
            nested_candidate,
            Snapshot(updated_ref, "Clean public Git lineage"),
            **identity,
        )

    assert git(nested_candidate, "rev-parse", "HEAD").stdout.strip() == identity[
        "expected_tip"
    ]


def test_foreign_commit_is_not_visible_through_ambient_alternates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _refs = make_source_history(tmp_path / "target")
    donor, _donor_refs = make_source_history(tmp_path / "donor")
    foreign_commit = commit_files(
        donor, "donor-only commit", {"DONOR.txt": b"foreign object\n"}
    )
    destination = tmp_path / "clean"
    monkeypatch.setenv(
        "GIT_ALTERNATE_OBJECT_DIRECTORIES", str(donor / ".git" / "objects")
    )

    with pytest.raises(LineageError, match="does not resolve"):
        build_lineage(
            source,
            destination,
            (Snapshot(foreign_commit, "Sanitized public baseline"),),
        )

    assert not destination.exists()


@pytest.mark.parametrize(
    "state_kind",
    ["shallow", "graft", "alternate", "extra-worktree", "promisor"],
)
def test_amend_rejects_incomplete_repository_state_before_mutation(
    tmp_path: Path,
    state_kind: str,
) -> None:
    source, refs = make_source_history(tmp_path / "source-parent")
    destination = tmp_path / "clean"
    build_lineage(
        source,
        destination,
        (
            Snapshot(refs["p2"], "Sanitized public baseline"),
            Snapshot(refs["p3"], "Wheel resources and workspace initialization"),
            Snapshot(refs["p4"], "Clean public Git lineage"),
        ),
    )
    identity = candidate_identity(destination)
    original_tip = identity["expected_tip"]
    original_roadmap = (destination / "ROADMAP.md").read_bytes()
    if state_kind == "shallow":
        (destination / ".git" / "shallow").write_text(
            original_tip + "\n", encoding="ascii"
        )
    elif state_kind == "graft":
        grafts = destination / ".git" / "info" / "grafts"
        grafts.parent.mkdir(parents=True, exist_ok=True)
        grafts.write_text(
            original_tip + "\n", encoding="ascii"
        )
    elif state_kind == "alternate":
        donor, _donor_refs = make_source_history(tmp_path / "donor-parent")
        (destination / ".git" / "objects" / "info" / "alternates").write_text(
            str(donor / ".git" / "objects") + "\n", encoding="utf-8"
        )
    elif state_kind == "extra-worktree":
        git(destination, "worktree", "add", "--detach", str(tmp_path / "linked"), "HEAD")
    else:
        git(destination, "config", "remote.origin.promisor", "true")
    updated_ref = commit_files(
        source, "private update", {"ROADMAP.md": b"updated\n"}
    )

    with pytest.raises(LineageError):
        amend_tip(
            source,
            destination,
            Snapshot(updated_ref, "Clean public Git lineage"),
            **identity,
        )

    assert git(destination, "rev-parse", "HEAD").stdout.strip() == original_tip
    assert (destination / "ROADMAP.md").read_bytes() == original_roadmap


def test_amend_rejects_symlinked_destination_git_storage_before_mutation(
    tmp_path: Path,
) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    build_lineage(
        source,
        destination,
        (
            Snapshot(refs["p2"], "Sanitized public baseline"),
            Snapshot(refs["p3"], "Wheel resources and workspace initialization"),
            Snapshot(refs["p4"], "Clean public Git lineage"),
        ),
    )
    original_tip = git(destination, "rev-parse", "HEAD").stdout.strip()
    pack = destination / ".git" / "objects" / "pack"
    external = tmp_path / "external-pack"
    external.mkdir()
    pack.rmdir()
    pack.symlink_to(external, target_is_directory=True)
    updated_ref = commit_files(
        source,
        "private update",
        {"ROADMAP.md": b"updated\n"},
    )

    with pytest.raises(LineageError, match="internal Git storage"):
        amend_tip(
            source,
            destination,
            Snapshot(updated_ref, "Clean public Git lineage"),
            expected_tip=original_tip,
            expected_first_tree="0" * 40,
            expected_second_tree="0" * 40,
        )

    assert git(destination, "rev-parse", "HEAD").stdout.strip() == original_tip


@pytest.mark.parametrize(
    "identity_key",
    ["expected_tip", "expected_first_tree", "expected_second_tree"],
)
def test_amend_rejects_wrong_candidate_identity_before_mutation(
    tmp_path: Path,
    identity_key: str,
) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    build_lineage(
        source,
        destination,
        (
            Snapshot(refs["p2"], "Sanitized public baseline"),
            Snapshot(refs["p3"], "Wheel resources and workspace initialization"),
            Snapshot(refs["p4"], "Clean public Git lineage"),
        ),
    )
    identity = candidate_identity(destination)
    original_tip = identity["expected_tip"]
    identity[identity_key] = "0" * 40
    updated_ref = commit_files(
        source, "private update", {"ROADMAP.md": b"updated\n"}
    )

    with pytest.raises(LineageError, match="candidate identity"):
        amend_tip(
            source,
            destination,
            Snapshot(updated_ref, "Clean public Git lineage"),
            **identity,
        )

    assert git(destination, "rev-parse", "HEAD").stdout.strip() == original_tip


def test_build_preflights_sparse_archive_before_destination_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w") as archive:
        member = tarfile.TarInfo("sparse.bin")
        member.type = tarfile.GNUTYPE_SPARSE
        member.size = 0
        archive.addfile(member, io.BytesIO())
    real_run = subprocess.run

    def run_with_sparse_archive(*args: object, **kwargs: object) -> object:
        command = args[0]
        if command[:4] == ["git", "--no-replace-objects", "archive", "--format=tar"]:
            return subprocess.CompletedProcess(
                command, 0, stdout=payload.getvalue(), stderr=b""
            )
        return real_run(*args, **kwargs)

    monkeypatch.setattr(reconstructor.subprocess, "run", run_with_sparse_archive)

    with pytest.raises(LineageError, match="sparse|unsafe member type"):
        build_lineage(
            source,
            destination,
            (Snapshot(refs["p2"], "Sanitized public baseline"),),
        )

    assert not destination.exists()


def test_git_failure_redacts_sensitive_arguments(tmp_path: Path) -> None:
    source, _refs = make_source_history(tmp_path)
    canary = "secret-message-canary"

    with pytest.raises(LineageError) as failure:
        reconstructor._checked_git(source, "rev-parse", canary)

    assert canary not in str(failure.value)
    assert str(source) not in str(failure.value)


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_proof_output_is_published_only_after_complete_write(tmp_path: Path) -> None:
    source, _refs = make_source_history(tmp_path)
    json_output = tmp_path / "proof.json"
    reservation = reconstructor._reserve_proof_output(
        source,
        tmp_path / "clean",
        json_output,
    )

    assert not json_output.exists()
    assert reservation.temporary.exists()

    reconstructor._write_reserved_proofs(reservation, ())
    reservation.finish()

    assert json.loads(json_output.read_text(encoding="utf-8")) == {"proofs": []}
    assert not reservation.temporary.exists()


def test_proof_publication_failure_leaves_no_canonical_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _refs = make_source_history(tmp_path)
    json_output = tmp_path / "proof.json"
    reservation = reconstructor._reserve_proof_output(
        source,
        tmp_path / "clean",
        json_output,
    )

    def fail_link(*_args: object, **_kwargs: object) -> None:
        raise OSError("forced publication failure")

    monkeypatch.setattr(os, "link", fail_link)

    with pytest.raises(LineageError, match="could not be written"):
        reconstructor._write_reserved_proofs(reservation, ())
    reservation.abort()

    assert not json_output.exists()
    assert not reservation.temporary.exists()


def test_build_cli_writes_three_snapshot_proofs(tmp_path: Path) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    json_output = tmp_path / "proof.json"

    result = run_cli(
        "build",
        "--source",
        str(source),
        "--destination",
        str(destination),
        "--snapshot",
        f"{refs['p2']}::Sanitized public baseline",
        "--snapshot",
        f"{refs['p3']}::Wheel resources and workspace initialization",
        "--snapshot",
        f"{refs['p4']}::Clean public Git lineage",
        *build_identity_arguments(source, refs),
        "--json-output",
        str(json_output),
    )

    assert result.returncode == 0
    assert "Public lineage reconstruction: PASS" in result.stdout
    evidence = json.loads(json_output.read_text(encoding="utf-8"))
    assert len(evidence["proofs"]) == 3
    assert [item["source_ref"] for item in evidence["proofs"]] == [
        refs["p2"],
        refs["p3"],
        refs["p4"],
    ]
    assert all(item["source_tree"] == item["clean_tree"] for item in evidence["proofs"])
    assert all(item["source_commit"] for item in evidence["proofs"])
    assert all(item["clean_commit"] for item in evidence["proofs"])
    assert all(item["entry_count"] == len(item["manifest"]) for item in evidence["proofs"])
    assert all(
        set(entry) == {"path", "mode", "type", "object_id"}
        for item in evidence["proofs"]
        for entry in item["manifest"]
    )
    assert all(
        item["manifest"] == sorted(item["manifest"], key=lambda entry: entry["path"])
        for item in evidence["proofs"]
    )
    assert stat.S_IMODE(json_output.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "snapshot",
    ["missing-separator", "::missing ref", "missing-message::"],
)
def test_cli_rejects_malformed_snapshot_without_traceback(
    tmp_path: Path, snapshot: str
) -> None:
    source, _refs = make_source_history(tmp_path)

    result = run_cli(
        "amend",
        "--source",
        str(source),
        "--destination",
        str(tmp_path / "clean"),
        "--snapshot",
        snapshot,
        "--json-output",
        str(tmp_path / "proof.json"),
    )

    assert result.returncode == 2
    assert "Traceback" not in result.stdout + result.stderr


def test_build_cli_rejects_count_other_than_three_before_mutation(
    tmp_path: Path,
) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"

    result = run_cli(
        "build",
        "--source",
        str(source),
        "--destination",
        str(destination),
        "--snapshot",
        f"{refs['p2']}::Sanitized public baseline",
        "--snapshot",
        f"{refs['p3']}::Wheel resources and workspace initialization",
        "--json-output",
        str(tmp_path / "proof.json"),
    )

    assert result.returncode == 2
    assert "exactly three --snapshot arguments" in result.stderr
    assert "Traceback" not in result.stdout + result.stderr
    assert not destination.exists()


def test_build_cli_requires_approved_source_identity_before_mutation(
    tmp_path: Path,
) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    json_output = tmp_path / "proof.json"

    result = run_cli(
        "build",
        "--source",
        str(source),
        "--destination",
        str(destination),
        "--snapshot",
        f"{refs['p2']}::Sanitized public baseline",
        "--snapshot",
        f"{refs['p3']}::Wheel resources and workspace initialization",
        "--snapshot",
        f"{refs['p4']}::Clean public Git lineage",
        "--json-output",
        str(json_output),
    )

    assert result.returncode == 2
    assert "build requires explicit approved source identity" in result.stderr
    assert not destination.exists()
    assert not json_output.exists()


@pytest.mark.parametrize("failure_kind", ["identity", "message", "ancestry"])
def test_build_cli_rejects_wrong_build_contract_before_mutation(
    tmp_path: Path,
    failure_kind: str,
) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    json_output = tmp_path / "proof.json"
    first_ref = refs["p2"]
    first_message = "Sanitized public baseline"
    third_ref = refs["p4"]
    identity_arguments = build_identity_arguments(source, refs)
    if failure_kind == "identity":
        identity_arguments[1] = "0" * 40
    elif failure_kind == "message":
        first_message = "Unapproved baseline message"
    else:
        third_ref = refs["private_root"]

    result = run_cli(
        "build",
        "--source",
        str(source),
        "--destination",
        str(destination),
        "--snapshot",
        f"{first_ref}::{first_message}",
        "--snapshot",
        f"{refs['p3']}::Wheel resources and workspace initialization",
        "--snapshot",
        f"{third_ref}::Clean public Git lineage",
        *identity_arguments,
        "--json-output",
        str(json_output),
    )

    assert result.returncode == 2
    assert "Public lineage reconstruction: ERROR" in result.stderr
    assert not destination.exists()
    assert not json_output.exists()


def test_cli_rejects_json_output_inside_source_before_mutation(
    tmp_path: Path,
) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    original_readme = (source / "README.md").read_bytes()

    result = run_cli(
        "build",
        "--source",
        str(source),
        "--destination",
        str(destination),
        "--snapshot",
        f"{refs['p2']}::Sanitized public baseline",
        "--snapshot",
        f"{refs['p3']}::Wheel resources and workspace initialization",
        "--snapshot",
        f"{refs['p4']}::Clean public Git lineage",
        *build_identity_arguments(source, refs),
        "--json-output",
        str(source / "README.md"),
    )

    assert result.returncode == 2
    assert "outside the source and destination" in result.stderr
    assert (source / "README.md").read_bytes() == original_readme
    assert git(source, "status", "--porcelain=v1").stdout == ""
    assert not destination.exists()


def test_linked_source_rejects_json_output_inside_common_git_directory(
    tmp_path: Path,
) -> None:
    source, refs = make_source_history(tmp_path / "primary-parent")
    linked = tmp_path / "linked-source"
    git(source, "worktree", "add", "--detach", str(linked), refs["p4"])
    destination = tmp_path / "clean"
    json_output = source / ".git" / "proof.json"

    result = run_cli(
        "build",
        "--source",
        str(linked),
        "--destination",
        str(destination),
        "--snapshot",
        f"{refs['p2']}::Sanitized public baseline",
        "--snapshot",
        f"{refs['p3']}::Wheel resources and workspace initialization",
        "--snapshot",
        f"{refs['p4']}::Clean public Git lineage",
        *build_identity_arguments(linked, refs),
        "--json-output",
        str(json_output),
    )

    assert result.returncode == 2
    assert "outside the source" in result.stderr
    assert not destination.exists()
    assert not json_output.exists()


@pytest.mark.parametrize("link_kind", ["hardlink", "symlink"])
def test_cli_rejects_preexisting_json_output_link_before_mutation(
    tmp_path: Path,
    link_kind: str,
) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    destination.mkdir()
    original_readme = (source / "README.md").read_bytes()
    external_target = tmp_path / "external-target.txt"
    external_target.write_bytes(b"external evidence\n")
    json_output = tmp_path / "proof.json"
    if link_kind == "hardlink":
        os.link(source / "README.md", json_output)
        protected_target = source / "README.md"
    else:
        json_output.symlink_to(external_target)
        protected_target = external_target
    original_target = protected_target.read_bytes()

    result = run_cli(
        "build",
        "--source",
        str(source),
        "--destination",
        str(destination),
        "--snapshot",
        f"{refs['p2']}::Sanitized public baseline",
        "--snapshot",
        f"{refs['p3']}::Wheel resources and workspace initialization",
        "--snapshot",
        f"{refs['p4']}::Clean public Git lineage",
        *build_identity_arguments(source, refs),
        "--json-output",
        str(json_output),
    )

    assert result.returncode == 2
    assert "absent, non-symlink" in result.stderr
    assert protected_target.read_bytes() == original_target
    assert (source / "README.md").read_bytes() == original_readme
    assert git(source, "status", "--porcelain=v1").stdout == ""
    assert list(destination.iterdir()) == []


def test_amend_cli_writes_updated_tip_proof(tmp_path: Path) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    build_lineage(
        source,
        destination,
        (
            Snapshot(refs["p2"], "Sanitized public baseline"),
            Snapshot(refs["p3"], "Wheel resources and workspace initialization"),
            Snapshot(refs["p4"], "Clean public Git lineage"),
        ),
    )
    updated_ref = commit_files(
        source,
        "private p4 evidence",
        {"ROADMAP.md": b"clean lineage\nfinal evidence\n"},
    )
    before = git(destination, "rev-list", "--reverse", "main").stdout.splitlines()
    identity = candidate_identity(destination)
    json_output = tmp_path / "proof.json"

    result = run_cli(
        "amend",
        "--source",
        str(source),
        "--destination",
        str(destination),
        "--snapshot",
        f"{updated_ref}::Clean public Git lineage",
        "--expected-tip",
        identity["expected_tip"],
        "--expected-first-tree",
        identity["expected_first_tree"],
        "--expected-second-tree",
        identity["expected_second_tree"],
        *source_snapshot_identity_arguments(source, updated_ref),
        "--json-output",
        str(json_output),
    )

    assert result.returncode == 0
    assert "Public lineage reconstruction: PASS" in result.stdout
    after = git(destination, "rev-list", "--reverse", "main").stdout.splitlines()
    assert after[:2] == before[:2]
    assert after[2] != before[2]
    proof = json.loads(json_output.read_text(encoding="utf-8"))["proofs"][0]
    assert proof["source_ref"] == updated_ref
    assert proof["source_tree"] == proof["clean_tree"]
    assert proof["clean_commit"] == after[2]


def test_amend_cli_rejects_wrong_expected_source_identity_before_mutation(
    tmp_path: Path,
) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    build_lineage(
        source,
        destination,
        (
            Snapshot(refs["p2"], "Sanitized public baseline"),
            Snapshot(refs["p3"], "Wheel resources and workspace initialization"),
            Snapshot(refs["p4"], "Clean public Git lineage"),
        ),
    )
    identity = candidate_identity(destination)
    updated_ref = commit_files(
        source,
        "private update",
        {"ROADMAP.md": b"updated\n"},
    )
    source_identity = source_snapshot_identity_arguments(source, updated_ref)
    source_identity[1] = "0" * 40
    json_output = tmp_path / "proof.json"

    result = run_cli(
        "amend",
        "--source",
        str(source),
        "--destination",
        str(destination),
        "--snapshot",
        f"{updated_ref}::Clean public Git lineage",
        "--expected-tip",
        identity["expected_tip"],
        "--expected-first-tree",
        identity["expected_first_tree"],
        "--expected-second-tree",
        identity["expected_second_tree"],
        *source_identity,
        "--json-output",
        str(json_output),
    )

    assert result.returncode == 2
    assert "expected source identity does not match" in result.stderr
    assert git(destination, "rev-parse", "HEAD").stdout.strip() == identity["expected_tip"]
    assert not json_output.exists()


def test_amend_cli_requires_explicit_candidate_identity(tmp_path: Path) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    build_lineage(
        source,
        destination,
        (
            Snapshot(refs["p2"], "Sanitized public baseline"),
            Snapshot(refs["p3"], "Wheel resources and workspace initialization"),
            Snapshot(refs["p4"], "Clean public Git lineage"),
        ),
    )
    original_tip = git(destination, "rev-parse", "HEAD").stdout.strip()

    result = run_cli(
        "amend",
        "--source",
        str(source),
        "--destination",
        str(destination),
        "--snapshot",
        f"{refs['p4']}::Clean public Git lineage",
        "--json-output",
        str(tmp_path / "proof.json"),
    )

    assert result.returncode == 2
    assert git(destination, "rev-parse", "HEAD").stdout.strip() == original_tip


def test_cli_rejects_missing_proof_parent_before_destination_mutation(
    tmp_path: Path,
) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"

    result = run_cli(
        "build",
        "--source",
        str(source),
        "--destination",
        str(destination),
        "--snapshot",
        f"{refs['p2']}::Sanitized public baseline",
        "--snapshot",
        f"{refs['p3']}::Wheel resources and workspace initialization",
        "--snapshot",
        f"{refs['p4']}::Clean public Git lineage",
        *build_identity_arguments(source, refs),
        "--json-output",
        str(tmp_path / "missing" / "proof.json"),
    )

    assert result.returncode == 2
    assert not destination.exists()


@pytest.mark.parametrize("destination_exists", [False, True])
def test_build_rolls_back_after_post_mutation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    destination_exists: bool,
) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    if destination_exists:
        destination.mkdir()
    real_commit = reconstructor._commit_prepared_snapshot

    def fail_after_commit(*args: object, **kwargs: object):
        real_commit(*args, **kwargs)
        raise LineageError("forced post-mutation failure")

    monkeypatch.setattr(reconstructor, "_commit_prepared_snapshot", fail_after_commit)

    with pytest.raises(LineageError, match="forced post-mutation failure"):
        build_lineage(
            source,
            destination,
            (Snapshot(refs["p2"], "Sanitized public baseline"),),
        )

    if destination_exists:
        assert destination.is_dir()
        assert list(destination.iterdir()) == []
    else:
        assert not destination.exists()


def test_build_does_not_follow_a_replaced_destination_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    displaced = tmp_path / "displaced-clean"
    real_commit = reconstructor._commit_prepared_snapshot
    swapped = False

    def replace_destination_path(*args: object, **kwargs: object):
        nonlocal swapped
        if not swapped:
            swapped = True
            destination.rename(displaced)
            destination.mkdir()
            (destination / "external-marker.txt").write_text(
                "preserve\n",
                encoding="utf-8",
            )
        return real_commit(*args, **kwargs)

    monkeypatch.setattr(
        reconstructor,
        "_commit_prepared_snapshot",
        replace_destination_path,
    )

    with pytest.raises(LineageError, match="destination path changed"):
        build_lineage(
            source,
            destination,
            (Snapshot(refs["p2"], "Sanitized public baseline"),),
        )

    assert (destination / "external-marker.txt").read_text(encoding="utf-8") == (
        "preserve\n"
    )
    assert (displaced / ".git").is_dir()


def test_amend_rolls_back_after_post_mutation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    build_lineage(
        source,
        destination,
        (
            Snapshot(refs["p2"], "Sanitized public baseline"),
            Snapshot(refs["p3"], "Wheel resources and workspace initialization"),
            Snapshot(refs["p4"], "Clean public Git lineage"),
        ),
    )
    identity = candidate_identity(destination)
    original_roadmap = (destination / "ROADMAP.md").read_bytes()
    updated_ref = commit_files(
        source, "private update", {"ROADMAP.md": b"updated\n"}
    )
    real_manifest = reconstructor._tree_manifest

    def fail_clean_manifest(repo: Path, treeish: str):
        if repo.resolve() == destination.resolve():
            raise LineageError("forced manifest failure")
        return real_manifest(repo, treeish)

    monkeypatch.setattr(reconstructor, "_tree_manifest", fail_clean_manifest)

    with pytest.raises(LineageError, match="forced manifest failure"):
        amend_tip(
            source,
            destination,
            Snapshot(updated_ref, "Clean public Git lineage"),
            **identity,
        )

    assert git(destination, "rev-parse", "HEAD").stdout.strip() == identity["expected_tip"]
    assert (destination / "ROADMAP.md").read_bytes() == original_roadmap
    assert git(destination, "status", "--porcelain=v1").stdout == ""


@pytest.mark.parametrize("mode", ["build", "amend"])
def test_proof_write_failure_rolls_back_and_removes_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    arguments = [
        mode,
        "--source",
        str(source),
        "--destination",
        str(destination),
    ]
    original_tip: str | None = None
    if mode == "build":
        for ref, message in (
            (refs["p2"], "Sanitized public baseline"),
            (refs["p3"], "Wheel resources and workspace initialization"),
            (refs["p4"], "Clean public Git lineage"),
        ):
            arguments.extend(["--snapshot", f"{ref}::{message}"])
        arguments.extend(build_identity_arguments(source, refs))
    else:
        build_lineage(
            source,
            destination,
            (
                Snapshot(refs["p2"], "Sanitized public baseline"),
                Snapshot(refs["p3"], "Wheel resources and workspace initialization"),
                Snapshot(refs["p4"], "Clean public Git lineage"),
            ),
        )
        identity = candidate_identity(destination)
        original_tip = identity["expected_tip"]
        updated_ref = commit_files(
            source, "private update", {"ROADMAP.md": b"updated\n"}
        )
        arguments.extend(
            [
                "--snapshot",
                f"{updated_ref}::Clean public Git lineage",
                "--expected-tip",
                identity["expected_tip"],
                "--expected-first-tree",
                identity["expected_first_tree"],
                "--expected-second-tree",
                identity["expected_second_tree"],
                *source_snapshot_identity_arguments(source, updated_ref),
            ]
        )
    proof = tmp_path / "proof.json"
    arguments.extend(["--json-output", str(proof)])

    def fail_write(*_args: object, **_kwargs: object) -> None:
        raise LineageError("forced proof write failure")

    monkeypatch.setattr(reconstructor, "_write_reserved_proofs", fail_write, raising=False)

    result = reconstructor.main(arguments)

    assert result == 2
    assert not proof.exists()
    if mode == "build":
        assert not destination.exists()
    else:
        assert git(destination, "rev-parse", "HEAD").stdout.strip() == original_tip
        assert git(destination, "status", "--porcelain=v1").stdout == ""


def test_amend_rejects_ignored_material_before_mutation(tmp_path: Path) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    build_lineage(
        source,
        destination,
        (
            Snapshot(refs["p2"], "Sanitized public baseline"),
            Snapshot(refs["p3"], "Wheel resources and workspace initialization"),
            Snapshot(refs["p4"], "Clean public Git lineage"),
        ),
    )
    identity = candidate_identity(destination)
    exclude = destination / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_text(
        "ignored.tmp\n", encoding="utf-8"
    )
    (destination / "ignored.tmp").write_text("preserve\n", encoding="utf-8")
    updated_ref = commit_files(
        source, "private update", {"ROADMAP.md": b"updated\n"}
    )

    with pytest.raises(LineageError, match="ignored"):
        amend_tip(
            source,
            destination,
            Snapshot(updated_ref, "Clean public Git lineage"),
            **identity,
        )

    assert (destination / "ignored.tmp").read_text(encoding="utf-8") == "preserve\n"
    assert git(destination, "rev-parse", "HEAD").stdout.strip() == identity["expected_tip"]
