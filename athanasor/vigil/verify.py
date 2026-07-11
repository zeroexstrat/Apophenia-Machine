#!/usr/bin/env python3
"""Vigil — gate verification for the Apophenia Machine.

Three modes:
  start  — check all gates before substantive work
  verify — check all gates after substantive work, plus diff against start state
  close  — update generated gate state in lapis/state.json

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
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from athanasor.schemas import parse_schema, validate as validate_schema
from athanasor.rejections import (
    candidate_fingerprint,
    evidence_fingerprint,
    load_rejections,
)
from athanasor.skills.common import is_specific_text

ALLOWED_OUTPUT_PREFIXES = (
    "nigredo/",
    "albedo/",
    "citrinitas/",
    "rubedo/",
    "athanasor/vigil/reports/",
    "athanasor/lapis/",
)
ALLOWED_UNTRACKED_PREFIXES = ALLOWED_OUTPUT_PREFIXES
ALLOWED_MODIFIED_PREFIXES = (
    "nigredo/",
    "albedo/",
    "citrinitas/",
    "rubedo/",
    "athanasor/lapis/",
    "athanasor/vigil/reports/",
)
ALLOWED_UNTRACKED_EXACT = {
    "athanasor/embeddings.json",
    "athanasor/embeddings.npy",
    "athanasor/lapis/memory.json",
    "athanasor/lapis/memory.jsonl",
    "athanasor/lapis/knowledge_graph.json",
    "athanasor/lapis/knowledge_graph.jsonl",
}

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
STATE_PATH = PROJECT_ROOT / "athanasor" / "lapis" / "state.json"
GATES_PATH = PROJECT_ROOT / "athanasor" / "vigil" / "gates.yaml"
REPORTS_DIR = PROJECT_ROOT / "athanasor" / "vigil" / "reports"
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

            def _is_allowed_path(value: str, prefixes: tuple[str, ...]) -> bool:
                return any(value == prefix[:-1] or value.startswith(prefix) for prefix in prefixes)

            if status == "??":
                if clean_path in ALLOWED_UNTRACKED_EXACT:
                    continue
                if _is_allowed_path(clean_path, ALLOWED_UNTRACKED_PREFIXES):
                    continue
                noisy_lines.append(raw)
                continue

            if _is_allowed_path(clean_path, ALLOWED_MODIFIED_PREFIXES):
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
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            # The gate must report registry corruption, never crash on it —
            # every pipeline command runs this check.
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                issues.append(f"Line {i}: unparseable registry line")
                continue
            if not isinstance(entry, dict):
                issues.append(f"Line {i}: registry line is not an object")
                continue
            triage = entry.get("triage")
            if not isinstance(triage, dict):
                triage = {}
            if triage.get("outcome") == "confirmed" and not triage.get("last_reviewed"):
                issues.append(f"Line {i}: '{entry.get('title','')}' confirmed without review date")
    if issues:
        return False, "\n".join(issues[:10])
    return True, "Registry clean."


def _safe_yaml(path: Path):
    try:
        import yaml

        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _schema_errors(payload: dict[str, Any], schema_name: str) -> list[str]:
    try:
        schema = parse_schema(PROJECT_ROOT / schema_name)
    except Exception as exc:
        return [f"schema unavailable: {exc}"]
    ok, errors, _, changed = validate_schema(payload, schema, path="/", fix=False)
    if changed:
        errors.append("schema validation unexpectedly changed the artifact")
    return [] if ok and not errors else errors


def _specific_text(value: Any) -> bool:
    return is_specific_text(value)


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _registry_entries(root: Path) -> list[dict]:
    path = root / "albedo" / "registry.jsonl"
    entries: list[dict] = []
    if not path.exists():
        return entries
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def check_corpus(root: Path = PROJECT_ROOT) -> tuple[bool, str]:
    """Corpus: processed records validate and contain nonblank claim evidence fields."""
    issues: list[str] = []
    for entry in _registry_entries(root):
        status = str(entry.get("status") or "")
        if status not in {"ingested_only", "exhausted"}:
            continue
        paper_id = str(entry.get("paper_id") or "?")
        rel = (entry.get("paths") or {}).get("library") or f"albedo/library/{paper_id}.yaml"
        record = _safe_yaml(root / rel)
        if record is None:
            issues.append(f"{paper_id}: library record missing/unreadable ({rel})")
            continue
        errors = _schema_errors(record, "SCHEMA.yaml")
        if errors:
            issues.append(f"{paper_id}: library schema invalid: {'; '.join(errors[:5])}")
            continue
        claims = record.get("claims")
        evidence_bearing = isinstance(claims, list) and any(
            isinstance(claim, dict)
            and _specific_text(claim.get("statement"))
            and _specific_text(claim.get("evidence"))
            for claim in claims
        )
        if not evidence_bearing:
            issues.append(f"{paper_id}: no claim has both nonblank statement and evidence fields")
    if issues:
        return False, "Corpus violations:\n" + "\n".join(issues[:10])
    return (
        True,
        "Corpus: processed library records are schema-valid and contain structural evidence fields; "
        "this does not establish scientific truth or evidence adequacy.",
    )


def check_coniunctio(root: Path = PROJECT_ROOT) -> tuple[bool, str]:
    """Coniunctio: connection structure and novelty labels respect declared explicit citations."""
    issues: list[str] = []
    lib_cache: dict[str, dict | None] = {}

    def _record(paper_id: str) -> dict | None:
        if paper_id not in lib_cache:
            lib_cache[paper_id] = _safe_yaml(root / "albedo" / "library" / f"{paper_id}.yaml")
        return lib_cache[paper_id]

    def _title(record: dict | None) -> str:
        if not record:
            return ""
        source = record.get("source") if isinstance(record.get("source"), dict) else {}
        return _normalized(source.get("title"))

    def _targets(record: dict | None) -> set[str]:
        out: set[str] = set()
        if not record:
            return out
        for item in record.get("connections_explicit") or []:
            if isinstance(item, dict) and item.get("target_paper"):
                out.add(_normalized(item["target_paper"]))
        return out

    for base in (root / "citrinitas" / "within_domain", root / "citrinitas" / "cross_domain"):
        if not base.exists():
            continue
        for path in base.rglob("*.y*ml"):
            payload = _safe_yaml(path)
            if not payload:
                issues.append(f"{path.name}: connection missing/unreadable")
                continue
            errors = _schema_errors(payload, "CONNECT_SCHEMA.yaml")
            if errors:
                issues.append(f"{path.name}: connection schema invalid: {'; '.join(errors[:5])}")
                continue
            a_id = str(payload.get("paper_a_id") or "")
            b_id = str(payload.get("paper_b_id") or "")
            rec_a, rec_b = _record(a_id), _record(b_id)
            missing = [paper_id for paper_id, record in ((a_id, rec_a), (b_id, rec_b)) if not record]
            if missing:
                issues.append(f"{path.name}: library record missing for {', '.join(missing)}")
                continue
            for field in ("evidence_a", "evidence_b"):
                if not _specific_text(payload.get(field)):
                    issues.append(f"{path.name}: {field} is blank or placeholder text")
            if payload.get("novelty") == "obvious":
                continue
            cited = (
                (_title(rec_b) and _title(rec_b) in _targets(rec_a))
                or (_title(rec_a) and _title(rec_a) in _targets(rec_b))
                or (_normalized(b_id) in _targets(rec_a))
                or (_normalized(a_id) in _targets(rec_b))
            )
            if cited:
                issues.append(
                    f"{a_id} <-> {b_id}: marked '{payload.get('novelty')}' despite a declared explicit citation"
                )
    if issues:
        return False, "Coniunctio violations:\n" + "\n".join(issues[:10])
    return (
        True,
        "Coniunctio: connection records validate and novelty labels respect declared explicit citations only; "
        "this is not an external novelty search.",
    )


def check_calcinatio(root: Path = PROJECT_ROOT) -> tuple[bool, str]:
    """Calcinatio: exhaustion records validate, derivations trace, and speculation stops at five."""
    issues: list[str] = []
    exhaust_dir = root / "albedo" / "exhaust"
    if exhaust_dir.exists():
        for path in exhaust_dir.glob("*_exhaust.yaml"):
            payload = _safe_yaml(path)
            if not payload:
                issues.append(f"{path.name}: exhaustion missing/unreadable")
                continue
            errors = _schema_errors(payload, "EXHAUST_SCHEMA.yaml")
            if errors:
                issues.append(f"{path.name}: exhaustion schema invalid: {'; '.join(errors[:5])}")
                continue
            consecutive_speculative = 0
            for item in payload.get("derivations") or []:
                if not isinstance(item, dict):
                    continue
                conf = str(item.get("confidence") or "").strip().lower()
                if conf in {"derived", "likely"} and not _specific_text(item.get("follows_from")):
                    issues.append(f"{path.name}: {conf} derivation has no specific source trace")
                if conf == "speculative":
                    consecutive_speculative += 1
                    if consecutive_speculative > 5:
                        issues.append(f"{path.name}: speculative ceiling exceeded (more than 5 consecutive items)")
                        break
                else:
                    consecutive_speculative = 0
    if issues:
        return False, "Calcinatio violations:\n" + "\n".join(issues[:10])
    return (
        True,
        "Calcinatio: exhaustion schemas, confidence enums, trace fields, and the speculative ceiling validate; "
        "this does not prove logical validity.",
    )


def check_caput_mortuum(root: Path = PROJECT_ROOT) -> tuple[bool, str]:
    """Caput Mortuum: exhausted registry IDs and depth cursors exactly match their artifacts."""
    issues: list[str] = []
    for entry in _registry_entries(root):
        status = str(entry.get("status") or "")
        paper_id = str(entry.get("paper_id") or "?")
        raw_registry_depth = entry.get("exhausted_at_depth")
        if status != "exhausted":
            if raw_registry_depth is not None:
                issues.append(
                    f"{paper_id}: status '{status}' has exhaustion cursor {raw_registry_depth}"
                )
            continue
        rel = (entry.get("paths") or {}).get("exhaust") or f"albedo/exhaust/{paper_id}_exhaust.yaml"
        artifact = root / rel
        if not artifact.exists():
            issues.append(f"{paper_id}: exhausted but artifact missing ({rel})")
            continue
        payload = _safe_yaml(artifact)
        if payload is None:
            issues.append(f"{paper_id}: exhaustion artifact unreadable ({rel})")
            continue
        meta = (payload or {}).get("exhaustion") if isinstance((payload or {}).get("exhaustion"), dict) else {}
        artifact_id = str(meta.get("paper_id") or "")
        if artifact_id != paper_id:
            issues.append(f"{paper_id}: artifact paper id '{artifact_id}' does not match registry paper id")
        try:
            file_depth = int(meta.get("exhaustion_depth"))
        except (TypeError, ValueError):
            file_depth = 0
        try:
            registry_depth = int(raw_registry_depth)
        except (TypeError, ValueError):
            registry_depth = 0
        if not 1 <= registry_depth <= 5:
            issues.append(f"{paper_id}: registry cursor {registry_depth} outside supported depth 1..5")
        if not 1 <= file_depth <= 5:
            issues.append(f"{paper_id}: artifact depth {file_depth} outside supported depth 1..5")
        if file_depth != registry_depth:
            issues.append(
                f"{paper_id}: artifact depth {file_depth} does not equal registry cursor {registry_depth}"
            )
    if issues:
        return False, "Caput Mortuum violations:\n" + "\n".join(issues[:10])
    return (
        True,
        "Caput Mortuum: exhausted paper IDs and depth cursors exactly match durable artifacts; "
        "this cannot reconstruct prior token use before state was written.",
    )


def check_nigredo_redux(root: Path = PROJECT_ROOT) -> tuple[bool, str]:
    """Nigredo Redux: durable rejected cluster/evidence fingerprints cannot re-surface pending."""
    issues: list[str] = []
    ledger_path = root / "athanasor" / "lapis" / "rejections.jsonl"
    rejections, ledger_errors = load_rejections(ledger_path)
    if ledger_errors:
        return False, "Nigredo Redux violations:\nmalformed rejection ledger: " + "; ".join(ledger_errors[:10])
    rejected_pairs = {
        (entry["candidate_fingerprint"], entry["evidence_fingerprint"])
        for entry in rejections
    }
    hypotheses_dir = root / "rubedo" / "hypotheses"
    if hypotheses_dir.exists():
        for path in hypotheses_dir.glob("*.yaml"):
            payload = _safe_yaml(path)
            if not payload:
                issues.append(f"{path.stem}: hypothesis missing/unreadable")
                continue
            triage = payload.get("triage") if isinstance(payload.get("triage"), dict) else {}
            decision = str(triage.get("decision") or "").strip().lower()
            status = str(payload.get("status") or "").strip().lower()
            identity = (candidate_fingerprint(payload), evidence_fingerprint(payload))
            if decision in {"rejected", "reject_novelty_claim"} and status in {"pending_review", "investigate"}:
                issues.append(f"{payload.get('cluster_id') or path.stem}: rejected candidate re-surfaced as '{status}'")
            if status in {"pending_review", "investigate"} and identity in rejected_pairs:
                issues.append(
                    f"{payload.get('cluster_id') or path.stem}: pending hypothesis matches a recorded rejection fingerprint"
                )
            if (decision in {"rejected", "reject_novelty_claim"} or status == "rejected") and identity not in rejected_pairs:
                issues.append(
                    f"{payload.get('cluster_id') or path.stem}: rejected hypothesis fingerprint is missing from rejection ledger"
                )
    if issues:
        return False, "Nigredo Redux violations:\n" + "\n".join(issues[:10])
    return (
        True,
        "Nigredo Redux: no pending hypothesis repeats a recorded cluster/evidence rejection; "
        "the same cluster may return only with changed evidence.",
    )


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
    """Update lapis/state.json with latest gate states and live pipeline counts."""
    if not STATE_PATH.exists():
        return
    with open(STATE_PATH) as f:
        state = json.load(f)
    state["gates"] = {
        name: gate["status"] for name, gate in report["gates"].items()
    }
    state["gates"]["last_vigil"] = report["timestamp"]
    state["last_updated"] = report["timestamp"]

    # Sync counts from the registry so durable state never drifts from reality.
    entries = _registry_entries(PROJECT_ROOT)
    status_counts: dict[str, int] = {}
    for entry in entries:
        key = str(entry.get("status") or "unknown")
        status_counts[key] = status_counts.get(key, 0) + 1
    state["processing"] = {
        "registry_total": len(entries),
        "status_counts": status_counts,
        "library_records": len(list((PROJECT_ROOT / "albedo" / "library").glob("*.yaml")))
        if (PROJECT_ROOT / "albedo" / "library").exists() else 0,
        "exhaust_records": len(list((PROJECT_ROOT / "albedo" / "exhaust").glob("*_exhaust.yaml")))
        if (PROJECT_ROOT / "albedo" / "exhaust").exists() else 0,
    }
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
    gates["corpus"] = check_corpus()
    gates["coniunctio"] = check_coniunctio()
    gates["calcinatio"] = check_calcinatio()
    gates["caput_mortuum"] = check_caput_mortuum()
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
