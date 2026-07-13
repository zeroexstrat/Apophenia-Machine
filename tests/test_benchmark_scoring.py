from __future__ import annotations

import json
import math
import shutil
from copy import deepcopy
from pathlib import Path

import pytest

from athanasor.benchmark.artifacts import BenchmarkArtifactError, artifact_digest, validate_score
from athanasor.benchmark.pipeline import fetch_sources, prepare_benchmark, run_fallback
from athanasor.benchmark.scoring import (
    HUMAN_ANNOTATION_METRICS,
    MetricValue,
    macro_f1,
    ndcg_at_k,
    paired_bootstrap_interval,
    precision_at_k,
    score_run,
    synthetic_gold_commitment,
    wilson_interval,
)
from athanasor.benchmark.protocol import load_mapping
from tests.test_benchmark_pipeline import (
    BENCHMARK_ROOT,
    synthetic_manifest,
    synthetic_responses,
    visible_extractor,
)
from tests.benchmark_fixtures import write_frozen_bundle


def synthetic_run(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    benchmark = tmp_path / "benchmark"
    shutil.copytree(BENCHMARK_ROOT, benchmark)
    manifest = synthetic_manifest()
    sources = tmp_path / "sources"
    fetch_sources(manifest, sources, fetcher=synthetic_responses(manifest).__getitem__)
    prepared = prepare_benchmark(
        benchmark,
        manifest,
        sources,
        tmp_path / "prepared.json",
        extractor=visible_extractor,
    )
    return benchmark, run_fallback(prepared)


def synthetic_gold(run: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "artifact_type": "azoth_synthetic_gold",
        "benchmark_id": "operations-decision-support-v1",
        "synthetic": True,
        "notice": "SYNTHETIC CONTRACT TEST — NOT A PERFORMANCE CLAIM",
        "gold_pairs": [
            {
                "pair_id": row["pair_id"],
                "paper_a_id": row["paper_a_id"],
                "paper_b_id": row["paper_b_id"],
                "label": index % 4,
            }
            for index, row in enumerate(run["results"])
        ],
        "freeze": {"freeze_time": "2026-07-12T00:00:00Z"},
    }


def install_synthetic_commitment(benchmark: Path, gold: dict[str, object]) -> None:
    payload = {
        "schema_version": 1,
        "artifact_type": "azoth_synthetic_gold_commitment",
        "benchmark_id": "operations-decision-support-v1",
        "synthetic": True,
        "notice": "SYNTHETIC CONTRACT TEST — NOT A PERFORMANCE CLAIM",
        "commitment": synthetic_gold_commitment(gold),
    }
    path = benchmark / "synthetic" / "gold-commitment.json"
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def metric_by_name(score: dict[str, object], name: str) -> dict[str, object]:
    return next(row for row in score["metrics"] if row["name"] == name)


def test_macro_f1_uses_all_four_classes() -> None:
    result = macro_f1([0, 1, 2, 3], [0, 1, 1, 3])
    assert isinstance(result, MetricValue)
    assert result.numerator == 3
    assert result.denominator == 4
    assert result.value == pytest.approx((1.0 + 2 / 3 + 0.0 + 1.0) / 4)


def test_macro_f1_is_undefined_when_a_class_has_zero_denominator() -> None:
    result = macro_f1([0, 0], [0, 0])
    assert result.value is None
    assert result.uncertainty["undefined_class"] == 1


def test_precision_at_5_and_ndcg_use_canonical_queries() -> None:
    gold = {("a", "b"): 3, ("a", "c"): 2, ("a", "d"): 0}
    ranked = {"a": ["d", "b", "c"]}
    assert precision_at_k(gold, ranked, k=5).value == pytest.approx(2 / 3)
    assert ndcg_at_k(gold, ranked, k=10).value == pytest.approx(
        (0 + 7 / math.log2(3) + 3 / math.log2(4))
        / (7 + 3 / math.log2(3))
    )


def test_wilson_interval_and_bootstrap_are_deterministic() -> None:
    assert wilson_interval(5, 10) == pytest.approx(
        (0.236593090512564, 0.7634069094874361)
    )
    first = paired_bootstrap_interval([0.0, 1.0, 1.0], lambda rows: sum(rows) / len(rows))
    second = paired_bootstrap_interval([0.0, 1.0, 1.0], lambda rows: sum(rows) / len(rows))
    assert first == second
    assert first is not None and first[0] <= 2 / 3 <= first[1]


def test_score_run_computes_all_frozen_metrics(tmp_path: Path) -> None:
    benchmark, run = synthetic_run(tmp_path)
    gold = synthetic_gold(run)
    install_synthetic_commitment(benchmark, gold)
    score = score_run(benchmark, run, gold)
    protocol = load_mapping(benchmark / "protocol.yaml")
    assert [row["name"] for row in score["metrics"]] == [
        row["name"] for row in protocol["metrics"]
    ]
    assert len(score["metrics"]) == 13
    assert validate_score(score) == []
    for metric, contract in zip(score["metrics"], protocol["metrics"]):
        assert metric["numerator_definition"] == contract["numerator"]
        assert metric["denominator_definition"] == contract["denominator"]


@pytest.mark.parametrize("name", sorted(HUMAN_ANNOTATION_METRICS))
def test_missing_human_population_is_null(tmp_path: Path, name: str) -> None:
    benchmark, run = synthetic_run(tmp_path)
    gold = synthetic_gold(run)
    install_synthetic_commitment(benchmark, gold)
    metric = metric_by_name(score_run(benchmark, run, gold), name)
    assert metric["value"] is None
    assert metric["numerator"] == metric["denominator"] == 0
    assert metric["threshold_met"] is None


def test_complete_human_annotations_populate_review_metrics(tmp_path: Path) -> None:
    benchmark, run = synthetic_run(tmp_path)
    gold = synthetic_gold(run)
    install_synthetic_commitment(benchmark, gold)
    item_ids = [item["item_id"] for row in run["results"] for item in row["items"]]
    annotations = {
        "schema_version": 1,
        "artifact_type": "azoth_benchmark_human_annotations",
        "benchmark_id": run["benchmark_id"],
        "run_sha256": artifact_digest(run),
        "ood_assignments": [{"decision_id": "ood_1", "unsafe": False}],
        "claims": [{"claim_id": "claim_1", "supported": True}],
        "evidence_spans": [{"span_id": "span_1", "supported": True}],
        "items": [
            {
                "item_id": item_id,
                "supported": True,
                "useful": index % 2 == 0,
                "redundant": False,
                "confidence": "derived" if index == 0 else "likely",
            }
            for index, item_id in enumerate(item_ids)
        ],
    }
    score = score_run(benchmark, run, gold, annotations=annotations)
    assert metric_by_name(score, "unsafe_ood_assignment")["value"] == 0.0
    assert metric_by_name(score, "claim_precision")["value"] == 1.0
    assert metric_by_name(score, "evidence_support")["value"] == 1.0
    assert metric_by_name(score, "supported_items")["value"] == 1.0
    assert metric_by_name(score, "unsupported_derived_items")["value"] == 0.0


def test_gold_commitment_mismatch_is_rejected(tmp_path: Path) -> None:
    benchmark, run = synthetic_run(tmp_path)
    gold = synthetic_gold(run)
    install_synthetic_commitment(benchmark, gold)
    tampered = deepcopy(gold)
    tampered["gold_pairs"][0]["label"] = 3
    with pytest.raises(BenchmarkArtifactError, match="commitment"):
        score_run(benchmark, run, tampered)


def test_annotations_must_bind_exact_run_and_known_items(tmp_path: Path) -> None:
    benchmark, run = synthetic_run(tmp_path)
    gold = synthetic_gold(run)
    install_synthetic_commitment(benchmark, gold)
    annotations = {
        "schema_version": 1,
        "artifact_type": "azoth_benchmark_human_annotations",
        "benchmark_id": run["benchmark_id"],
        "run_sha256": "0" * 64,
        "items": [{"item_id": "unknown", "supported": True, "useful": True, "redundant": False, "confidence": "derived"}],
        "ood_assignments": [],
        "claims": [],
        "evidence_spans": [],
    }
    with pytest.raises(BenchmarkArtifactError, match="run_sha256"):
        score_run(benchmark, run, gold, annotations=annotations)


def test_real_gold_path_validates_exact_p5_commitment(tmp_path: Path) -> None:
    benchmark, gold_path, _source_dir, _repo = write_frozen_bundle(tmp_path)
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    results = []
    for index, pair in enumerate(gold["gold_pairs"]):
        results.append(
            {
                "pair_id": pair["pair_id"],
                "paper_a_id": pair["paper_a_id"],
                "paper_b_id": pair["paper_b_id"],
                "predicted_label": pair["label"],
                "candidate": pair["label"] in (2, 3),
                "score": pair["label"] / 3,
                "rank_a": 1,
                "rank_b": 1,
                "items": [],
                "status": "pending_review",
            }
        )
    by_paper: dict[str, list[tuple[float, dict[str, object], str]]] = {}
    for row in results:
        by_paper.setdefault(row["paper_a_id"], []).append((row["score"], row, "rank_a"))
        by_paper.setdefault(row["paper_b_id"], []).append((row["score"], row, "rank_b"))
    for rows in by_paper.values():
        for rank, (_score, row, field) in enumerate(
            sorted(rows, key=lambda value: (-value[0], value[1]["pair_id"])), start=1
        ):
            row[field] = rank
    run = {
        "schema_version": 1,
        "artifact_type": "azoth_benchmark_run",
        "benchmark_id": "operations-decision-support-v1",
        "synthetic": False,
        "prepared_sha256": "1" * 64,
        "backend": {"name": "locked_fixture", "version": 1},
        "seed": 5607,
        "results": results,
        "status": "locked",
    }
    score = score_run(benchmark, run, gold)
    assert score["gold_commitment"] == load_mapping(benchmark / "freeze-manifest.json")[
        "private_gold_commitment"
    ]
    assert score["synthetic"] is False


def test_human_annotations_fail_closed_on_types_and_duplicate_ids(tmp_path: Path) -> None:
    benchmark, run = synthetic_run(tmp_path)
    gold = synthetic_gold(run)
    install_synthetic_commitment(benchmark, gold)
    annotations = {
        "schema_version": 1,
        "artifact_type": "azoth_benchmark_human_annotations",
        "benchmark_id": run["benchmark_id"],
        "run_sha256": artifact_digest(run),
        "ood_assignments": [{"decision_id": "ood_1", "unsafe": "no"}],
        "claims": [
            {"claim_id": "claim_1", "supported": True},
            {"claim_id": "claim_1", "supported": False},
        ],
        "evidence_spans": [],
        "items": [],
    }
    with pytest.raises(BenchmarkArtifactError, match="unsafe|duplicate"):
        score_run(benchmark, run, gold, annotations=annotations)


def test_human_annotations_require_exact_artifact_contract(tmp_path: Path) -> None:
    benchmark, run = synthetic_run(tmp_path)
    gold = synthetic_gold(run)
    install_synthetic_commitment(benchmark, gold)
    annotations = {
        "schema_version": 1,
        "artifact_type": "wrong",
        "benchmark_id": run["benchmark_id"],
        "run_sha256": artifact_digest(run),
        "ood_assignments": [],
        "claims": [],
        "evidence_spans": [],
        "items": [],
    }
    with pytest.raises(BenchmarkArtifactError, match="artifact_type"):
        score_run(benchmark, run, gold, annotations=annotations)
