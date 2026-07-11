"""Session lifecycle commands must keep handoff authority and Git staging explicit."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from athanasor.session import commands


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )


def _configure_root(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    lapis = root / "athanasor" / "lapis"
    monkeypatch.setattr(commands, "ROOT", root)
    monkeypatch.setattr(commands, "STATE_PATH", lapis / "state.json")
    monkeypatch.setattr(commands, "CODEX_PATH", lapis / "codex.md")
    monkeypatch.setattr(commands, "ROADMAP_PATH", root / "PROJECT_ROADMAP.md", raising=False)
    monkeypatch.setattr(commands, "REGISTRY_PATH", root / "albedo" / "registry.jsonl")
    monkeypatch.setattr(commands, "NIGREDO_ROOT", root / "nigredo")
    monkeypatch.setattr(commands, "ALBEDO_ROOT", root / "albedo")
    monkeypatch.setattr(commands, "CITRINITAS_ROOT", root / "citrinitas")
    monkeypatch.setattr(commands, "RUBEDO_ROOT", root / "rubedo")
    monkeypatch.setattr(commands, "LAPIS_ROOT", lapis)
    monkeypatch.setattr(
        commands,
        "MEMORY_CANDIDATES",
        (
            lapis / "memory.jsonl",
            lapis / "memory.json",
            lapis / "knowledge_graph.json",
            lapis / "knowledge_graph.jsonl",
        ),
    )


def _session_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    vigil_exit: int = 0,
    vigil_body: str | None = None,
) -> Path:
    root = tmp_path / "repo"
    (root / "athanasor" / "lapis").mkdir(parents=True)
    (root / "athanasor" / "vigil").mkdir(parents=True)
    (root / "athanasor" / "lapis" / "state.json").write_text(
        json.dumps({"sessions": {"total": 0}}), encoding="utf-8"
    )
    (root / "athanasor" / "lapis" / "codex.md").write_text(
        "See PROJECT_ROADMAP.md\n", encoding="utf-8"
    )
    (root / "PROJECT_ROADMAP.md").write_text(
        "# Roadmap\n\n| Task | P0-T1 |\n\n**Next task:** P1-T1\n", encoding="utf-8"
    )
    (root / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    (root / ".gitignore").write_text(
        "athanasor/lapis/memory.jsonl\nathanasor/vigil/reports/\n", encoding="utf-8"
    )
    (root / "athanasor" / "vigil" / "verify.py").write_text(
        vigil_body or ("import sys\n" f"raise SystemExit({vigil_exit})\n"),
        encoding="utf-8",
    )
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test User")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "baseline")
    _configure_root(monkeypatch, root)
    return root


def test_roadmap_summary_reads_active_and_next_task(tmp_path: Path) -> None:
    roadmap = tmp_path / "PROJECT_ROADMAP.md"
    roadmap.write_text(
        "# Roadmap\n\n| Task | P0-T1 — Safe close |\n| Status | in progress |\n\n"
        "**Next task:** P1-T1 — Archive pilot.  \n",
        encoding="utf-8",
    )

    summary = commands.roadmap_summary(roadmap)

    assert summary == {
        "path": str(roadmap),
        "status": "available",
        "active_task": "P0-T1 — Safe close",
        "active_status": "in progress",
        "next_task": "P1-T1 — Archive pilot.",
        "error": None,
    }


@pytest.mark.parametrize(
    ("body", "count"),
    [
        ("# Roadmap\n", 0),
        (
            "**Next task:** P1-T1\n\n**Next task:** P2-T1\n",
            2,
        ),
    ],
)
def test_roadmap_summary_rejects_missing_or_duplicate_next_task(
    tmp_path: Path, body: str, count: int
) -> None:
    roadmap = tmp_path / "PROJECT_ROADMAP.md"
    roadmap.write_text(body, encoding="utf-8")

    summary = commands.roadmap_summary(roadmap)

    assert summary["status"] == "invalid"
    assert summary["next_task"] is None
    assert summary["error"] == f"expected exactly one next-task marker; found {count}"


def test_incipere_renders_canonical_roadmap_tasks(capsys: pytest.CaptureFixture[str]) -> None:
    snapshot = {
        "timestamp": "2026-07-11T00:00:00+00:00",
        "worktree": {
            "inside_worktree": True,
            "branch": "main",
            "commit": "abc",
            "status": "clean",
            "pending_changes": [],
        },
        "pipeline": {
            "registry_total": 0,
            "registry_status_counts": {},
            "library_records": 0,
            "exhaust_records": 0,
            "connections": 0,
            "hypotheses": 0,
            "drafts": 0,
            "nigredo_inbox_items": 0,
            "nigredo_domain_queue": 0,
        },
        "knowledge_graph": {
            "path": None,
            "status": "missing",
            "nodes": 0,
            "edges": 0,
            "notes": "none",
        },
        "roadmap": {
            "path": "PROJECT_ROADMAP.md",
            "status": "available",
            "active_task": "P0-T1 — Safe close",
            "active_status": "in progress",
            "next_task": "P1-T1 — Archive pilot",
        },
    }

    assert commands.render_incipere(snapshot) == 0
    output = capsys.readouterr().out
    assert "PROJECT_ROADMAP.md" in output
    assert "P0-T1 — Safe close" in output
    assert "in progress" in output
    assert "P1-T1 — Archive pilot" in output


def test_recommendations_defer_to_canonical_next_task() -> None:
    snapshot = {
        "roadmap": {
            "status": "available",
            "next_task": "P1-T1 — Archive pilot",
        },
        "pipeline": {
            "registry_total": 57,
            "registry_status_counts": {"ingested_only": 3},
            "registry_domain_counts": {"ML": 19},
            "nigredo_inbox_items": 0,
            "connections": 76,
            "hypotheses": 2,
        },
        "worktree": {"inside_worktree": True},
        "knowledge_graph": {"status": "missing"},
    }

    assert commands.recommendations(snapshot) == [
        "Resume canonical roadmap task: P1-T1 — Archive pilot"
    ]


def test_recommendations_keep_in_progress_task_ahead_of_next_task() -> None:
    snapshot = {
        "roadmap": {
            "status": "available",
            "active_task": "P0-T1 — Safe close",
            "active_status": "in progress",
            "next_task": "P1-T1 — Archive pilot",
        }
    }

    assert commands.recommendations(snapshot) == [
        "Resume canonical active task: P0-T1 — Safe close"
    ]


def test_recommendations_stop_when_canonical_roadmap_is_missing() -> None:
    snapshot = {
        "roadmap": {
            "status": "missing",
            "error": "canonical roadmap is missing",
        },
        "pipeline": {
            "registry_total": 57,
            "registry_status_counts": {"ingested_only": 3},
            "registry_domain_counts": {"ML": 19},
            "nigredo_inbox_items": 1,
            "connections": 76,
            "hypotheses": 2,
        },
        "worktree": {"inside_worktree": True},
        "knowledge_graph": {"status": "missing"},
    }

    assert commands.recommendations(snapshot) == [
        "Repair canonical roadmap before project work: canonical roadmap is missing"
    ]


@pytest.mark.parametrize("candidate", ["../outside.txt", "/tmp/outside.txt", "a/../../outside"])
def test_validate_stage_paths_rejects_external_or_traversal_paths(
    tmp_path: Path, candidate: str
) -> None:
    with pytest.raises(ValueError, match="repository-relative"):
        commands.validate_stage_paths(tmp_path, [candidate])


def test_validate_stage_paths_accepts_existing_repo_relative_path(tmp_path: Path) -> None:
    state = tmp_path / "athanasor" / "lapis" / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text("{}\n", encoding="utf-8")

    assert commands.validate_stage_paths(
        tmp_path, ["athanasor/lapis/state.json"]
    ) == [state.resolve()]


def test_concludere_no_commit_only_writes_ignored_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _session_repo(tmp_path, monkeypatch)
    before = (root / "athanasor" / "lapis" / "state.json").read_bytes()

    assert commands.run_concludere(["--no-commit", "-f", "checkpoint"]) == 0

    assert (root / "athanasor" / "lapis" / "state.json").read_bytes() == before
    assert (root / "athanasor" / "lapis" / "memory.jsonl").exists()
    assert _git(root, "status", "--short").stdout == ""


def test_concludere_no_commit_rejects_tracked_memory_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _session_repo(tmp_path, monkeypatch)
    roadmap = root / "PROJECT_ROADMAP.md"
    before = roadmap.read_bytes()

    result = commands.run_concludere(
        ["--no-commit", "--memory-db", "PROJECT_ROADMAP.md", "-f", "checkpoint"]
    )

    assert result == 1
    assert roadmap.read_bytes() == before
    assert _git(root, "status", "--short").stdout == ""


def test_concludere_no_commit_rejects_external_memory_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _session_repo(tmp_path, monkeypatch)
    outside = root.parent / "outside.jsonl"

    result = commands.run_concludere(
        ["--no-commit", "--memory-db", "../outside.jsonl", "-f", "checkpoint"]
    )

    assert result == 1
    assert not outside.exists()


def test_concludere_refuses_prestaged_index_before_persisting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _session_repo(tmp_path, monkeypatch)
    (root / "tracked.txt").write_text("staged\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")

    result = commands.run_concludere(
        ["--stage", "athanasor/lapis/state.json", "-m", "close"]
    )

    assert result == 1
    assert not (root / "athanasor" / "lapis" / "memory.jsonl").exists()
    assert _git(root, "diff", "--cached", "--name-only").stdout.strip() == "tracked.txt"


def test_concludere_refuses_dirty_tracked_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _session_repo(tmp_path, monkeypatch)
    (root / "tracked.txt").write_text("dirty\n", encoding="utf-8")

    result = commands.run_concludere(
        ["--stage", "athanasor/lapis/state.json", "-m", "close"]
    )

    assert result == 1
    assert not (root / "athanasor" / "lapis" / "memory.jsonl").exists()
    assert _git(root, "diff", "--name-only").stdout.strip() == "tracked.txt"


def test_concludere_runs_vigil_then_commits_only_explicit_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _session_repo(tmp_path, monkeypatch)
    (root / "unrelated.tmp").write_text("do not stage\n", encoding="utf-8")

    result = commands.run_concludere(
        [
            "--stage",
            "athanasor/lapis/state.json",
            "-f",
            "verified close",
            "-m",
            "close session",
        ]
    )

    assert result == 0
    committed = _git(root, "show", "--format=", "--name-only", "HEAD").stdout.splitlines()
    assert committed == ["athanasor/lapis/state.json"]
    assert (root / "unrelated.tmp").exists()
    assert _git(root, "diff", "--name-only").stdout == ""
    assert _git(root, "diff", "--cached", "--name-only").stdout == ""


def test_concludere_rolls_back_stage_paths_when_vigil_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _session_repo(tmp_path, monkeypatch, vigil_exit=1)
    state = root / "athanasor" / "lapis" / "state.json"
    before = state.read_bytes()
    head = _git(root, "rev-parse", "HEAD").stdout.strip()

    result = commands.run_concludere(
        ["--stage", "athanasor/lapis/state.json", "-m", "close"]
    )

    assert result == 1
    assert state.read_bytes() == before
    assert _git(root, "rev-parse", "HEAD").stdout.strip() == head
    assert _git(root, "diff", "--name-only").stdout == ""
    assert _git(root, "diff", "--cached", "--name-only").stdout == ""


def test_concludere_refuses_and_rolls_back_vigil_staged_outside_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _session_repo(
        tmp_path,
        monkeypatch,
        vigil_body=(
            "from pathlib import Path\n"
            "import subprocess\n"
            "Path('tracked.txt').write_text('vigil staged\\n', encoding='utf-8')\n"
            "subprocess.run(['git', 'add', 'tracked.txt'], check=True)\n"
        ),
    )
    head = _git(root, "rev-parse", "HEAD").stdout.strip()

    result = commands.run_concludere(
        ["--stage", "athanasor/lapis/state.json", "-m", "close"]
    )

    assert result == 1
    assert (root / "tracked.txt").read_text(encoding="utf-8") == "baseline\n"
    assert _git(root, "rev-parse", "HEAD").stdout.strip() == head
    assert _git(root, "diff", "--name-only").stdout == ""
    assert _git(root, "diff", "--cached", "--name-only").stdout == ""


def test_concludere_rolls_back_vigil_unstaged_outside_allowlist_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _session_repo(
        tmp_path,
        monkeypatch,
        vigil_body=(
            "from pathlib import Path\n"
            "Path('tracked.txt').write_text('vigil dirty\\n', encoding='utf-8')\n"
            "raise SystemExit(1)\n"
        ),
    )

    result = commands.run_concludere(
        ["--stage", "athanasor/lapis/state.json", "-m", "close"]
    )

    assert result == 1
    assert (root / "tracked.txt").read_text(encoding="utf-8") == "baseline\n"
    assert _git(root, "diff", "--name-only").stdout == ""
    assert _git(root, "diff", "--cached", "--name-only").stdout == ""
