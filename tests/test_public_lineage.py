"""Complete public Git lineage audit boundaries."""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.check_public_lineage as lineage_auditor
from scripts.check_public_lineage import AuditError, audit_repository


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_public_lineage.py"


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def commit_files(repo: Path, files: dict[str, bytes | None]) -> None:
    for relative_path, content in files.items():
        path = repo / relative_path
        if content is None:
            path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "update")


def make_repo(
    tmp_path: Path,
    files: dict[str, bytes],
    *,
    commit_count: int = 3,
) -> Path:
    assert commit_count >= 1
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Azoth Test")
    git(repo, "config", "user.email", "azoth@example.invalid")
    commit_files(repo, files)
    for index in range(1, commit_count):
        git(repo, "commit", "--allow-empty", "-m", f"snapshot {index + 1}")
    return repo


def test_clean_main_only_repository_passes(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"README.md": b"synthetic only\n"})
    report = audit_repository(repo, forbidden_objects=set(), forbidden_text=())
    assert report.findings == ()
    assert report.refs == ("refs/heads/main",)
    assert report.commit_count == 3


def test_ignores_ambient_git_dir_and_audits_requested_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_path = b"/" + b"Users/example/private.bin"
    repo = make_repo(tmp_path / "target", {"payload.bin": private_path})
    decoy = make_repo(tmp_path / "decoy", {"README.md": b"safe\n"})
    monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))

    report = audit_repository(repo, forbidden_objects=set(), forbidden_text=())

    assert any(
        "payload.bin" in item and "absolute user path" in item
        for item in report.findings
    )


def test_ignores_ambient_object_alternates_when_checking_completeness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = make_repo(tmp_path, {"README.md": b"safe\n"})
    external_objects = tmp_path / "external-objects"
    shutil.copytree(repo / ".git" / "objects", external_objects)
    for entry in (repo / ".git" / "objects").iterdir():
        if entry.name == "info":
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    monkeypatch.setenv("GIT_ALTERNATE_OBJECT_DIRECTORIES", str(external_objects))

    with pytest.raises(AuditError):
        audit_repository(repo, forbidden_objects=set(), forbidden_text=())


def test_all_git_subprocesses_receive_sanitized_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = make_repo(tmp_path, {"README.md": b"safe\n"})
    real_run = subprocess.run
    observed_environments: list[dict[str, str] | None] = []
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.abbrev")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "12")

    def recording_run(*args: object, **kwargs: object) -> object:
        observed_environments.append(kwargs.get("env"))
        return real_run(*args, **kwargs)

    monkeypatch.setattr(lineage_auditor.subprocess, "run", recording_run)

    report = audit_repository(repo, forbidden_objects=set(), forbidden_text=())

    assert report.findings == ()
    assert observed_environments
    assert all(
        environment is not None
        and environment.get("GIT_CONFIG_NOSYSTEM") == "1"
        and environment.get("GIT_CONFIG_GLOBAL") == os.devnull
        and not any(
            key.upper().startswith("GIT_")
            and key not in {"GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL"}
            for key in environment
        )
        for environment in observed_environments
    )


def test_rejects_local_fsck_configuration(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"README.md": b"safe\n"})
    git(repo, "config", "fsck.missingEmail", "ignore")

    with pytest.raises(AuditError, match="fsck configuration"):
        audit_repository(repo, forbidden_objects=set(), forbidden_text=())


def test_rejects_worktree_fsck_configuration(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"README.md": b"safe\n"})
    git(repo, "config", "extensions.worktreeConfig", "true")
    git(repo, "config", "--worktree", "fsck.missingEmail", "ignore")

    with pytest.raises(AuditError, match="fsck configuration"):
        audit_repository(repo, forbidden_objects=set(), forbidden_text=())


