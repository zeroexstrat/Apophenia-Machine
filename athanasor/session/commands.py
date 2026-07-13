#!/usr/bin/env python3
"""Session lifecycle commands for Azoth.

`/incipere`:
  - ensures a git worktree exists,
  - reads git and persistent state,
  - reads the canonical project roadmap,
  - prints where the project is and the recorded active/next task.

`/concludere`:
  - stores session findings in ignored persistent memory,
  - runs Vigil close before staging,
  - updates Lapis state,
  - commits only an explicit repository-relative staging allowlist.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from ..workspace import discover_workspace
from .durability import assert_durable_worktree

ROOT = discover_workspace()
STATE_PATH = ROOT / "athanasor" / "lapis" / "state.json"
CODEX_PATH = ROOT / "athanasor" / "lapis" / "codex.md"
ROADMAP_PATH = ROOT / "PROJECT_ROADMAP.md"
REGISTRY_PATH = ROOT / "albedo" / "registry.jsonl"
NIGREDO_ROOT = ROOT / "nigredo"
ALBEDO_ROOT = ROOT / "albedo"
CITRINITAS_ROOT = ROOT / "citrinitas"
RUBEDO_ROOT = ROOT / "rubedo"
LAPIS_ROOT = ROOT / "athanasor" / "lapis"

MEMORY_CANDIDATES = (
    LAPIS_ROOT / "memory.jsonl",
    LAPIS_ROOT / "memory.json",
    LAPIS_ROOT / "knowledge_graph.json",
    LAPIS_ROOT / "knowledge_graph.jsonl",
)


def run_cmd(
    cmd: list[str],
    *,
    cwd: Path,
    check: bool = False,
    env: dict[str, str] | None = None,
    context: str | None = None,
) -> subprocess.CompletedProcess[str]:
    if not cmd:
        raise RuntimeError(f"{context or 'command'}: empty command invocation")

    context = context or f"{cmd[0]} {' '.join(cmd[1:])}".strip()
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"{context}: command not found ({cmd[0]}): {exc}") from exc
    except OSError as exc:
        raise RuntimeError(f"{context}: failed to run command ({cmd[0]}): {exc}") from exc

    if check and result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            f"{context}: exit code {result.returncode}" + (f" ({output})" if output else "")
        )

    return result


def is_git_worktree(path: Path) -> bool:
    result = run_cmd(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=path,
        context="git rev-parse --is-inside-work-tree",
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def ensure_git_worktree(path: Path) -> list[str]:
    messages: list[str] = []
    if is_git_worktree(path):
        messages.append(f"Detected git worktree at {path}")
        return messages

    run_cmd(["git", "init"], cwd=path, context="git init", check=True)

    messages.append(f"Initialized git worktree at {path} (no remote configured).")
    return messages


def git_state(path: Path) -> dict[str, Any]:
    if not is_git_worktree(path):
        return {
            "inside_worktree": False,
            "branch": None,
            "commit": None,
            "status": None,
        }

    branch_res = run_cmd(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=path,
        context="git rev-parse --abbrev-ref HEAD",
        check=True,
    )
    commit_res = run_cmd(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        context="git rev-parse HEAD",
        check=True,
    )
    status_res = run_cmd(
        ["git", "status", "--short"],
        cwd=path,
        context="git status --short",
        check=True,
    )
    remote_res = run_cmd(["git", "remote"], cwd=path, context="git remote", check=True)

    status = status_res.stdout.strip()
    return {
        "inside_worktree": True,
        "branch": branch_res.stdout.strip() or None,
        "commit": commit_res.stdout.strip() or None,
        "status": "clean" if status == "" else "dirty",
        "pending_changes": status.splitlines(),
        "remotes": remote_res.stdout.strip().splitlines(),
    }


def safe_load_json(path: Path) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def roadmap_summary(path: Path = ROADMAP_PATH) -> dict[str, Any]:
    """Read the canonical roadmap's active and next task without mutating it."""
    if not path.exists():
        return {
            "path": str(path),
            "status": "missing",
            "active_task": None,
            "active_status": None,
            "next_task": None,
            "error": "canonical roadmap is missing",
        }

    active_task: str | None = None
    active_status: str | None = None
    next_tasks: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if active_task is None and line.startswith("| Task |"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) >= 2 and cells[0] == "Task" and cells[1] != "Value":
                active_task = cells[1]
        if active_status is None and line.startswith("| Status |"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) >= 2 and cells[0] == "Status" and cells[1] != "Value":
                active_status = cells[1]
        match = re.match(r"^\*\*Next task:\*\*\s*(.+?)\s*$", line)
        if match:
            next_tasks.append(match.group(1).strip())

    if len(next_tasks) != 1:
        return {
            "path": str(path),
            "status": "invalid",
            "active_task": active_task,
            "active_status": active_status,
            "next_task": None,
            "error": f"expected exactly one next-task marker; found {len(next_tasks)}",
        }

    return {
        "path": str(path),
        "status": "available",
        "active_task": active_task,
        "active_status": active_status,
        "next_task": next_tasks[0],
        "error": None,
    }


