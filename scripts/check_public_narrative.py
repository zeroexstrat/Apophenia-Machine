#!/usr/bin/env python3
"""Verify that public P8 claims match locked evidence and authority limits."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_README = ROOT / "README.md"
DEFAULT_CASE_STUDY = (
    ROOT / "docs" / "case-studies" / "looped-transformer-prior-art.md"
)
DEFAULT_COMPARISON = (
    ROOT
    / "benchmarks"
    / "operations-decision-support-v1"
    / "results"
    / "locked-comparison.json"
)

SELECTED_METRICS = (
    "macro_f1",
    "unsafe_ood_assignment",
    "claim_precision",
    "reference_recall",
    "candidate_recall",
    "workload_reduction",
    "precision_at_5",
    "ndcg_at_10",
    "evidence_support",
    "supported_items",
    "useful_items",
    "redundancy",
    "unsupported_derived_items",
)

DIRECT_SOURCES = {
    "Parcae": "https://arxiv.org/html/2604.12946v1",
    "STARS": "https://arxiv.org/html/2605.26733v1",
    "CART": "https://arxiv.org/abs/2606.01495",
}


def _decimal(value: object) -> str:
    return "undefined" if value is None else f"{float(value):.4f}"


def _count(value: object) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:.4f}"


def _model_metrics(comparison: dict[str, object]) -> dict[str, dict[str, Any]]:
    runs = comparison.get("runs")
    if not isinstance(runs, list):
        raise ValueError("/runs: expected a list")
    model = next(
        (
            run
            for run in runs
            if isinstance(run, dict) and run.get("run_id") == "model_5_6_sol"
        ),
        None,
    )
    if model is None or not isinstance(model.get("metrics"), list):
        raise ValueError("/runs/model_5_6_sol: missing model metrics")
    metrics = {
        metric.get("name"): metric
        for metric in model["metrics"]
        if isinstance(metric, dict) and isinstance(metric.get("name"), str)
    }
    if set(metrics) != set(SELECTED_METRICS):
        raise ValueError("/runs/model_5_6_sol/metrics: expected the exact 13 metrics")
    return metrics


def metric_rows(comparison: dict[str, object]) -> list[str]:
    """Render the exact denominator-bearing README rows for the locked model run."""

    metrics = _model_metrics(comparison)
    rows: list[str] = []
    for name in SELECTED_METRICS:
        metric = metrics[name]
        uncertainty = metric.get("uncertainty_result")
        if not isinstance(uncertainty, dict):
            raise ValueError(
                f"/runs/model_5_6_sol/metrics/{name}/uncertainty_result: missing"
            )
        threshold = {True: "met", False: "not met", None: "undefined"}.get(
            metric.get("threshold_met")
        )
        if threshold is None:
            raise ValueError(
                f"/runs/model_5_6_sol/metrics/{name}/threshold_met: invalid"
            )
        try:
            row = (
                f"| `{name}` | {_decimal(metric.get('value'))} | "
                f"{_count(metric.get('numerator'))} / "
                f"{_count(metric.get('denominator'))} | "
                f"{_decimal(uncertainty.get('lower'))}–"
                f"{_decimal(uncertainty.get('upper'))} | {threshold} |"
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"/runs/model_5_6_sol/metrics/{name}: invalid numeric field"
            ) from exc
        rows.append(row)
    return rows


def audit_public_narrative(
    readme: str,
    case_study: str,
    comparison: dict[str, object],
) -> list[str]:
    """Return sorted field-addressed findings without mutating the inputs."""

    errors: list[str] = []
    try:
        expected_rows = metric_rows(comparison)
    except ValueError as exc:
        return [f"/comparison: {exc}"]

    for name, row in zip(SELECTED_METRICS, expected_rows, strict=True):
        if row not in readme:
            errors.append(f"/README/metrics/{name}: exact locked row is missing")

    required_readme = {
        "/README/scope/papers": "12-paper",
        "/README/scope/pairs": "66-pair",
        "/README/provenance/provider": "provider model identity",
        "/README/authority": "validity and novelty remain human-reviewed",
    }
    folded_readme = readme.casefold()
    for address, phrase in required_readme.items():
        if phrase.casefold() not in folded_readme:
            errors.append(f"{address}: missing {phrase!r}")

    demo = readme.find("## Five-minute demo")
    architecture = readme.find("## Architecture")
    if demo < 0 or architecture < 0 or demo > architecture:
        errors.append("/README/order: Five-minute demo must precede Architecture")

    folded_case = case_study.casefold()
    required_case = {
        "/case/status/candidate": "pending_review",
        "/case/status/decision": "rejected",
        "/case/reframe/comparison": "comparison",
        "/case/reframe/replication": "replication",
    }
    for address, phrase in required_case.items():
        if phrase.casefold() not in folded_case:
            errors.append(f"{address}: missing {phrase!r}")
    if folded_case.find("pending_review") > folded_case.find("rejected"):
        errors.append("/case/status/order: candidate review state must precede rejection")

    for source, url in DIRECT_SOURCES.items():
        if url not in case_study:
            errors.append(f"/case/sources/{source}: missing primary-source URL")

    for phrase in ("we discovered", "novel contribution", "experiment confirmed"):
        if phrase in folded_case:
            errors.append(f"/case/unsupported_claim: prohibited phrase {phrase!r}")

    return sorted(dict.fromkeys(errors))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readme", type=Path, default=DEFAULT_README)
    parser.add_argument("--case-study", type=Path, default=DEFAULT_CASE_STUDY)
    parser.add_argument("--comparison", type=Path, default=DEFAULT_COMPARISON)
    return parser


def _read_text(path: Path, description: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"{description} is not readable: {path}: {exc}") from exc


def _read_comparison(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"comparison is not readable JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"comparison must be a JSON object: {path}")
    metric_rows(value)
    return value


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        readme = _read_text(args.readme, "README")
        case_study = _read_text(args.case_study, "case study")
        comparison = _read_comparison(args.comparison)
    except ValueError as exc:
        print(f"Public narrative audit: ERROR: {exc}")
        return 2

    errors = audit_public_narrative(readme, case_study, comparison)
    if errors:
        print("Public narrative audit: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Public narrative audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