@pytest.mark.parametrize(
    "state_kind",
    [
        "shallow",
        "alternate",
        "http-alternate",
        "graft",
        "extra-worktree",
        "bare",
        "promisor-config",
        "partial-clone-extension",
        "partial-clone-filter",
        "promisor-state",
    ],
)
def test_rejects_non_standalone_or_incomplete_repository_state(
    tmp_path: Path,
    state_kind: str,
) -> None:
    origin = make_repo(tmp_path / "origin", {"README.md": b"safe\n"})
    repo = origin
    if state_kind == "shallow":
        repo = tmp_path / "shallow"
        subprocess.run(
            ["git", "clone", "--depth=1", f"file://{origin}", str(repo)],
            check=True,
            capture_output=True,
        )
    elif state_kind == "alternate":
        donor = make_repo(tmp_path / "donor", {"README.md": b"donor\n"})
        alternates = repo / ".git" / "objects" / "info" / "alternates"
        alternates.write_text(str(donor / ".git" / "objects") + "\n", encoding="utf-8")
    elif state_kind == "http-alternate":
        (repo / ".git" / "objects" / "info" / "http-alternates").write_text(
            "https://example.invalid/objects\n",
            encoding="ascii",
        )
    elif state_kind == "graft":
        (repo / ".git" / "info" / "grafts").write_text(
            git(repo, "rev-parse", "HEAD").stdout.strip() + "\n",
            encoding="ascii",
        )
    elif state_kind == "extra-worktree":
        git(repo, "worktree", "add", "--detach", str(tmp_path / "linked"), "HEAD")
    elif state_kind == "bare":
        repo = tmp_path / "bare.git"
        subprocess.run(
            ["git", "clone", "--bare", str(origin), str(repo)],
            check=True,
            capture_output=True,
        )
    elif state_kind == "promisor-config":
        git(repo, "config", "remote.origin.promisor", "true")
    elif state_kind == "partial-clone-extension":
        git(repo, "config", "extensions.partialClone", "origin")
    elif state_kind == "partial-clone-filter":
        git(repo, "config", "remote.origin.partialCloneFilter", "blob:none")
    else:
        (repo / ".git" / "objects" / "pack" / "synthetic.promisor").touch()

    with pytest.raises(AuditError):
        audit_repository(repo, forbidden_objects=set(), forbidden_text=())


def test_rejects_linked_worktree_git_file(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"README.md": b"safe\n"})
    linked = tmp_path / "linked"
    git(repo, "worktree", "add", "--detach", str(linked), "HEAD")
    assert (linked / ".git").is_file()

    with pytest.raises(AuditError, match="standalone"):
        audit_repository(linked, forbidden_objects=set(), forbidden_text=())


def test_detached_head_fails(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"README.md": b"safe\n"})
    git(repo, "switch", "--detach")

    report = audit_repository(repo, forbidden_objects=set(), forbidden_text=())

    assert any("HEAD must be refs/heads/main" in item for item in report.findings)


@pytest.mark.parametrize("commit_count", [2, 4])
def test_wrong_commit_count_fails(tmp_path: Path, commit_count: int) -> None:
    repo = make_repo(tmp_path, {"README.md": b"safe\n"}, commit_count=commit_count)

    report = audit_repository(repo, forbidden_objects=set(), forbidden_text=())

    assert any("exactly three commits" in item for item in report.findings)


def test_non_linear_three_commit_history_fails(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"README.md": b"safe\n"})
    commits = git(repo, "rev-list", "--reverse", "main").stdout.splitlines()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    merge_tip = git(
        repo,
        "commit-tree",
        tree,
        "-p",
        commits[1],
        "-p",
        commits[0],
        "-m",
        "non-linear tip",
    ).stdout.strip()
    git(repo, "update-ref", "refs/heads/main", merge_tip, commits[2])

    report = audit_repository(repo, forbidden_objects=set(), forbidden_text=())

    assert report.commit_count == 3
    assert any("strict linear topology" in item for item in report.findings)


@pytest.mark.parametrize(
    ("marker", "detail"),
    [
        ("/" + "Users/example/private", "absolute user path"),
        ("paper_" + "123456", "pilot identifier"),
        ("LLM unavailable; " + "fallback connection", "runtime dump"),
        ("ghp_" + ("A" * 36), "credential pattern"),
        ("-----BEGIN " + "PRIVATE KEY-----", "credential pattern"),
        ("operator-supplied-marker", "forbidden text"),
    ],
)
def test_raw_commit_objects_are_scanned_with_commit_identity(
    tmp_path: Path,
    marker: str,
    detail: str,
) -> None:
    repo = make_repo(tmp_path, {"README.md": b"safe\n"})
    git(repo, "commit", "--amend", "--allow-empty", "-m", marker)
    tip = git(repo, "rev-parse", "HEAD").stdout.strip()
    forbidden_text = (marker.encode(),) if detail == "forbidden text" else ()

    report = audit_repository(repo, forbidden_objects=set(), forbidden_text=forbidden_text)

    assert any(
        f"commit {tip}" in item and detail in item for item in report.findings
    )