def count_files(path: Path, suffixes: tuple[str, ...]) -> int:
    if not path.exists():
        return 0
    total = 0
    for suffix in suffixes:
        total += len(list(path.rglob(f"*{suffix}")))
    return total


def read_jsonl_lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                lines.append(payload)
    return lines


def registry_snapshot() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {
            "total": 0,
            "status_counts": {},
            "domain_counts": {},
            "entries": [],
        }

    entries: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    domain_counts: Counter[str] = Counter()

    for payload in read_jsonl_lines(REGISTRY_PATH):
        status = payload.get("status", "unknown")
        domain = payload.get("domain", "unknown")
        status_counts[status] += 1
        domain_counts[domain] += 1
        entries.append(payload)

    return {
        "total": len(entries),
        "status_counts": dict(status_counts),
        "domain_counts": dict(domain_counts),
        "entries": entries,
    }


def _count_connection_files() -> int:
    count = 0
    paths = (
        CITRINITAS_ROOT / "within_domain",
        CITRINITAS_ROOT / "cross_domain",
    )
    for base in paths:
        if not base.exists():
            continue
        count += len(list(base.rglob("*.yaml")))
        count += len(list(base.rglob("*.yml")))
    return count


def _count_yaml(path: Path) -> int:
    if not path.exists():
        return 0
    return len(list(path.rglob("*.yaml"))) + len(list(path.rglob("*.yml")))


def detect_knowledge_db() -> Path | None:
    for candidate in MEMORY_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def knowledge_db_summary(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "path": None,
            "status": "missing",
            "nodes": 0,
            "edges": 0,
            "notes": "No memory/knowledge graph file found yet.",
        }

    if path.suffix == ".jsonl":
        lines = read_jsonl_lines(path)
        return {
            "path": str(path.relative_to(ROOT)),
            "status": "available",
            "nodes": len(lines),
            "edges": 0,
            "notes": "Tracked as JSONL append-only entries.",
        }

    payload = safe_load_json(path)
    if payload is None:
        return {
            "path": str(path.relative_to(ROOT)),
            "status": "invalid",
            "nodes": 0,
            "edges": 0,
            "notes": "Failed to parse JSON memory file.",
        }

    if isinstance(payload, list):
        return {
            "path": str(path.relative_to(ROOT)),
            "status": "available",
            "nodes": len(payload),
            "edges": 0,
            "notes": "Tracked as JSON list entries.",
        }

    nodes = payload.get("nodes")
    edges = payload.get("edges")
    if isinstance(nodes, list) and isinstance(edges, list):
        return {
            "path": str(path.relative_to(ROOT)),
            "status": "available",
            "nodes": len(nodes),
            "edges": len(edges),
            "notes": "Tracked as explicit graph with nodes/edges.",
        }

    if isinstance(payload, dict) and "entries" in payload and isinstance(payload["entries"], list):
        return {
            "path": str(path.relative_to(ROOT)),
            "status": "available",
            "nodes": len(payload["entries"]),
            "edges": 0,
            "notes": "Tracked as JSON entries.",
        }

    return {
        "path": str(path.relative_to(ROOT)),
        "status": "available",
        "nodes": 0,
        "edges": 0,
        "notes": f"JSON keys: {sorted(payload.keys()) if isinstance(payload, dict) else 'n/a'}",
    }


