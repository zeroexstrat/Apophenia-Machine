#!/usr/bin/env python3
"""Schema migration utility for Azoth artifacts.

The migrator walks generated YAML files and normalizes versioned payloads so
artifacts stay machine-verifiable after older runs.
"""

from __future__ import annotations

import argparse
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]


KNOWN_VERSIONS = {
    "library": 1,
    "exhaust": 2,
    "connect": 1,
    "detect": 1,
}

SCHEMA_FALLBACK = {
    "high": 4,
    "very_high": 5,
    "veryhigh": 5,
    "high-ish": 4,
    "medium": 3,
    "moderate": 3,
    "low": 2,
    "very_low": 1,
    "low_to_medium": 2,
    "speculative": 2,
    "likely": 3,
    "derived": 5,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_yaml(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def write_yaml(path: Path, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False)


def coerce_int(value: Any, fallback: int = 0) -> int:
    if value is None:
        return fallback
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except ValueError:
            return fallback
    return fallback


def coerce_float(value: Any, fallback: float = 0.0) -> float:
    if value is None:
        return fallback
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return fallback
    return fallback


def coerce_confidence(value: Any, fallback: int = 0) -> int:
    if isinstance(value, bool):
        return fallback
    if value is None:
        return fallback

    text = str(value).strip().lower().replace(" ", "_")
    if not text:
        return fallback

    if text in SCHEMA_FALLBACK:
        mapped = SCHEMA_FALLBACK[text]
    elif text == "verylow":
        mapped = 1
    elif re.fullmatch(r"\d+(\.\d+)?", text):
        mapped = int(float(text))
    else:
        mapped = fallback

    return max(1, min(5, int(mapped)))


def _infer_schema_type(path: Path) -> str:
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        rel = None

    if rel is not None and len(rel.parts) >= 2:
        if rel.parts[0] == "albedo" and rel.parts[1] == "library":
            return "library"
        if rel.parts[0] == "albedo" and rel.parts[1] == "exhaust":
            return "exhaust"
        if rel.parts[0] == "citrinitas" and rel.parts[1] in {"within_domain", "cross_domain"}:
            return "connect"
        if rel.parts[0] == "rubedo" and rel.parts[1] == "hypotheses":
            return "detect"

    if path.name.endswith("_exhaust.yaml"):
        return "exhaust"
    if path.parent.name in {"within_domain", "cross_domain"}:
        return "connect"
    if path.parent.name == "hypotheses":
        return "detect"
    return "library"


def _status_alias(value: Any, allowed: set[str], fallback: str) -> str:
    if isinstance(value, str):
        normalized = value.strip().lower().replace(" ", "_")
        if normalized in allowed:
            return normalized
    return fallback


def migrate_library(payload: dict[str, Any], version: int, notes: list[str]) -> tuple[dict[str, Any], bool]:
    changed = False

    if payload.get("schema_version") != version:
        if "schema_version" in payload:
            notes.append(f"schema_version: {payload.get('schema_version')} -> {version}")
        else:
            notes.append(f"schema_version added ({version})")
        payload["schema_version"] = version
        changed = True

    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    year = source.get("year")
    if isinstance(year, str):
        parsed = coerce_int(year, fallback=None)
        if parsed is not None:
            source["year"] = parsed
            changed = True
            notes.append("normalized source.year to integer")
    payload["source"] = source

    return payload, changed


def migrate_exhaust(payload: dict[str, Any], version: int, notes: list[str]) -> tuple[dict[str, Any], bool]:
    changed = False

    if payload.get("schema_version") != version:
        if "schema_version" in payload:
            notes.append(f"schema_version: {payload.get('schema_version')} -> {version}")
        else:
            notes.append(f"schema_version added ({version})")
        payload["schema_version"] = version
        changed = True

    top = payload.get("exhaustion")
    if isinstance(top, dict):
        if top.get("exhaustion_depth") is not None:
            depth = coerce_int(top.get("exhaustion_depth"), fallback=3)
            if depth != top.get("exhaustion_depth"):
                top["exhaustion_depth"] = max(1, min(5, depth))
                changed = True
                notes.append("normalized exhaustion.exhaustion_depth")

        term = top.get("termination")
        if isinstance(term, dict):
            criterion = term.get("criterion")
            if isinstance(criterion, str) and criterion not in {
                "redundancy",
                "speculative_ceiling",
                "hard_cap",
                "completed",
            }:
                term["criterion"] = "completed"
                changed = True
                notes.append("normalized termination.criterion")
            deeper = term.get("deeper_available")
            if isinstance(deeper, str):
                lowered = deeper.lower()
                if lowered in {"true", "1", "yes", "y"}:
                    term["deeper_available"] = True
                    changed = True
                elif lowered in {"false", "0", "no", "n"}:
                    term["deeper_available"] = False
                    changed = True
            top["termination"] = term

        payload["exhaustion"] = top

    for key in ("derivations", "exercises", "missing_angles", "open_questions", "unstated_assumptions", "experiments", "necessary_connections"):
        items = payload.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if "source_claim" in item:
                continue
            if "follows_from" in item and item.get("statement"):
                item["source_claim"] = item.get("follows_from")
                changed = True
                notes.append(f"{key}: added source_claim from follows_from")

    return payload, changed


def migrate_connect(payload: dict[str, Any], version: int, path: Path, notes: list[str]) -> tuple[dict[str, Any], bool]:
    changed = False

    if payload.get("schema_version") != version:
        if "schema_version" in payload:
            notes.append(f"schema_version: {payload.get('schema_version')} -> {version}")
        else:
            notes.append(f"schema_version added ({version})")
        payload["schema_version"] = version
        changed = True

    if payload.get("pair_scope") not in {"within_domain", "cross_domain"}:
        if path.parent.name == "within_domain":
            payload["pair_scope"] = "within_domain"
            changed = True
        elif path.parent.name == "cross_domain":
            payload["pair_scope"] = "cross_domain"
            changed = True
    if payload.get("paper_a_id") is None and "paper_a" in payload:
        payload["paper_a_id"] = str(payload["paper_a"])
        changed = True
    if payload.get("paper_b_id") is None and "paper_b" in payload:
        payload["paper_b_id"] = str(payload["paper_b"])
        changed = True

    pdomains = payload.get("pair_domains")
    if not isinstance(pdomains, dict):
        payload["pair_domains"] = {
            "paper_a_domain": payload.get("paper_a_domain"),
            "paper_b_domain": payload.get("paper_b_domain"),
        }
        if any(v is not None for v in payload["pair_domains"].values()):
            changed = True

    confidence_raw = coerce_confidence(payload.get("confidence_raw"), fallback=coerce_confidence(payload.get("confidence"), fallback=3))
    confidence = coerce_confidence(payload.get("confidence"), fallback=confidence_raw if confidence_raw else 3)
    if confidence_raw:
        if payload.get("confidence_raw") != confidence_raw:
            payload["confidence_raw"] = confidence_raw
            changed = True
    if payload.get("confidence") != confidence:
        payload["confidence"] = confidence
        changed = True

    if not isinstance(payload.get("status"), str) or payload["status"] not in {"pending_review", "accepted", "rejected", "investigate"}:
        payload["status"] = "pending_review"
        changed = True

    if payload.get("novelty") not in {"obvious", "non-obvious", "speculative"}:
        payload["novelty"] = "non-obvious"
        changed = True

    if payload.get("connection_type") == "shared_approach":
        payload["connection_type"] = "methodological_overlap"
        changed = True

    if not isinstance(payload.get("tags"), list):
        payload["tags"] = []
        changed = True

    return payload, changed


def migrate_detect(payload: dict[str, Any], version: int, notes: list[str]) -> tuple[dict[str, Any], bool]:
    changed = False

    if payload.get("schema_version") != version:
        if "schema_version" in payload:
            notes.append(f"schema_version: {payload.get('schema_version')} -> {version}")
        else:
            notes.append(f"schema_version added ({version})")
        payload["schema_version"] = version
        changed = True

    if payload.get("cluster_id") in (None, ""):
        if payload.get("id"):
            payload["cluster_id"] = str(payload["id"])
            notes.append("migrated cluster_id from id")
            changed = True

    if not isinstance(payload.get("paper_ids"), list):
        papers = []
        if isinstance(payload.get("papers"), list):
            papers = [str(x) for x in payload["papers"]]
        elif isinstance(payload.get("paper_id"), str):
            papers = [str(payload["paper_id"])]
        payload["paper_ids"] = papers
        changed = True

    status = _status_alias(payload.get("status"), {"pending_review", "investigate", "accepted", "rejected"}, "pending_review")
    if payload.get("status") != status:
        payload["status"] = status
        changed = True

    novelty = payload.get("novelty")
    if novelty in {"yes", "y", "true", "1"}:
        payload["novelty"] = True
        changed = True
    elif novelty in {"no", "n", "false", "0"}:
        payload["novelty"] = False
        changed = True
    elif isinstance(novelty, bool):
        pass
    else:
        payload.setdefault("novelty", True)
        payload["novelty"] = bool(payload.get("novelty")) if payload.get("novelty") is not None else True
        changed = True

    gaps = payload.get("gaps")
    if isinstance(gaps, list):
        for idx, gap in enumerate(gaps):
            if not isinstance(gap, dict):
                continue
            if not isinstance(gap.get("gap_type"), str):
                gap["gap_type"] = "unexplored_question"
                changed = True
            gap["confidence"] = coerce_confidence(gap.get("confidence"), fallback=3)
            gap["feasibility"] = coerce_confidence(gap.get("feasibility"), fallback=3)
            if not isinstance(gap.get("novelty"), bool):
                if gap.get("novelty") in {"yes", "true", "1"}:
                    gap["novelty"] = True
                    changed = True
                elif gap.get("novelty") in {"no", "false", "0"}:
                    gap["novelty"] = False
                    changed = True
                else:
                    gap["novelty"] = True
                    changed = True
            if not isinstance(gap.get("supporting_papers"), list):
                if isinstance(gap.get("supporting_paper"), list):
                    gap["supporting_papers"] = gap["supporting_paper"]
                    changed = True
                elif isinstance(gap.get("supporting_paper"), str):
                    gap["supporting_papers"] = [gap.get("supporting_paper")]
                    changed = True
                else:
                    gap["supporting_papers"] = []
                    changed = True
            if gap.get("rank") is None:
                gap["rank"] = idx + 1
                changed = True

    # ensure list order for deterministic file diffs
    if payload.get("paper_ids"):
        paper_ids = list(dict.fromkeys([str(x) for x in payload["paper_ids"] if isinstance(x, str)]))
        if paper_ids != payload.get("paper_ids"):
            payload["paper_ids"] = paper_ids
            changed = True

    return payload, changed


def migrate_file(path: Path, target_versions: dict[str, int], write: bool, notes: list[str]) -> tuple[bool, int, list[str]]:
    if not path.exists() or not path.is_file():
        return False, 0, notes

    if path.suffix.lower() not in {".yaml", ".yml"}:
        return False, 0, notes

    data = load_yaml(path)
    if data is None:
        return False, 0, notes + ["empty_or_invalid_yaml"]
    if not isinstance(data, dict):
        return False, 0, notes + ["root_not_mapping"]

    artifact = _infer_schema_type(path)
    version = target_versions.get(artifact, KNOWN_VERSIONS[artifact])
    original = deepcopy(data)

    changed = False
    if artifact == "library":
        data, changed = migrate_library(data, version=version, notes=notes)
    elif artifact == "exhaust":
        data, changed = migrate_exhaust(data, version=version, notes=notes)
    elif artifact == "connect":
        data, changed = migrate_connect(data, version=version, path=path, notes=notes)
    elif artifact == "detect":
        data, changed = migrate_detect(data, version=version, notes=notes)

    if data == original:
        changed = False

    if changed and write:
        write_yaml(path, data)

    return changed, len(notes), notes


def _iter_targets(
    root: Path,
    explicit: list[Path] | None,
    all_scope: bool,
) -> list[Path]:
    if explicit:
        out: list[Path] = []
        for target in explicit:
            if not target.exists():
                continue
            if target.is_file():
                out.append(target)
                continue
            if target.is_dir():
                out.extend(sorted(target.rglob("*.y*ml")))
        return out

    if not all_scope:
        return []

    folders = [
        root / "albedo" / "library",
        root / "albedo" / "exhaust",
        root / "citrinitas" / "within_domain",
        root / "citrinitas" / "cross_domain",
        root / "rubedo" / "hypotheses",
    ]
    out: list[Path] = []
    for folder in folders:
        if folder.exists():
            out.extend(sorted(folder.rglob("*.y*ml")))
    return out


def _resolve_targets(target_versions: dict[str, int], paths: list[Path], all_scope: bool) -> tuple[list[Path], list[str]]:
    targets = _iter_targets(ROOT, paths, all_scope=all_scope)
    summary: list[str] = []
    if not targets:
        summary.append("No YAML files selected.")
    return sorted(set(targets)), summary


def _report_file(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Migrate Azoth YAML artifacts to target schema versions.")
    p.add_argument("paths", nargs="*", type=Path, help="Files or directories to migrate")
    p.add_argument("--all", action="store_true", dest="all_scope", help="Migrate all known artifact directories")
    p.add_argument("--target", type=int, help="Global target schema version override")
    p.add_argument("--library-version", type=int, help="Target version for library SCHEMA.yaml outputs")
    p.add_argument("--exhaust-version", type=int, help="Target version for EXHAUST_SCHEMA.yaml outputs")
    p.add_argument("--connect-version", type=int, help="Target version for CONNECT_SCHEMA.yaml outputs")
    p.add_argument("--detect-version", type=int, help="Target version for DETECT_SCHEMA.yaml outputs")
    p.add_argument("--dry-run", action="store_true", help="Do not write files")
    p.add_argument("--json", action="store_true", help="Emit migration report as JSON")
    return p


def build_target_versions(args: argparse.Namespace) -> dict[str, int]:
    version_map = dict(KNOWN_VERSIONS)
    if args.target is not None:
        for key in version_map:
            version_map[key] = args.target

    if args.library_version is not None:
        version_map["library"] = args.library_version
    if args.exhaust_version is not None:
        version_map["exhaust"] = args.exhaust_version
    if args.connect_version is not None:
        version_map["connect"] = args.connect_version
    if args.detect_version is not None:
        version_map["detect"] = args.detect_version

    return version_map


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.all_scope and not args.paths:
        parser.print_help()
        return 2

    target_versions = build_target_versions(args)
    targets, report = _resolve_targets(target_versions, [Path(p).resolve() for p in args.paths], all_scope=args.all_scope)

    changed_count = 0
    processed_count = 0
    file_reports: list[dict[str, Any]] = []

    for path in targets:
        notes: list[str] = []
        changed, _, _ = migrate_file(path, target_versions=target_versions, write=not args.dry_run, notes=notes)
        processed_count += 1
        if changed:
            changed_count += 1
            action = "would_update" if args.dry_run else "updated"
            file_reports.append({"file": _report_file(path), "action": action, "notes": notes or ["no-op"]})
        else:
            file_reports.append({"file": _report_file(path), "action": "unchanged", "notes": notes or ["no-op"]})

    result = {
        "timestamp": _now_iso(),
        "processed": processed_count,
        "changed": changed_count,
        "dry_run": args.dry_run,
        "target_versions": target_versions,
        "files": file_reports,
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps(result, indent=2))
        for summary in report:
            print(summary)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
