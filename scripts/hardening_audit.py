#!/usr/bin/env python3
"""Hardening audit for pipeline artifacts and registry invariants."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from athanasor.registry import Registry
from athanasor.scripts.validate import validate_file


def _iter_artifacts(root: Path) -> list[Path]:
    folders = [
        root / "albedo" / "library",
        root / "albedo" / "exhaust",
        root / "citrinitas" / "within_domain",
        root / "citrinitas" / "cross_domain",
        root / "rubedo" / "hypotheses",
        root / "rubedo" / "drafts",
    ]
    out: list[Path] = []
    for folder in folders:
        if not folder.exists():
            continue
        for path in folder.rglob("*.y*ml"):
            if path.is_file():
                out.append(path)
    return sorted(out)


def _validate_artifacts(root: Path, *, strict: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for path in _iter_artifacts(root):
        ok, detail, _ = validate_file(path, fix=False)
        if not ok:
            message = f"{path.relative_to(root)}: {'; '.join(detail)}"
            if strict:
                errors.append(message)
            else:
                warnings.append(message)
    return errors, warnings


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    output: list[dict[str, Any]] = []
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
                output.append(payload)
    return output


def _index_connection_papers(root: Path) -> set[str]:
    out: set[str] = set()
    for folder in (root / "citrinitas" / "within_domain", root / "citrinitas" / "cross_domain"):
        if not folder.exists():
            continue
        for path in folder.rglob("*.y*ml"):
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                continue
            paper_a = str(payload.get("paper_a_id") or "").strip()
            paper_b = str(payload.get("paper_b_id") or "").strip()
            if paper_a:
                out.add(paper_a)
            if paper_b:
                out.add(paper_b)
    return out


def _iter_connection_report_paths(root: Path) -> list[Path]:
    report_dir = root / "citrinitas" / "reports"
    if not report_dir.exists():
        return []
    return sorted(report_dir.glob("connect_report_*.yaml"))


def _iter_connection_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for folder in (root / "citrinitas" / "within_domain", root / "citrinitas" / "cross_domain"):
        if not folder.exists():
            continue
        paths.extend(sorted(folder.rglob("*.y*ml")))
    return paths


def _index_hypothesis_papers(root: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    for path in (root / "rubedo" / "hypotheses").glob("*.yaml"):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        for paper_id in payload.get("paper_ids", []):
            pid = str(paper_id).strip()
            if not pid:
                continue
            out[pid] = out.get(pid, 0) + 1
    return out


def _index_draft_papers(root: Path) -> set[str]:
    index_file = root / "rubedo" / "drafts" / "index.md"
    if not index_file.exists():
        return set()
    pattern = re.compile(r"papers:([^|]+)")
    found: set[str] = set()
    for raw in index_file.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw.startswith("-"):
            continue
        match = pattern.search(raw)
        if not match:
            continue
        payload = match.group(1).replace("\\n", "").strip()
        for paper_id in payload.split(","):
            value = paper_id.strip()
            if value:
                found.add(value)
    return found


def _validate_registry_state(root: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    registry_path = root / "albedo" / "registry.jsonl"
    entries = _read_jsonl(registry_path)

    ids = [entry.get("paper_id") for entry in entries if entry.get("paper_id")]
    if len(ids) != len(set(ids)):
        errors.append("Registry contains duplicate paper IDs.")

    status_counts = Counter(str(entry.get("status", "")) for entry in entries)
    for expected in ("pending", "ingested_only", "exhausted"):
        if status_counts.get(expected, 0) == 0:
            warnings.append(f"No papers currently in status={expected}.")

    connections = _index_connection_papers(root)
    hypotheses = _index_hypothesis_papers(root)
    drafted_papers = _index_draft_papers(root)

    for entry in entries:
        paper_id = str(entry.get("paper_id") or "")
        status = str(entry.get("status") or "pending")
        paths = entry.get("paths") or {}
        library_rel = paths.get("library")
        exhaust_rel = paths.get("exhaust")

        if status == "exhausted":
            if not library_rel:
                errors.append(f"{paper_id}: exhausted paper missing library path.")
            if not exhaust_rel:
                errors.append(f"{paper_id}: exhausted paper missing exhaust path.")
        if library_rel and not (root / library_rel).exists():
            warnings.append(f"{paper_id}: library path missing: {library_rel}")
        if exhaust_rel and not (root / exhaust_rel).exists():
            warnings.append(f"{paper_id}: exhaust path missing: {exhaust_rel}")

        if entry.get("connected"):
            if paper_id and paper_id not in connections:
                warnings.append(f"{paper_id}: connected=true but no connection artifact found.")
        if entry.get("detected"):
            if paper_id and paper_id not in hypotheses:
                warnings.append(f"{paper_id}: detected=true but not present in any hypothesis.")
        if entry.get("drafted"):
            if paper_id and paper_id not in drafted_papers:
                warnings.append(f"{paper_id}: drafted=true but not in draft index.")

    return errors, warnings


def _validate_connection_reports(root: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    report_paths = _iter_connection_report_paths(root)
    connection_files = _iter_connection_paths(root)
    if connection_files and not report_paths:
        warnings.append("No connect synthesis report found despite saved connection files.")
        return errors, warnings

    if not report_paths:
        return errors, warnings

    for path in report_paths:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            warnings.append(f"{path.relative_to(root)}: report is not a YAML mapping.")
            continue

        scope = payload.get("scope")
        if not isinstance(scope, str) or not scope.strip():
            warnings.append(f"{path.relative_to(root)}: missing/invalid scope.")

        generated_at = payload.get("generated_at")
        if not isinstance(generated_at, str) or not generated_at.strip():
            warnings.append(f"{path.relative_to(root)}: missing generated_at.")

        pairs = payload.get("pairs")
        if not isinstance(pairs, dict):
            warnings.append(f"{path.relative_to(root)}: missing pairs block.")
            continue

        for field in [
            "candidate_pairs",
            "analyzed_pairs",
            "pairs_with_no_connection",
            "skipped_similarity",
            "below_confidence_threshold",
            "validation_failed",
            "speculative_filtered",
        ]:
            raw = pairs.get(field)
            if not isinstance(raw, int) or raw < 0:
                warnings.append(f"{path.relative_to(root)}: invalid pairs.{field} = {raw!r}.")

        connections = payload.get("connections")
        if not isinstance(connections, dict):
            warnings.append(f"{path.relative_to(root)}: missing connections summary.")

    for path in connection_files:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            warnings.append(f"{path.relative_to(root)}: connection artifact is not a YAML mapping.")
            continue
        confidence = payload.get("confidence")
        if not isinstance(confidence, int) or confidence < 3:
            warnings.append(
                f"{path.relative_to(root)}: expected persisted connection confidence >=3 "
                f"(found: {confidence!r})."
            )

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Run hardening checks and return non-zero on failures.")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=ROOT,
        help="Project root to inspect.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat schema validation warnings as hard failures.",
    )
    args = parser.parse_args()

    root = args.project_root.resolve()
    schema_errors, schema_warnings = _validate_artifacts(root, strict=args.strict)
    registry_errors, registry_warnings = _validate_registry_state(root)
    report_errors, report_warnings = _validate_connection_reports(root)

    if schema_warnings or registry_warnings or report_warnings:
        print("Warnings:")
        for item in schema_warnings + registry_warnings + report_warnings:
            print(f"  - {item}")

    if schema_errors or registry_errors or report_errors:
        print("Errors:")
        for item in schema_errors + registry_errors + report_errors:
            print(f"  - {item}")
        return 1

    print("Hardening audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
