#!/usr/bin/env python3
"""Compare Azoth exhaust output across runs — one project root per agent/model.

Point it at the same library exhausted by different driving agents (Claude, Codex,
autoclaw, or different configured backends) and it reports, per paper and in
aggregate, how much and what kind of exhaustion each produced — so you can study
differences in generation across models on identical inputs.

Usage:
  python3 scripts/exhaust_diff.py --run claude=/path/to/run_a --run gpt=/path/to/run_b
  python3 scripts/exhaust_diff.py --run a=./a --run b=./b --json
  python3 scripts/exhaust_diff.py --run a=./a --run b=./b --paper <paper_id>

Each --run is LABEL=PROJECT_ROOT. A project root is a directory containing
albedo/exhaust/*_exhaust.yaml.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

BUCKETS = (
    "derivations",
    "exercises",
    "missing_angles",
    "open_questions",
    "unstated_assumptions",
    "experiments",
    "necessary_connections",
)
DERIVATION_CONFIDENCE = ("derived", "likely", "speculative")


def _load_exhaust_dir(root: Path) -> dict[str, dict[str, Any]]:
    """Index a run's exhaust files by paper_id -> {bucket counts, confidence tally}."""
    papers: dict[str, dict[str, Any]] = {}
    exhaust_dir = Path(root) / "albedo" / "exhaust"
    if not exhaust_dir.exists():
        return papers
    for path in sorted(exhaust_dir.glob("*_exhaust.yaml")):
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(payload, dict):
            continue
        meta = payload.get("exhaustion") if isinstance(payload.get("exhaustion"), dict) else {}
        paper_id = str(meta.get("paper_id") or path.stem.replace("_exhaust", ""))
        counts: dict[str, int] = {}
        non_redundant = 0
        confidence: dict[str, int] = {level: 0 for level in DERIVATION_CONFIDENCE}
        for bucket in BUCKETS:
            items = payload.get(bucket)
            if not isinstance(items, list):
                counts[bucket] = 0
                continue
            counts[bucket] = len(items)
            for item in items:
                if not isinstance(item, dict):
                    continue
                if not item.get("redundant", False):
                    non_redundant += 1
                level = str(item.get("confidence", "")).strip().lower()
                if level in confidence:
                    confidence[level] += 1
        papers[paper_id] = {
            "counts": counts,
            "total": sum(counts.values()),
            "non_redundant": non_redundant,
            "confidence": confidence,
            "depth": meta.get("exhaustion_depth"),
        }
    return papers


def compare(runs: dict[str, Path | str]) -> dict[str, Any]:
    """Build a cross-run comparison of exhaust output."""
    indexed = {label: _load_exhaust_dir(Path(root)) for label, root in runs.items()}
    labels = list(runs.keys())

    all_paper_ids = sorted({pid for run in indexed.values() for pid in run})

    totals: dict[str, dict[str, Any]] = {}
    for label in labels:
        run = indexed[label]
        bucket_totals = {b: sum(p["counts"].get(b, 0) for p in run.values()) for b in BUCKETS}
        conf_totals = {
            level: sum(p["confidence"].get(level, 0) for p in run.values())
            for level in DERIVATION_CONFIDENCE
        }
        totals[label] = {
            "papers": len(run),
            "total_items": sum(p["total"] for p in run.values()),
            "non_redundant": sum(p["non_redundant"] for p in run.values()),
            "by_bucket": bucket_totals,
            "derivation_confidence": conf_totals,
        }

    papers: dict[str, dict[str, Any]] = {}
    for pid in all_paper_ids:
        papers[pid] = {label: (indexed[label].get(pid, {}) or {}).get("counts") for label in labels}
        for label in labels:
            if papers[pid][label] is None:
                papers[pid][label] = None  # explicit coverage gap

    papers_in_all = [pid for pid in all_paper_ids if all(indexed[label].get(pid) for label in labels)]

    return {
        "runs": labels,
        "totals": totals,
        "coverage": {label: len(indexed[label]) for label in labels},
        "papers": papers,
        "papers_in_all_runs": papers_in_all,
        "paper_union": all_paper_ids,
    }


def render_text(report: dict[str, Any]) -> str:
    labels = report["runs"]
    lines: list[str] = []
    lines.append("Exhaust comparison across runs: " + ", ".join(labels))
    lines.append("=" * 60)

    lines.append("\nTotals per run:")
    header = f"  {'metric':<26}" + "".join(f"{label:>14}" for label in labels)
    lines.append(header)
    lines.append(f"  {'papers covered':<26}" + "".join(f"{report['coverage'][l]:>14}" for l in labels))
    lines.append(
        f"  {'total items':<26}" + "".join(f"{report['totals'][l]['total_items']:>14}" for l in labels)
    )
    lines.append(
        f"  {'non-redundant items':<26}"
        + "".join(f"{report['totals'][l]['non_redundant']:>14}" for l in labels)
    )
    for bucket in BUCKETS:
        row = "".join(f"{report['totals'][l]['by_bucket'][bucket]:>14}" for l in labels)
        lines.append(f"  {bucket:<26}{row}")

    lines.append(f"\nPapers in all runs: {len(report['papers_in_all_runs'])} of {len(report['paper_union'])}")
    lines.append("\nPer-paper total items (— = not exhausted in that run):")
    lines.append(f"  {'paper_id':<40}" + "".join(f"{label:>14}" for label in labels))
    for pid in report["paper_union"]:
        cells = []
        for label in labels:
            counts = report["papers"][pid][label]
            cells.append("—" if counts is None else str(sum(counts.values())))
        lines.append(f"  {pid[:40]:<40}" + "".join(f"{c:>14}" for c in cells))
    return "\n".join(lines)


def _parse_run(spec: str) -> tuple[str, Path]:
    if "=" not in spec:
        raise argparse.ArgumentTypeError(f"--run must be LABEL=PATH, got {spec!r}")
    label, _, path = spec.partition("=")
    label = label.strip()
    if not label or not path.strip():
        raise argparse.ArgumentTypeError(f"--run must be LABEL=PATH, got {spec!r}")
    return label, Path(path.strip()).expanduser()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare Azoth exhaust output across runs.")
    parser.add_argument(
        "--run",
        dest="runs",
        action="append",
        type=_parse_run,
        required=True,
        metavar="LABEL=PROJECT_ROOT",
        help="A labelled project root. Repeat for each run to compare.",
    )
    parser.add_argument("--paper", default=None, help="Restrict per-paper output to one paper_id.")
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    args = parser.parse_args(argv)

    runs = dict(args.runs)
    if len(runs) < 1:
        parser.error("provide at least one --run")

    report = compare(runs)

    if args.paper:
        report["papers"] = {args.paper: report["papers"].get(args.paper, {})}
        report["paper_union"] = [args.paper] if args.paper in report["paper_union"] else []

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