def build_snapshot() -> dict[str, Any]:
    registry = registry_snapshot()
    git = git_state(ROOT)
    knowledge = knowledge_db_summary(detect_knowledge_db())
    roadmap = roadmap_summary(ROADMAP_PATH)

    inbox_count = count_files(NIGREDO_ROOT / "inbox", (".pdf", ".txt", ".md", ".tex"))
    domain_pdf_count = sum(
        count_files(NIGREDO_ROOT / domain, (".pdf", ".txt", ".md", ".tex"))
        for domain in ("physics", "ML", "philosophy", "neuroscience", "mathematics", "unclassified")
    )

    return {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "worktree": git,
        "pipeline": {
            "registry_total": registry["total"],
            "registry_status_counts": registry["status_counts"],
            "registry_domain_counts": registry["domain_counts"],
            "library_records": _count_yaml(ALBEDO_ROOT / "library"),
            "exhaust_records": _count_yaml(ALBEDO_ROOT / "exhaust"),
            "connections": _count_connection_files(),
            "hypotheses": _count_yaml(RUBEDO_ROOT / "hypotheses"),
            "drafts": _count_yaml(RUBEDO_ROOT / "drafts"),
            "nigredo_inbox_items": inbox_count,
            "nigredo_domain_queue": domain_pdf_count,
        },
        "knowledge_graph": knowledge,
        "roadmap": roadmap,
        "codex": str(CODEX_PATH),
    }


def recommendations(snapshot: dict[str, Any]) -> list[str]:
    roadmap = snapshot.get("roadmap") or {}
    if roadmap and roadmap.get("status") != "available":
        return [f"Repair canonical roadmap before project work: {roadmap.get('error', 'invalid')}"]
    if roadmap.get("status") == "available":
        active_status = str(roadmap.get("active_status") or "").strip().lower()
        if roadmap.get("active_task") and active_status in {"active", "in progress"}:
            return [f"Resume canonical active task: {roadmap['active_task']}"]
        if roadmap.get("next_task"):
            return [f"Resume canonical roadmap task: {roadmap['next_task']}"]

    pipeline = snapshot["pipeline"]
    status_counts = pipeline["registry_status_counts"]
    reg_total = pipeline["registry_total"]
    actions: list[str] = []

    if pipeline["nigredo_inbox_items"] > 0:
        actions.append("Run ingestion on queued inbox items (/ingest /awaken workflow).")
    if status_counts.get("pending", 0) > 0 or status_counts.get("ingested_only", 0) > 0:
        doms = [
            domain
            for domain, count in pipeline["registry_domain_counts"].items()
            if count and count > 0
        ]
        actions.append(
            "Awaken domain subagents for ingested papers: /awaken <domain> --depth 3 --count 3."
            if doms
            else "Awaken a domain subagent when ingested papers are staged."
        )
    if reg_total >= 2:
        actions.append("Run structural connection pass: /connect --all.")
    if pipeline["connections"] > 0:
        actions.append("Run gap detection on connection clusters: /detect --all.")
    if pipeline["hypotheses"] > 0:
        actions.append("Generate candidate research note drafts from hypotheses: /draft.")
    if snapshot["worktree"]["inside_worktree"] is False:
        actions.append("Initialize git worktree with /incipere before other automation.")
    if snapshot["knowledge_graph"]["status"] == "missing":
        actions.append("Create memory persistence DB on next /concludere call.")

    if not actions:
        actions.append("No obvious next action; use /validate and /status checks to confirm integrity.")

    return actions