@pytest.mark.parametrize(
    ("content", "detail"),
    [
        (b"binary\x00/" + b"Users/example/private", "absolute user path"),
        (b"binary\x00paper_" + b"123456", "pilot identifier"),
        (b"binary\x00LLM unavailable; " + b"fallback connection", "runtime dump"),
        (b"binary\x00ghp_" + (b"A" * 36), "credential pattern"),
        (b"binary\x00operator-supplied-marker", "forbidden text"),
    ],
)
def test_every_historical_blob_is_scanned_regardless_of_suffix(
    tmp_path: Path,
    content: bytes,
    detail: str,
) -> None:
    repo = make_repo(tmp_path, {"removed.payload": content}, commit_count=1)
    commit_files(repo, {"removed.payload": None, "README.md": b"safe\n"})
    git(repo, "commit", "--allow-empty", "-m", "third snapshot")
    forbidden_text = (
        (b"operator-supplied-marker",) if detail == "forbidden text" else ()
    )

    report = audit_repository(repo, forbidden_objects=set(), forbidden_text=forbidden_text)

    assert any(
        "removed.payload" in item and detail in item for item in report.findings
    )


def test_preambled_pdf_signature_fails(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"artifact.bin": b"preamble\n%" + b"PDF-1.7\n"})

    report = audit_repository(repo, forbidden_objects=set(), forbidden_text=())

    assert any(
        "artifact.bin" in item and "PDF signature" in item
        for item in report.findings
    )


def test_pattern_literal_files_still_scan_non_detector_sensitive_content(
    tmp_path: Path,
) -> None:
    literal_payload = (
        b"/" + b"Users/example/private\n"
        b"paper_" + b"123456\n"
        b"LLM unavailable; " + b"fallback connection\n"
        b"ghp_" + (b"A" * 36) + b"\noperator-supplied-marker\n"
        b"%" + b"PDF-1.7\n"
    )
    repo = make_repo(
        tmp_path,
        {
            "scripts/check_public_tree.py": literal_payload,
            "tests/test_public_tree.py": literal_payload,
        },
    )

    report = audit_repository(
        repo,
        forbidden_objects=set(),
        forbidden_text=(b"operator-supplied-marker",),
    )

    assert any("credential pattern" in item for item in report.findings)
    assert any("forbidden text" in item for item in report.findings)
    assert any("PDF signature" in item for item in report.findings)
    assert any("absolute user path" in item for item in report.findings)
    assert any("pilot identifier" in item for item in report.findings)
    assert any("runtime dump" in item for item in report.findings)


