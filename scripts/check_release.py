#!/usr/bin/env python3
"""Fail closed when the public release evidence drifts from locked artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = ROOT / "release" / "v0.2.0.json"
BENCHMARK_ROOT = ROOT / "benchmarks" / "operations-decision-support-v1"
COMPARISON_RELATIVE = Path(
    "benchmarks/operations-decision-support-v1/results/locked-comparison.json"
)
SOURCES_RELATIVE = Path("benchmarks/operations-decision-support-v1/sources.yaml")
SELECTED_METRICS = (
    "macro_f1",
    "unsafe_ood_assignment",
    "claim_precision",
    "reference_recall",
    "candidate_recall",
    "workload_reduction",
    "useful_items",
    "unsupported_derived_items",
)
MISSED = ["macro_f1", "workload_reduction", "useful_items"]
UNDEFINED = ["unsafe_ood_assignment", "unsupported_derived_items"]
PYTHON_VERSIONS = ["3.10", "3.11", "3.12"]
EXPECTED_URLS = {
    "repository": "https://github.com/zeroexstrat/Apophenia-Machine",
    "release": "https://github.com/zeroexstrat/Apophenia-Machine/releases/tag/v0.2.0",
    "case_study": "https://0xstrategies.com/case-studies/apophenia-machine.html",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _version(root: Path) -> str:
    match = re.search(
        r'^version\s*=\s*"([^"]+)"',
        (root / "pyproject.toml").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if not match:
        raise ValueError("pyproject version missing")
    return match.group(1)


def _model_metrics(comparison: dict[str, Any]) -> dict[str, dict[str, Any]]:
    try:
        run = next(
            row for row in comparison["runs"] if row["run_id"] == "model_5_6_sol"
        )
    except (KeyError, StopIteration) as exc:
        raise ValueError("locked comparison lacks model_5_6_sol") from exc
    return {row["name"]: row for row in run["metrics"]}


def load_release_evidence(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("release evidence must be an object")
    return payload


def audit_release(
    root: Path = ROOT,
    evidence_path: Path = DEFAULT_EVIDENCE,
) -> list[str]:
    errors: list[str] = []
    try:
        evidence = load_release_evidence(evidence_path)
        version = _version(root)
        comparison_path = root / COMPARISON_RELATIVE
        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        expected_metrics = _model_metrics(comparison)
        sources = yaml.safe_load((root / SOURCES_RELATIVE).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        return [f"/release: {exc}"]

    if evidence.get("schema_version") != 1:
        errors.append("/schema_version: expected 1")
    if evidence.get("artifact_type") != "azoth_release_evidence":
        errors.append("/artifact_type: expected azoth_release_evidence")
    if evidence.get("version") != version:
        errors.append("/version: evidence and pyproject differ")
    if evidence.get("python") != PYTHON_VERSIONS:
        errors.append("/python: expected 3.10, 3.11, and 3.12")

    benchmark = evidence.get("benchmark")
    if not isinstance(benchmark, dict):
        return sorted(errors + ["/benchmark: object required"])
    if benchmark.get("benchmark_id") != comparison.get("benchmark_id"):
        errors.append("/benchmark/benchmark_id: mismatch")
    if benchmark.get("locked_comparison_sha256") != _sha256(comparison_path):
        errors.append("/benchmark/locked_comparison_sha256: mismatch")

    source_rows = sources.get("sources", []) if isinstance(sources, dict) else []
    paper_count = len(source_rows)
    expected_pairs = paper_count * (paper_count - 1) // 2
    if benchmark.get("papers") != paper_count:
        errors.append("/benchmark/papers: source count mismatch")
    if benchmark.get("pairs") != expected_pairs:
        errors.append("/benchmark/pairs: canonical pair count mismatch")
    if benchmark.get("runs") != len(comparison.get("runs", [])):
        errors.append("/benchmark/runs: comparison run count mismatch")
    metric_records = sum(len(row.get("metrics", [])) for row in comparison.get("runs", []))
    if benchmark.get("metric_records") != metric_records:
        errors.append("/benchmark/metric_records: comparison count mismatch")

    public_metrics = benchmark.get("metrics")
    if not isinstance(public_metrics, dict):
        errors.append("/benchmark/metrics: object required")
        public_metrics = {}
    if set(public_metrics) != set(SELECTED_METRICS):
        errors.append("/benchmark/metrics: exact selected metric set required")
    for name in SELECTED_METRICS:
        public = public_metrics.get(name)
        locked = expected_metrics.get(name)
        if not isinstance(public, dict) or locked is None:
            errors.append(f"/benchmark/metrics/{name}: missing")
            continue
        fields = {
            "value": locked["value"],
            "numerator": locked["numerator"],
            "denominator": locked["denominator"],
            "lower": locked["uncertainty_result"]["lower"],
            "upper": locked["uncertainty_result"]["upper"],
            "threshold_met": locked["threshold_met"],
        }
        for field, expected in fields.items():
            if public.get(field) != expected:
                errors.append(f"/benchmark/metrics/{name}/{field}: mismatch")

    if benchmark.get("missed_targets") != MISSED:
        errors.append("/benchmark/missed_targets: exact ordered set required")
    if benchmark.get("undefined_metrics") != UNDEFINED:
        errors.append("/benchmark/undefined_metrics: exact ordered set required")

    limitations = evidence.get("limitations")
    if not isinstance(limitations, dict):
        errors.append("/limitations: object required")
        limitation_text = ""
    else:
        limitation_text = " ".join(str(value) for value in limitations.values()).lower()
    for phrase in (
        "12-paper",
        "66-pair",
        "external-validity",
        "human-reviewed",
        "not independently verified",
    ):
        if phrase not in limitation_text:
            errors.append(f"/limitations/{phrase}: missing")
    if evidence.get("urls") != EXPECTED_URLS:
        errors.append("/urls: exact canonical URLs required")

    try:
        readme = (root / "README.md").read_text(encoding="utf-8")
        changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        notes = (root / "docs" / "releases" / "v0.2.0.md").read_text(
            encoding="utf-8"
        )
    except OSError as exc:
        errors.append(f"/release_docs: {exc}")
        return sorted(errors)
    if "actions/workflows/hardening.yml/badge.svg?branch=main" not in readme:
        errors.append("/README/badge: missing main hardening badge")
    if "@v0.2.0" not in readme:
        errors.append("/README/install: missing v0.2.0 pin")
    if "## [0.2.0] - 2026-07-13" not in changelog:
        errors.append("/CHANGELOG/version: missing 0.2.0 heading")
    if any(name not in notes for name in MISSED):
        errors.append("/release_notes/missed_targets: exact names required")
    if any(name not in notes for name in UNDEFINED):
        errors.append("/release_notes/undefined_metrics: exact names required")
    for phrase in (
        "12-paper",
        "66-pair",
        "human-reviewed",
        "external validity",
        "not independently verified",
    ):
        if phrase.lower() not in notes.lower():
            errors.append(f"/release_notes/limitations/{phrase}: missing")
    return sorted(errors)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    errors = audit_release(ROOT, args.evidence)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("Release audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
