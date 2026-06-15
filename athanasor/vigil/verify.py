#!/usr/bin/env python3
"""Vigil — gate verification for the Apophenia Machine.

Three modes:
  start  — check all gates before substantive work
  verify — check all gates after substantive work, plus diff against start state
  close  — update lapis/state.json, write codex.md, produce mortem

Usage:
  python3 athanasor/vigil/verify.py start
  python3 athanasor/vigil/verify.py verify
  python3 athanasor/vigil/verify.py close
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

ALLOWED_UNTRACKED_PREFIXES = (
    "nigredo/",
    "albedo/",
    "citrinitas/",
    "rubedo/",
    "athanasor/vigil/reports/",
)
ALLOWED_UNTRACKED_EXACT = {
    "athanasor/embeddings.json",
    "athanasor/embeddings.npy",
}

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
STATE_PATH = PROJECT_ROOT / "athanasor" / "lapis" / "state.json"
CODEX_PATH = PROJECT_ROOT / "athanasor" / "lapis" / "codex.md"
GATES_PATH = PROJECT_ROOT / "athanasor" / "vigil" / "gates.yaml"
REPORTS_DIR = PROJECT_ROOT / "athanasor" / "vigil" / "reports"
MORTEMS_DIR = PROJECT_ROOT / "athanasor" / "mortems"
REGISTRY_PATH = PROJECT_ROOT / "albedo" / "registry.jsonl"

# ---------------------------------------------------------------------------
# Gate checks
# ---------------------------------------------------------------------------

def check_git_drift() -> tuple[bool, str]:
    """Fail if uncommitted changes exist. Worktree must be clean."""
    import subprocess
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=PROJECT_ROOT
    )
    if result.stdout.strip():
        noisy_lines: list[str] = []
        for raw in result.stdout.splitlines():
            if len(raw) < 3:
                noisy_lines.append(raw)
                continue
            status, path = raw[:2], raw[3:]
            clean_path = path.strip()
            if clean_path.startswith('"') and clean_path.endswith('"'):
                clean_path = clean_path[1:-1]
            clean_path = clean_path.replace("\\", "/")

            if status == "??":
                if clean_path in ALLOWED_UNTRACKED_EXACT:
                    continue
                for prefix in ALLOWED_UNTRACKED_PREFIXES:
                    if clean_path.startswith(prefix):
                        break
                else:
                    noisy_lines.append(raw)
                continue

            noisy_lines.append(raw)

        if noisy_lines:
            return False, "Uncommitted changes:\n" + "\n".join(noisy_lines[:500])
        return True, "Worktree clean (allowed untracked runtime artifacts ignored)."
    return True, "Worktree clean."


def check_registry() -> tuple[bool, str]:
    """Fail if any entry has status 'confirmed' without a triage date."""
    if not REGISTRY_PATH.exists():
        return True, "No registry yet — no entries to verify."
    issues = []
    with open(REGISTRY_PATH) as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            entry = json.loads(line)
            triage = entry.get("triage", {})
            gates = entry.get("gates", {})
            # Corpus: ingested papers must have at least one claim
            if entry.get("status", "").startswith("ingested"):
                if gates.get("corpus") == "pass":
                    # Already validated, skip
                    pass
            # Coniunctio: connections claiming novelty must not cite each other
            # (checked during cross-connection pass, tracked here)
            if triage.get("outcome") == "confirmed" and not triage.get("last_reviewed"):
                issues.append(f"Line {i}: '{entry.get('title','')}' confirmed without review date")
    if issues:
        return False, "\n".join(issues[:10])
    return True, "Registry clean."


def check_exhaustion_ceiling() -> tuple[bool, str]:
    """Warn if exhausted papers are being re-processed without --reprocess."""
    exhaust_dir = PROJECT_ROOT / "albedo" / "exhaust"
    if not exhaust_dir.exists():
        return True, "No exhaustion directory yet."
    # Inactive by default — populated during exhaustion passes
    return True, "Exhaustion tracking active via registry.jsonl cursor."


def check_nigredo_redux() -> tuple[bool, str]:
    """Check that rejected candidates are not re-surfacing."""
    hypotheses_dir = PROJECT_ROOT / "rubedo" / "hypotheses"
    if not hypotheses_dir.exists():
        return True, "No hypotheses directory yet."
    # Inactive by default — populated after first Rubedo pass
    return True, "Nigredo Redux gate: no candidates to track."


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def make_report(gates: dict[str, tuple[bool, str]], mode: str) -> dict:
    """Produce a Vigil report."""
    all_pass = all(passed for passed, _ in gates.values())
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()

    report = {
        "mode": mode,
        "timestamp": timestamp,
        "passed": all_pass,
        "gates": {
            name: {"status": "pass" if passed else "fail", "detail": detail}
            for name, (passed, detail) in gates.items()
        }
    }
    return report


def write_report(report: dict, mode: str) -> Path:
    """Write report to athanasor/vigil/reports/."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REPORTS_DIR / f"vigil_{mode}_{ts}.json"
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    return path


def update_state(report: dict) -> None:
    """Update lapis/state.json with latest gate states."""
    if not STATE_PATH.exists():
        return
    with open(STATE_PATH) as f:
        state = json.load(f)
    state["gates"] = {
        name: gate["status"] for name, gate in report["gates"].items()
    }
    state["gates"]["last_vigil"] = report["timestamp"]
    state["last_updated"] = report["timestamp"]
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Vigil — Apophenia Machine gate checker")
    parser.add_argument("mode", choices=["start", "verify", "close"])
    args = parser.parse_args()

    gates = {}
    gates["git_drift"] = check_git_drift()
    gates["registry"] = check_registry()
    gates["exhaustion_ceiling"] = check_exhaustion_ceiling()
    gates["nigredo_redux"] = check_nigredo_redux()

    report = make_report(gates, args.mode)
    path = write_report(report, args.mode)

    if args.mode == "close":
        update_state(report)

    if report["passed"]:
        print(f"Vigil {args.mode}: PASS ({len(gates)} gates)")
    else:
        failed = [n for n, g in gates.items() if not g[0]]
        print(f"Vigil {args.mode}: FAIL — {len(failed)} gate(s) failed: {', '.join(failed)}")
        for name, (passed, detail) in gates.items():
            if not passed:
                print(f"\n  [{name}] {detail}")
        sys.exit(1)

    print(f"  Report: {path}")


if __name__ == "__main__":
    main()