@pytest.mark.parametrize(
    "path",
    [
        "docs/superpowers/plans/2026-07-11-p2-public-baseline.md",
        "scripts/check_connect_pruning.py",
        "scripts/check_public_tree.py",
        "tests/test_public_tree.py",
    ],
)
def test_exact_reviewed_fixture_blobs_do_not_self_trigger(
    tmp_path: Path,
    path: str,
) -> None:
    content = subprocess.run(
        ["git", "show", f"HEAD:{path}"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    repo = make_repo(tmp_path, {path: content})

    report = audit_repository(repo, forbidden_objects=set(), forbidden_text=())

    assert report.findings == ()


def test_pdf_signature_without_line_boundary_fails(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {"artifact.bin": b"polyglot-prefix%" + b"PDF-1.7\n"},
    )

    report = audit_repository(repo, forbidden_objects=set(), forbidden_text=())

    assert any("artifact.bin" in item and "PDF signature" in item for item in report.findings)


def test_detector_regex_definition_does_not_look_like_a_private_path(
    tmp_path: Path,
) -> None:
    regex_definition = (
        b're.compile(rb"/' + b'Users/[^\\s`\\\"\\\']+")\n'
    )
    repo = make_repo(
        tmp_path,
        {"scripts/check_public_tree.py": regex_definition},
    )

    report = audit_repository(repo, forbidden_objects=set(), forbidden_text=())

    assert not any("absolute user path" in item for item in report.findings)


def test_sensitive_filename_components_are_scanned(tmp_path: Path) -> None:
    private_name = "notes/" + "paper_" + "123456.txt"
    repo = make_repo(tmp_path, {private_name: b"safe content\n"})

    report = audit_repository(repo, forbidden_objects=set(), forbidden_text=())

    assert any(private_name in item and "pilot identifier" in item for item in report.findings)


@pytest.mark.parametrize("storage_name", ["pack", "info"])
def test_rejects_symlinked_internal_git_storage(
    tmp_path: Path,
    storage_name: str,
) -> None:
    repo = make_repo(tmp_path, {"README.md": b"safe\n"})
    if storage_name == "pack":
        storage = repo / ".git" / "objects" / "pack"
        external = tmp_path / "external-pack"
        external.mkdir()
        storage.rmdir()
        storage.symlink_to(external, target_is_directory=True)
    else:
        storage = repo / ".git" / "info" / "exclude"
        external = tmp_path / "external-info"
        external.write_bytes(storage.read_bytes())
        storage.unlink()
        storage.symlink_to(external)

    with pytest.raises(AuditError, match="internal Git storage"):
        audit_repository(repo, forbidden_objects=set(), forbidden_text=())


def test_ref_update_during_audit_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = make_repo(tmp_path, {"README.md": b"safe\n"})
    real_run = lineage_auditor.run_git
    updated = False

    def racing_run(
        audit_repo: Path,
        *args: str,
        input_bytes: bytes | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        nonlocal updated
        result = real_run(audit_repo, *args, input_bytes=input_bytes)
        if not updated and "rev-list" in args:
            updated = True
            subprocess.run(
                ["git", "commit", "--allow-empty", "-m", "concurrent update"],
                cwd=audit_repo,
                check=True,
                capture_output=True,
            )
        return result

    monkeypatch.setattr(lineage_auditor, "run_git", racing_run)

    with pytest.raises(AuditError, match="refs changed"):
        audit_repository(repo, forbidden_objects=set(), forbidden_text=())


def test_symbolic_head_update_during_audit_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = make_repo(tmp_path, {"README.md": b"safe\n"})
    real_run = lineage_auditor.run_git
    updated = False

    def racing_run(
        audit_repo: Path,
        *args: str,
        input_bytes: bytes | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        nonlocal updated
        result = real_run(audit_repo, *args, input_bytes=input_bytes)
        if not updated and "rev-list" in args:
            updated = True
            subprocess.run(
                ["git", "switch", "--detach"],
                cwd=audit_repo,
                check=True,
                capture_output=True,
            )
        return result

    monkeypatch.setattr(lineage_auditor, "run_git", racing_run)

    with pytest.raises(AuditError, match="HEAD changed"):
        audit_repository(repo, forbidden_objects=set(), forbidden_text=())


def test_extra_branch_and_tag_fail(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"README.md": b"ok\n"})
    git(repo, "branch", "legacy")
    git(repo, "tag", "v0.1.3")
    report = audit_repository(repo, forbidden_objects=set(), forbidden_text=())
    assert any("unexpected ref: refs/heads/legacy" in item for item in report.findings)
    assert any("unexpected ref: refs/tags/v0.1.3" in item for item in report.findings)


def test_historical_pdf_private_path_lfs_gitlink_and_secret_fail(
    tmp_path: Path,
) -> None:
    private_path = b"/" + b"Users/example/private.pdf"
    repo = make_repo(
        tmp_path,
        {
            "removed.bin": b"%" + b"PDF-1.7\nprivate pilot\n",
            "removed.txt": private_path,
        },
    )
    commit_files(repo, {"removed.bin": None, "removed.txt": None, "safe.txt": b"safe\n"})
    token = b"ghp_" + (b"A" * 36)
    lfs = (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:" + (b"0" * 64) + b"\nsize 1\n"
    )
    commit_files(repo, {"token.txt": token, "asset.dat": lfs})

    nested = make_repo(tmp_path / "nested-parent", {"nested.txt": b"safe\n"})
    git(
        repo,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        str(nested),
        "vendor/nested",
    )
    git(repo, "commit", "-m", "add gitlink")

    report = audit_repository(repo, forbidden_objects=set(), forbidden_text=())
    assert any(
        "PDF signature" in item and "removed.bin" in item for item in report.findings
    )
    assert any(
        "absolute user path" in item and "removed.txt" in item
        for item in report.findings
    )
    assert any("LFS pointer" in item and "asset.dat" in item for item in report.findings)
    assert any("gitlink" in item and "vendor/nested" in item for item in report.findings)
    assert any(
        "credential pattern" in item and "token.txt" in item
        for item in report.findings
    )


def test_forbidden_object_and_text_fail(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"safe.txt": b"private-marker\n"})
    blob = git(repo, "rev-parse", "HEAD:safe.txt").stdout.strip()
    report = audit_repository(
        repo,
        forbidden_objects={blob},
        forbidden_text=(b"private-marker",),
    )
    assert any(
        f"forbidden reachable object: {blob}" in item for item in report.findings
    )
    assert any("forbidden text" in item for item in report.findings)


def test_content_finding_handles_colon_in_path(tmp_path: Path) -> None:
    private_path = b"/" + b"Users/example/private.txt"
    repo = make_repo(tmp_path, {"notes:private.txt": private_path})

    report = audit_repository(repo, forbidden_objects=set(), forbidden_text=())

    assert any(
        "notes:private.txt" in item and "absolute user path" in item
        for item in report.findings
    )


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def expected_tip_args(repo: Path) -> tuple[str, str]:
    return "--expected-tip", git(repo, "rev-parse", "main").stdout.strip()


def test_cli_writes_json_evidence_for_clean_lineage(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"README.md": b"synthetic only\n"})
    json_output = tmp_path / "audit.json"

    tip = git(repo, "rev-parse", "main").stdout.strip()
    result = run_cli(
        "--repo",
        str(repo),
        "--expected-tip",
        tip,
        "--json-output",
        str(json_output),
    )

    assert result.returncode == 0
    assert "Public lineage audit: PASS" in result.stdout
    assert "commits=3" in result.stdout
    evidence = json.loads(json_output.read_text(encoding="utf-8"))
    assert evidence["refs"] == ["refs/heads/main"]
    assert evidence["commit_count"] == 3
    assert evidence["findings"] == []
    assert evidence["main_commit"] == tip
    assert evidence["main_tree"] == git(repo, "rev-parse", "main^{tree}").stdout.strip()
    assert evidence["forbidden_object_count"] == 0
    assert evidence["forbidden_text_count"] == 0
    assert len(evidence["forbidden_object_digest"]) == 64
    assert len(evidence["forbidden_text_digest"]) == 64
    assert evidence["expected_tip"] == tip
    assert not Path(evidence["repo"]).is_absolute()
    assert str(repo) not in json_output.read_text(encoding="utf-8")
    assert stat.S_IMODE(json_output.stat().st_mode) == 0o600


def test_expected_tip_mismatch_is_a_finding_and_is_recorded(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"README.md": b"safe\n"})
    expected_tip = "0" * 40

    report = audit_repository(
        repo,
        forbidden_objects=set(),
        forbidden_text=(),
        expected_tip=expected_tip,
    )

    assert report.expected_tip == expected_tip
    assert any("main tip does not match expected tip" in item for item in report.findings)


