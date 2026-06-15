#!/usr/bin/env python3
"""Session lifecycle commands for Azoth.

`/incipere`:
  - ensures a git worktree exists,
  - reads git and persistent state,
  - prints where the project is and what can be done next.

`/concludere`:
  - stores session findings in persistent memory (json/jsonl),
  - updates lapis state/codex metadata,
  - creates a git commit.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = ROOT / "athanasor" / "lapis" / "state.json"
CODEX_PATH = ROOT / "athanasor" / "lapis" / "codex.md"
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


def run_cmd(cmd: list[str], *, cwd: Path, check: bool = False, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        env=env,
        check=check,
    )


def is_git_worktree(path: Path) -> bool:
    result = run_cmd(["git", "rev-parse", "--is-inside-work-tree"], cwd=path)
    return result.returncode == 0 and result.stdout.strip() == "true"


def ensure_git_worktree(path: Path) -> list[str]:
    messages: list[str] = []
    if is_git_worktree(path):
        messages.append(f"Detected git worktree at {path}")
        return messages

    init_result = run_cmd(["git", "init"], cwd=path)
    if init_result.returncode != 0:
        raise RuntimeError(
            "Could not initialize a git worktree at the project root. "
            "Run this command from the project directory or set WORKTREE_ROOT."
        )

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

    branch_res = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=path)
    commit_res = run_cmd(["git", "rev-parse", "HEAD"], cwd=path)
    status_res = run_cmd(["git", "status", "--short"], cwd=path)
    remote_res = run_cmd(["git", "remote"], cwd=path)

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
        "codex": str(CODEX_PATH),
    }


def recommendations(snapshot: dict[str, Any]) -> list[str]:
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

    next_actions = recommendations(snapshot)
    print("\nWhat can be done next:")
    for item in next_actions:
        print(f"- {item}")

    return 0


def append_to_codex(content: str) -> None:
    CODEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    if CODEX_PATH.exists():
        existing = CODEX_PATH.read_text(encoding="utf-8")
    else:
        existing = ""

    separator = "\n---\n"
    if existing and not existing.endswith("\n"):
        existing += "\n"
    if existing and not existing.rstrip().endswith("---"):
        existing += separator

    with open(CODEX_PATH, "w", encoding="utf-8") as f:
        f.write(existing)
        f.write(content.rstrip() + "\n")


def create_checkpoint_section(title: str, snapshot: dict[str, Any], findings: list[str] | None = None) -> str:
    ts = snapshot["timestamp"]
    lines = [f"\n## {title} ({ts})"]
    lines.append("")
    lines.append(f"- Branch: {snapshot['worktree'].get('branch')}")
    lines.append(f"- Head: {snapshot['worktree'].get('commit')}")
    lines.append(f"- Registry entries: {snapshot['pipeline']['registry_total']}")
    lines.append(f"- Library records: {snapshot['pipeline']['library_records']}")
    lines.append(f"- Exhaust records: {snapshot['pipeline']['exhaust_records']}")
    lines.append(f"- Connections: {snapshot['pipeline']['connections']}")
    lines.append(f"- Hypotheses: {snapshot['pipeline']['hypotheses']}")
    lines.append(f"- Drafts: {snapshot['pipeline']['drafts']}")
    lines.append(f"- Knowledge DB: {snapshot['knowledge_graph']['path']}")
    lines.append("")
    if findings:
        lines.append("### Findings")
        for item in findings:
            lines.append(f"- {item}")
    return "\n".join(lines)


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


def run_incipere(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="/incipere session start skill.")
    parser.add_argument("--refresh-codex", action="store_true", help="Write this snapshot to codex.md")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

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
        snapshot["timestamp"] = dt.datetime.now(dt.timezone.utc).isoformat()
        section = create_checkpoint_section("Session check-in", snapshot)
        append_to_codex(section)
        print(f"\nSession snapshot written to {CODEX_PATH}")

    return rc


def _collect_concludere_findings(args: argparse.Namespace) -> list[str]:
    findings: list[str] = []

    findings.extend(args.finding)

    if args.findings_file:
        file_path = Path(args.findings_file)
        if file_path.exists():
            findings.append(file_path.read_text(encoding="utf-8").strip())
        else:
            findings.append(f"findings_file not found: {file_path}")

    if not sys.stdin.isatty():
        stdin_text = sys.stdin.read().strip()
        if stdin_text:
            findings.append(stdin_text)

    if not findings:
        findings.append("No explicit findings provided; captured from git state snapshot.")

    return findings


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


def run_concludere(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="/concludere session close skill.")
    parser.add_argument("-f", "--finding", action="append", default=[], help="Finding to persist (repeatable)")
    parser.add_argument("-m", "--message", default=None, help="Git commit message.")
    parser.add_argument("--findings-file", dest="findings_file", default=None, help="Path to a text file of findings.")
    parser.add_argument("--memory-db", type=Path, default=None, help="Override memory database path.")
    parser.add_argument("--no-commit", action="store_true", help="Persist findings but skip git commit.")
    parser.add_argument("--skip-vigil-close", action="store_true", help="Skip running vigil close after commit.")
    args = parser.parse_args(argv)

    ensure_git_worktree(ROOT)

    snapshot = build_snapshot()
    findings = _collect_concludere_findings(args)
    timestamp = dt.datetime.now(dt.timezone.utc)

    memory_path = args.memory_db or default_memory_path()
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": timestamp.isoformat(),
        "skill": "concludere",
        "findings": findings,
        "worktree": {
            "branch": snapshot["worktree"].get("branch"),
            "commit": snapshot["worktree"].get("commit"),
            "root": str(ROOT),
        },
        "pipeline": snapshot["pipeline"],
        "knowledge_graph": snapshot["knowledge_graph"],
    }

    append_findings_to_memory(memory_path, entry)
    update_state_from_conclusion(snapshot)

    if not args.no_commit:
        commit_message = (
            args.message
            or f"concludere: persist findings at {timestamp.strftime('%Y-%m-%d %H:%M UTC')}"
        )

        run_cmd(["git", "add", "-A"], cwd=ROOT)
        if run_cmd(["git", "status", "--short"], cwd=ROOT).stdout.strip():
            env = os.environ.copy()
            env.setdefault("GIT_AUTHOR_NAME", "Azoth Session Bot")
            env.setdefault("GIT_AUTHOR_EMAIL", "azoth-bot@example.com")
            env.setdefault("GIT_COMMITTER_NAME", env["GIT_AUTHOR_NAME"])
            env.setdefault("GIT_COMMITTER_EMAIL", env["GIT_AUTHOR_EMAIL"])
            commit = run_cmd(
                ["git", "commit", "--no-gpg-sign", "-m", commit_message],
                cwd=ROOT,
                env=env,
            )
            if commit.returncode != 0:
                print(f"Commit failed: {commit.stderr.strip() or commit.stdout.strip()}")
                return 1
        else:
            print("No changes to commit.")

        run_cmd(["git", "rev-parse", "HEAD"], cwd=ROOT)
        new_head = run_cmd(["git", "rev-parse", "HEAD"], cwd=ROOT).stdout.strip()
        if new_head:
            print(f"Committed: {new_head[:9]}")

        if not args.skip_vigil_close:
            close_result = run_cmd(
                [sys.executable, str(ROOT / "athanasor" / "vigil" / "verify.py"), "close"],
                cwd=ROOT,
            )
            if close_result.returncode != 0:
                print(f"Vigil close reported: {close_result.stderr.strip() or close_result.stdout.strip()}")

    section = create_checkpoint_section("Session conclusion", snapshot, findings)
    append_to_codex(section)
    print(f"Findings saved to {memory_path}")
    print(f"Codex updated: {CODEX_PATH}")
    print(f"Persistent state updated: {STATE_PATH}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Azoth session commands: incipere/concludere entrypoint.")
    parser.add_argument("command", choices=["incipere", "concludere"], help="Command to run.")
    parser.add_argument("command_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    if args.command == "incipere":
        raise SystemExit(run_incipere(args.command_args))
    raise SystemExit(run_concludere(args.command_args))