def render_incipere(snapshot: dict[str, Any], json_output: bool = False) -> int:
    if json_output:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
        return 0

    worktree = snapshot["worktree"]
    pipeline = snapshot["pipeline"]
    knowledge = snapshot["knowledge_graph"]
    roadmap = snapshot.get("roadmap") or {
        "path": str(ROADMAP_PATH),
        "status": "missing",
        "active_task": None,
        "active_status": None,
        "next_task": None,
        "error": "canonical roadmap is missing",
    }

    print(f"\n/incipere :: session check-in ({snapshot['timestamp']})")
    print("Worktree:")
    print(f"- inside worktree: {worktree['inside_worktree']}")
    if worktree["inside_worktree"]:
        print(f"- branch: {worktree['branch']}")
        print(f"- head: {worktree['commit']}")
        print(f"- status: {worktree['status']}")
    else:
        print("- git status unavailable until initialized")

    if worktree["inside_worktree"] and worktree["pending_changes"]:
        print("\nPending changes:")
        for line in worktree["pending_changes"][:12]:
            print(f"- {line}")
        if len(worktree["pending_changes"]) > 12:
            remaining = len(worktree["pending_changes"]) - 12
            print(f"- ... and {remaining} more")

    print("\nProgress:")
    print(f"- Registry entries: {pipeline['registry_total']}")
    if pipeline["registry_total"]:
        for key, value in sorted(pipeline["registry_status_counts"].items()):
            print(f"  - {key}: {value}")
    print(f"- Albedo library: {pipeline['library_records']}")
    print(f"- Albedo exhaust: {pipeline['exhaust_records']}")
    print(f"- Connections: {pipeline['connections']}")
    print(f"- Hypotheses: {pipeline['hypotheses']}")
    print(f"- Drafts: {pipeline['drafts']}")

    print("\nNigredo intake:")
    print(f"- Inbox: {pipeline['nigredo_inbox_items']}")
    print(f"- Domain queue: {pipeline['nigredo_domain_queue']}")

    print("\nKnowledge memory/graph:")
    print(f"- path: {knowledge['path']}")
    print(f"- status: {knowledge['status']}")
    print(f"- nodes: {knowledge['nodes']} edges: {knowledge['edges']}")
    print(f"- note: {knowledge['notes']}")

    print("\nCanonical roadmap:")
    print(f"- path: {roadmap['path']}")
    print(f"- status: {roadmap['status']}")
    print(f"- active task: {roadmap['active_task'] or 'not recorded'}")
    print(f"- active status: {roadmap.get('active_status') or 'not recorded'}")
    print(f"- next task: {roadmap['next_task'] or 'not recorded'}")
    if roadmap.get("error"):
        print(f"- error: {roadmap['error']}")

    next_actions = recommendations(snapshot)
    print("\nWhat can be done next:")
    for item in next_actions:
        print(f"- {item}")

    return 0


def _handle_session_exception(command: str, exc: Exception) -> int:
    message = str(exc).strip() or "unknown failure"
    if message.lower().startswith("vigil"):
        print(f"{command}: gate check failed -> {message}")
    else:
        print(f"{command}: {message}")
    return 1


def default_memory_path() -> Path:
    existing = detect_knowledge_db()
    return existing or (LAPIS_ROOT / "memory.jsonl")