def test_malformed_expected_tip_is_rejected(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"README.md": b"safe\n"})

    with pytest.raises(AuditError, match="expected tip"):
        audit_repository(
            repo,
            forbidden_objects=set(),
            forbidden_text=(),
            expected_tip="not-an-object-id",
        )


def test_nonempty_policy_counts_and_digests_are_exact(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"README.md": b"safe\n"})
    objects = {"f" * 40, "0" * 40}
    markers = (b"alpha", b"beta\x00gamma")
    expected_object_payload = b"0" * 40 + b"\n" + b"f" * 40 + b"\n"
    expected_text_hasher = hashlib.sha256()
    for marker in markers:
        expected_text_hasher.update(len(marker).to_bytes(8, "big"))
        expected_text_hasher.update(marker)

    report = audit_repository(repo, objects, markers)

    assert report.forbidden_object_count == 2
    assert report.forbidden_object_digest == hashlib.sha256(
        expected_object_payload
    ).hexdigest()
    assert report.forbidden_text_count == 2
    assert report.forbidden_text_digest == expected_text_hasher.hexdigest()


def test_cli_rejects_existing_json_output_without_overwrite(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "source", {"README.md": b"synthetic only\n"})
    json_output = tmp_path / "audit.json"
    json_output.write_bytes(b"preserve me\n")

    result = run_cli(
        "--repo",
        str(repo),
        *expected_tip_args(repo),
        "--json-output",
        str(json_output),
    )

    assert result.returncode == 2
    assert json_output.read_bytes() == b"preserve me\n"


