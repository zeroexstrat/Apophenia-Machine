from __future__ import annotations

from copy import deepcopy

import pytest

from athanasor.benchmark.artifacts import BenchmarkArtifactError, SYNTHETIC_NOTICE
from athanasor.benchmark.reporting import render_markdown
from athanasor.benchmark.protocol import EXPECTED_P5_METRIC_CONTRACTS


def synthetic_score_fixture() -> dict[str, object]:
    metrics = []
    for name, contract in EXPECTED_P5_METRIC_CONTRACTS.items():
        metric = dict(contract)
        metric["name"] = name
        metric["numerator_definition"] = metric.pop("numerator")
        metric["denominator_definition"] = metric.pop("denominator")
        metric["threshold"] = dict(metric["threshold"])
        compatible_value = 0.0 if metric["comparison"] in {"==", "<="} else 1.0
        metric.update(
            {
            "numerator": int(compatible_value),
            "denominator": 1,
            "value": compatible_value,
            "uncertainty_result": {
                "method": "Wilson 95% interval",
                "lower": compatible_value,
                "upper": compatible_value,
            },
            "threshold_met": True,
            }
        )
        if name == "macro_f1":
            metric.update(
                {
                    "numerator": 12,
                    "denominator": 15,
                    "value": 0.812345,
                    "uncertainty_result": {
                        "method": "paired bootstrap 95% interval",
                        "lower": 0.7,
                        "upper": 0.9,
                        "seed": 5607,
                        "samples": 2000,
                    },
                }
            )
        elif name == "claim_precision":
            metric.update(
                {
                    "numerator": 0,
                    "denominator": 0,
                    "value": None,
                    "uncertainty_result": {
                        "method": "Wilson 95% interval",
                        "lower": None,
                        "upper": None,
                    },
                    "threshold_met": None,
                }
            )
        metrics.append(metric)
    return {
        "schema_version": 1,
        "artifact_type": "azoth_benchmark_score",
        "benchmark_id": "operations-decision-support-v1",
        "synthetic": True,
        "notice": SYNTHETIC_NOTICE,
        "run_sha256": "1" * 64,
        "gold_commitment": {
            "algorithm": "sha256-canonical-json-v1",
            "private_gold_sha256": "2" * 64,
            "schema_version": 1,
            "freeze_time": "2026-07-12T00:00:00Z",
        },
        "annotation_sha256": None,
        "calculation": {"version": 1, "bootstrap_seed": 5607, "bootstrap_samples": 2000},
        "metrics": metrics,
        "status": "scored",
    }


def test_synthetic_report_is_unmistakably_non_performance() -> None:
    rendered = render_markdown(synthetic_score_fixture())
    assert rendered.count(SYNTHETIC_NOTICE) >= 2
    assert "| Metric | Value | Numerator | Denominator | Uncertainty | Threshold |" in rendered
    assert "## Provenance" in rendered
    assert "## Undefined metrics" in rendered
    assert "## Limitations" in rendered


def test_report_is_byte_deterministic_and_does_not_recompute() -> None:
    score = synthetic_score_fixture()
    score["metrics"][0]["value"] = 0.923456
    first = render_markdown(score)
    second = render_markdown(deepcopy(score))
    assert first == second
    assert "0.923456" in first


def test_report_contains_exact_provenance_counts_and_threshold_outcomes() -> None:
    rendered = render_markdown(synthetic_score_fixture())
    assert "`" + "1" * 64 + "`" in rendered
    assert "12" in rendered and "15" in rendered
    assert "0.700000–0.900000" in rendered
    assert ">= 0.800000: met" in rendered
    assert "claim_precision" in rendered
    assert "undefined (0/0)" in rendered


def test_report_rejects_invalid_score() -> None:
    score = synthetic_score_fixture()
    score["metrics"][0]["numerator"] = True
    with pytest.raises(BenchmarkArtifactError, match="numerator"):
        render_markdown(score)


def test_report_escapes_markdown_table_cells() -> None:
    score = synthetic_score_fixture()
    score["metrics"][0]["uncertainty_result"]["method"] = "method|unsafe"
    rendered = render_markdown(score)
    assert "method\\|unsafe" in rendered