def append_findings_to_memory(
    memory_path: Path,
    entry: dict[str, Any],
) -> None:
    memory_path.parent.mkdir(parents=True, exist_ok=True)

    if memory_path.suffix == ".jsonl":
        with open(memory_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
        return

    payload = safe_load_json(memory_path)
    if not isinstance(payload, dict):
        payload = {"version": 1, "entries": []}
    if "entries" in payload and isinstance(payload["entries"], list):
        payload["entries"].append(entry)
        payload["updated_at"] = entry["timestamp"]
        with open(memory_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        return

    # Legacy graph shape support.
    nodes = payload.setdefault("nodes", [])
    edges = payload.setdefault("edges", [])
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(edges, list):
        edges = []
    nodes.append({"id": entry.get("id"), "type": "session", "payload": entry})
    payload["nodes"] = nodes
    payload["edges"] = edges
    payload["updated_at"] = entry["timestamp"]
    with open(memory_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def _build_memory_entry(
    *, skill: str, command: str, findings: list[str], snapshot: dict[str, Any]
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "skill": skill,
        "command": command,
        "findings": findings,
        "worktree": {
            "branch": snapshot["worktree"].get("branch"),
            "commit": snapshot["worktree"].get("commit"),
            "root": str(ROOT),
        },
        "pipeline": snapshot["pipeline"],
        "knowledge_graph": snapshot["knowledge_graph"],
    }


def persist_checkpoint(
    *, command: str, findings: list[str] | None = None, memory_db: Path | None = None
) -> Path:
    """
    Persist a lightweight session checkpoint to the memory DB only.

    This is intentionally non-committal: it writes structured progress for recovery
    and crash safety, without mutating tracked project state files.
    """
    snapshot = build_snapshot()
    findings_text = list(findings or [])
    if not findings_text:
        findings_text = [f"{command} completed; persisted snapshot."]

    memory_path = memory_db or default_memory_path()
    entry = _build_memory_entry(
        skill="checkpoint", command=command, findings=findings_text, snapshot=snapshot
    )
    append_findings_to_memory(memory_path, entry)
    return memory_path


def run_incipere(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="/incipere session start skill.")
    parser.add_argument(
        "--refresh-codex",
        action="store_true",
        help="Deprecated compatibility flag; the canonical roadmap is never rewritten automatically.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    try:
        assert_durable_worktree(ROOT)
        git_messages = ensure_git_worktree(ROOT)
        snapshot = build_snapshot()

        if args.json:
            rc = render_incipere(snapshot, json_output=True)
        else:
            rc = render_incipere(snapshot, json_output=False)
            if git_messages:
                for message in git_messages:
                    print(f"\n{message}")

        if args.refresh_codex:
            print(
                f"\n--refresh-codex is deprecated; update the canonical roadmap manually: "
                f"{ROADMAP_PATH}"
            )

        return rc
    except Exception as exc:  # pragma: no cover - session wrapper guard
        return _handle_session_exception("/incipere", exc)


def _collect_concludere_findings(args: argparse.Namespace) -> list[str]:
    findings: list[str] = []

    findings.extend(args.finding)

    if args.findings_file:
        file_path = Path(args.findings_file)
        if file_path.exists():
            findings.append(file_path.read_text(encoding="utf-8").strip())
        else:
            findings.append(f"findings_file not found: {file_path}")

    if not sys.stdin.isatty() and _stdin_has_data():
        stdin_text = sys.stdin.read().strip()
        if stdin_text:
            findings.append(stdin_text)

    if not findings:
        findings.append("No explicit findings provided; captured from git state snapshot.")

    return findings


def _stdin_has_data() -> bool:
    """True when piped stdin actually has bytes ready.

    Reading an attached-but-silent stdin (cron, some process runners) would
    block /concludere forever.
    """
    try:
        import select

        ready, _, _ = select.select([sys.stdin], [], [], 0)
        return bool(ready)
    except (ImportError, OSError, ValueError):
        return False


def update_state_from_conclusion(snapshot: dict[str, Any]) -> None:
    if not STATE_PATH.exists():
        return

    state = safe_load_json(STATE_PATH)
    if not isinstance(state, dict):
        return

    sessions = state.setdefault("sessions", {})
    sessions["total"] = int(sessions.get("total", 0)) + 1
    sessions["last_mortem"] = snapshot["timestamp"]
    state["last_updated"] = snapshot["timestamp"]
    state["processing_last_summary"] = {
        "registry_total": snapshot["pipeline"]["registry_total"],
        "connections": snapshot["pipeline"]["connections"],
        "hypotheses": snapshot["pipeline"]["hypotheses"],
        "drafts": snapshot["pipeline"]["drafts"],
    }

    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def validate_stage_paths(root: Path, candidates: list[str]) -> list[Path]:
    """Resolve an explicit, repository-relative staging allowlist."""
    resolved_root = root.resolve()
    paths: list[Path] = []
    seen: set[Path] = set()
    for raw in candidates:
        candidate = Path(raw)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError(f"--stage paths must be repository-relative without traversal: {raw}")
        resolved = (resolved_root / candidate).resolve()
        try:
            resolved.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(f"--stage paths must be repository-relative: {raw}") from exc
        if not resolved.exists():
            raise ValueError(f"--stage path does not exist: {raw}")
        if resolved not in seen:
            paths.append(resolved)
            seen.add(resolved)
    return paths


def validate_memory_path(root: Path, candidate: Path) -> Path:
    """Require crash-recovery memory to stay repository-local and Git-ignored."""
    resolved_root = root.resolve()
    if ".." in candidate.parts:
        raise ValueError(f"--memory-db must not contain path traversal: {candidate}")
    resolved = candidate.resolve() if candidate.is_absolute() else (resolved_root / candidate).resolve()
    try:
        relative = resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"--memory-db must stay inside the repository: {candidate}") from exc
    if resolved.exists() and not resolved.is_file():
        raise ValueError(f"--memory-db must name a file: {candidate}")

    ignored = run_cmd(
        ["git", "check-ignore", "--quiet", "--", str(relative)],
        cwd=resolved_root,
        context="git check-ignore --memory-db",
    )
    if ignored.returncode != 0:
        raise ValueError(
            f"--memory-db must be a repository-local Git-ignored recovery file: {candidate}"
        )
    return resolved


def _ensure_clean_tracked_worktree(root: Path) -> None:
    staged = run_cmd(
        ["git", "diff", "--cached", "--quiet", "--"],
        cwd=root,
        context="git diff --cached --quiet",
    )
    if staged.returncode != 0:
        raise RuntimeError("refusing session close: Git index already contains staged changes")

    unstaged = run_cmd(
        ["git", "diff", "--quiet", "--"],
        cwd=root,
        context="git diff --quiet",
    )
    if unstaged.returncode != 0:
        raise RuntimeError(
            "refusing session close: commit substantive tracked changes before /concludere"
        )


def _changed_tracked_paths(root: Path) -> set[Path]:
    result = run_cmd(
        ["git", "diff", "--name-only", "-z", "--"],
        cwd=root,
        context="git diff --name-only",
        check=True,
    )
    return {
        (root / value).resolve()
        for value in result.stdout.split("\0")
        if value
    }


def _staged_paths(root: Path) -> set[Path]:
    result = run_cmd(
        ["git", "diff", "--cached", "--name-only", "-z", "--"],
        cwd=root,
        context="git diff --cached --name-only",
        check=True,
    )
    return {(root / value).resolve() for value in result.stdout.split("\0") if value}


def _capture_files(paths: list[Path]) -> dict[Path, bytes | None]:
    return {path: path.read_bytes() if path.exists() else None for path in paths}


def _restore_files(captured: dict[Path, bytes | None]) -> None:
    for path, content in captured.items():
        if content is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)


def _rollback_closeout(root: Path, captured: dict[Path, bytes | None]) -> None:
    """Restore the clean tracked baseline established before close began."""
    run_cmd(
        ["git", "reset", "--quiet"],
        cwd=root,
        context="git reset closeout index",
        check=True,
    )
    changed = _changed_tracked_paths(root)
    if changed:
        relative_paths = sorted(str(path.relative_to(root.resolve())) for path in changed)
        run_cmd(
            ["git", "restore", "--source=HEAD", "--worktree", "--", *relative_paths],
            cwd=root,
            context="git restore failed closeout changes",
            check=True,
        )
    _restore_files(captured)


def run_concludere(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="/concludere session close skill.")
    parser.add_argument("-f", "--finding", action="append", default=[], help="Finding to persist (repeatable)")
    parser.add_argument("-m", "--message", default=None, help="Git commit message.")
    parser.add_argument("--findings-file", dest="findings_file", default=None, help="Path to a text file of findings.")
    parser.add_argument("--memory-db", type=Path, default=None, help="Override memory database path.")
    parser.add_argument("--no-commit", action="store_true", help="Persist findings but skip git commit.")
    parser.add_argument(
        "--stage",
        action="append",
        default=[],
        metavar="PATH",
        help="Repository-relative closeout path to stage (repeatable; commit mode only).",
    )
    args = parser.parse_args(argv)

    try:
        assert_durable_worktree(ROOT)
        ensure_git_worktree(ROOT)
        snapshot = build_snapshot()
        findings = _collect_concludere_findings(args)
        timestamp = dt.datetime.now(dt.timezone.utc)
        memory_path = validate_memory_path(ROOT, args.memory_db or default_memory_path())
        entry = _build_memory_entry(
            skill="concludere",
            command="concludere",
            findings=findings,
            snapshot=snapshot,
        )
        entry["timestamp"] = timestamp.isoformat()

        if args.no_commit:
            append_findings_to_memory(memory_path, entry)
            print(f"Findings saved to {memory_path}")
            print(f"Canonical roadmap remains manual: {ROADMAP_PATH}")
            return 0

        if not args.stage:
            raise ValueError("commit mode requires at least one explicit --stage PATH")
        stage_paths = validate_stage_paths(ROOT, args.stage)
        if STATE_PATH.resolve() not in stage_paths:
            raise ValueError(
                "commit mode requires --stage athanasor/lapis/state.json for generated close state"
            )

        _ensure_clean_tracked_worktree(ROOT)
        captured = _capture_files(stage_paths)
        committed = False
        try:
            append_findings_to_memory(memory_path, entry)
            vigil_env = os.environ.copy()
            vigil_env["AZOTH_PROJECT_ROOT"] = str(ROOT)
            local_vigil = ROOT / "athanasor" / "vigil" / "verify.py"
            vigil_command = (
                [sys.executable, str(local_vigil), "close"]
                if local_vigil.is_file()
                else [sys.executable, "-m", "athanasor.vigil.verify", "close"]
            )
            run_cmd(
                vigil_command,
                cwd=ROOT,
                env=vigil_env,
                context="Vigil close",
                check=True,
            )
            post_vigil_staged = _staged_paths(ROOT)
            if post_vigil_staged:
                staged_names = sorted(
                    str(path.relative_to(ROOT.resolve())) for path in post_vigil_staged
                )
                raise RuntimeError(
                    "Vigil close staged paths unexpectedly: " + ", ".join(staged_names)
                )
            update_state_from_conclusion(snapshot)

            changed = _changed_tracked_paths(ROOT)
            unexpected = sorted(str(path.relative_to(ROOT)) for path in changed - set(stage_paths))
            if unexpected:
                raise RuntimeError(
                    "session close modified paths outside the --stage allowlist: "
                    + ", ".join(unexpected)
                )

            relative_paths = [str(path.relative_to(ROOT)) for path in stage_paths]
            run_cmd(
                ["git", "add", "--", *relative_paths],
                cwd=ROOT,
                context="git add -- explicit closeout paths",
                check=True,
            )
            print("Staged closeout paths:")
            for value in relative_paths:
                print(f"- {value}")

            staged_paths = _staged_paths(ROOT)
            unexpected_staged = sorted(
                str(path.relative_to(ROOT.resolve()))
                for path in staged_paths - set(stage_paths)
            )
            if unexpected_staged:
                raise RuntimeError(
                    "Git index contains paths outside the --stage allowlist: "
                    + ", ".join(unexpected_staged)
                )

            staged = run_cmd(
                ["git", "diff", "--cached", "--quiet", "--"],
                cwd=ROOT,
                context="git diff --cached --quiet",
            )
            if staged.returncode == 0:
                print("No closeout changes to commit.")
            else:
                commit_message = (
                    args.message
                    or f"concludere: persist findings at {timestamp.strftime('%Y-%m-%d %H:%M UTC')}"
                )
                env = os.environ.copy()
                env.setdefault("GIT_AUTHOR_NAME", "Azoth Session Bot")
                env.setdefault("GIT_AUTHOR_EMAIL", "azoth-bot@example.com")
                env.setdefault("GIT_COMMITTER_NAME", env["GIT_AUTHOR_NAME"])
                env.setdefault("GIT_COMMITTER_EMAIL", env["GIT_AUTHOR_EMAIL"])
                run_cmd(
                    [
                        "git",
                        "commit",
                        "--no-gpg-sign",
                        "--only",
                        "-m",
                        commit_message,
                        "--",
                        *relative_paths,
                    ],
                    cwd=ROOT,
                    env=env,
                    context="git commit --no-gpg-sign --only explicit closeout paths",
                    check=True,
                )
                committed = True
                new_head = run_cmd(
                    ["git", "rev-parse", "HEAD"],
                    cwd=ROOT,
                    context="git rev-parse HEAD",
                    check=True,
                ).stdout.strip()
                print(f"Committed: {new_head[:9]}")

            _ensure_clean_tracked_worktree(ROOT)
        except Exception:
            if not committed:
                _rollback_closeout(ROOT, captured)
            raise

        print(f"Findings saved to {memory_path}")
        print(f"Persistent state updated: {STATE_PATH}")
        print(f"Update canonical roadmap manually: {ROADMAP_PATH}")
        return 0
    except Exception as exc:  # pragma: no cover - session wrapper guard
        return _handle_session_exception("/concludere", exc)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Azoth session commands: incipere/concludere entrypoint.")
    parser.add_argument("command", choices=["incipere", "concludere"], help="Command to run.")
    parser.add_argument("command_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    if args.command == "incipere":
        raise SystemExit(run_incipere(args.command_args))
    raise SystemExit(run_concludere(args.command_args))