@pytest.mark.parametrize("link_kind", ["hardlink", "symlink"])
def test_cli_rejects_linked_json_output_without_touching_target(
    tmp_path: Path,
    link_kind: str,
) -> None:
    repo = make_repo(tmp_path / "source", {"README.md": b"synthetic only\n"})
    protected = tmp_path / "protected.txt"
    protected.write_bytes(b"preserve me\n")
    json_output = tmp_path / "audit.json"
    if link_kind == "hardlink":
        os.link(protected, json_output)
    else:
        json_output.symlink_to(protected)

    result = run_cli(
        "--repo",
        str(repo),
        *expected_tip_args(repo),
        "--json-output",
        str(json_output),
    )

    assert result.returncode == 2
    assert protected.read_bytes() == b"preserve me\n"


def test_cli_rejects_json_output_inside_audited_repository(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path, {"README.md": b"synthetic only\n"})
    json_output = repo / "audit.json"

    result = run_cli(
        "--repo",
        str(repo),
        *expected_tip_args(repo),
        "--json-output",
        str(json_output),
    )

    assert result.returncode == 2
    assert not json_output.exists()
    assert git(repo, "status", "--porcelain=v1").stdout == ""


def test_cli_rejects_output_parent_symlinked_into_repository(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path / "source", {"README.md": b"synthetic only\n"})
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(repo, target_is_directory=True)
    json_output = linked_parent / "audit.json"

    result = run_cli(
        "--repo",
        str(repo),
        *expected_tip_args(repo),
        "--json-output",
        str(json_output),
    )

    assert result.returncode == 2
    assert not (repo / "audit.json").exists()


def test_json_publication_failure_leaves_no_partial_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = make_repo(tmp_path / "source", {"README.md": b"synthetic only\n"})
    json_output = tmp_path / "audit.json"

    def fail_link(*_args: object, **_kwargs: object) -> None:
        raise OSError("forced publication failure")

    monkeypatch.setattr(os, "link", fail_link)

    result = lineage_auditor.main(
        [
            "--repo",
            str(repo),
            *expected_tip_args(repo),
            "--json-output",
            str(json_output),
        ]
    )

    assert result == 2
    assert not json_output.exists()
    assert not tuple(tmp_path.glob(".audit.json.*.tmp"))


def test_cli_reports_findings_and_returns_one(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"safe.txt": b"private-marker\n"})
    blob = git(repo, "rev-parse", "HEAD:safe.txt").stdout.strip()
    object_file = tmp_path / "forbidden-objects.txt"
    text_file = tmp_path / "forbidden-text.txt"
    object_file.write_text(f"{blob}\n", encoding="ascii")
    text_file.write_bytes(b"private-marker\n")

    result = run_cli(
        "--repo",
        str(repo),
        *expected_tip_args(repo),
        "--forbidden-object-file",
        str(object_file),
        "--forbidden-text-file",
        str(text_file),
    )

    assert result.returncode == 1
    assert "Public lineage audit: FAIL" in result.stdout
    assert f"forbidden reachable object: {blob}" in result.stdout
    assert "forbidden text" in result.stdout


def test_cli_missing_input_file_returns_two_without_traceback(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"README.md": b"ok\n"})

    result = run_cli(
        "--repo",
        str(repo),
        *expected_tip_args(repo),
        "--forbidden-object-file",
        str(tmp_path / "missing.txt"),
    )

    assert result.returncode == 2
    assert "Traceback" not in result.stdout + result.stderr


def test_cli_malformed_object_file_returns_two_without_traceback(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"README.md": b"ok\n"})
    malformed = tmp_path / "malformed.txt"
    malformed.write_text("not-an-object-id\n", encoding="ascii")

    result = run_cli(
        "--repo",
        str(repo),
        *expected_tip_args(repo),
        "--forbidden-object-file",
        str(malformed),
    )

    assert result.returncode == 2
    assert "Traceback" not in result.stdout + result.stderr


def test_cli_non_git_path_returns_two_without_traceback(tmp_path: Path) -> None:
    result = run_cli("--repo", str(tmp_path), "--expected-tip", "0" * 40)

    assert result.returncode == 2
    assert "Traceback" not in result.stdout + result.stderr
