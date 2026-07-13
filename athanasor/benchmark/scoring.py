from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from athanasor.benchmark.artifacts import (
    SCORE_TYPE,
    SYNTHETIC_NOTICE,
    BenchmarkArtifactError,
    artifact_digest,
    validate_run,
    validate_score,
)
from athanasor.benchmark.freeze import gold_commitment, validate_gold_packet
from athanasor.benchmark.protocol import (
    BENCHMARK_ID,
    canonical_digest,
    load_mapping,
    validate_public_bundle,
)


HUMAN_ANNOTATION_METRICS = frozenset(
    {
        "unsafe_ood_assignment",
        "claim_precision",
        "evidence_support",
        "supported_items",
        "useful_items",
        "redundancy",
        "unsupported_derived_items",
    }
)


@dataclass(frozen=True)
class MetricValue:
    numerator: int | float
    denominator: int | float
    value: float | None
    uncertainty: dict[str, Any]


def _numeric_label(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value not in range(4):
        raise BenchmarkArtifactError(f"{path}: expected integer label 0-3")
    return value


def macro_f1(gold_labels: Sequence[int], predicted_labels: Sequence[int]) -> MetricValue:
    if len(gold_labels) != len(predicted_labels) or not gold_labels:
        return MetricValue(0, 0, None, {"reason": "empty or unequal label arrays"})
    scores: list[float] = []
    for label in range(4):
        true_positive = sum(gold == predicted == label for gold, predicted in zip(gold_labels, predicted_labels))
        false_positive = sum(gold != label and predicted == label for gold, predicted in zip(gold_labels, predicted_labels))
        false_negative = sum(gold == label and predicted != label for gold, predicted in zip(gold_labels, predicted_labels))
        denominator = 2 * true_positive + false_positive + false_negative
        if denominator == 0:
            return MetricValue(
                sum(gold == predicted for gold, predicted in zip(gold_labels, predicted_labels)),
                len(gold_labels),
                None,
                {"undefined_class": label},
            )
        scores.append(2 * true_positive / denominator)
    return MetricValue(
        sum(gold == predicted for gold, predicted in zip(gold_labels, predicted_labels)),
        len(gold_labels),
        sum(scores) / 4,
        {},
    )


def wilson_interval(
    numerator: int, denominator: int, confidence: float = 0.95
) -> tuple[float, float] | None:
    if denominator <= 0:
        return None
    if numerator < 0 or numerator > denominator:
        raise BenchmarkArtifactError("Wilson numerator must be between zero and denominator")
    if confidence != 0.95:
        raise BenchmarkArtifactError("only the frozen 95% Wilson interval is supported")
    z = 1.959963984540054
    proportion = numerator / denominator
    scale = 1 + z * z / denominator
    center = (proportion + z * z / (2 * denominator)) / scale
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / denominator
            + z * z / (4 * denominator * denominator)
        )
        / scale
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def paired_bootstrap_interval(
    observations: Sequence[Any],
    statistic: Callable[[Sequence[Any]], float | None],
    *,
    seed: int = 5607,
    samples: int = 2000,
) -> tuple[float, float] | None:
    if not observations:
        return None
    if samples <= 0:
        raise BenchmarkArtifactError("bootstrap samples must be positive")
    generator = random.Random(seed)
    values: list[float] = []
    size = len(observations)
    for _ in range(samples):
        sample = [observations[generator.randrange(size)] for _ in range(size)]
        value = statistic(sample)
        if value is not None and math.isfinite(value):
            values.append(float(value))
    if not values:
        return None
    return _percentile(values, 0.025), _percentile(values, 0.975)


def _pair_label(gold: Mapping[tuple[str, str], int], first: str, second: str) -> int:
    return int(gold.get(tuple(sorted((first, second))), 0))


def _precision_query_values(
    gold: Mapping[tuple[str, str], int], ranked: Mapping[str, Sequence[str]], k: int
) -> tuple[list[float], int, int]:
    values: list[float] = []
    numerator = 0
    denominator = 0
    papers = sorted(ranked)
    for query in papers:
        relevant = {
            second if first == query else first
            for (first, second), label in gold.items()
            if query in (first, second) and label in (2, 3)
        }
        if not relevant:
            continue
        results = list(ranked.get(query, ()))[:k]
        if not results:
            continue
        hits = sum(target in relevant for target in results)
        numerator += hits
        denominator += len(results)
        values.append(hits / len(results))
    return values, numerator, denominator


def precision_at_k(
    gold: Mapping[tuple[str, str], int], ranked: Mapping[str, Sequence[str]], *, k: int
) -> MetricValue:
    values, numerator, denominator = _precision_query_values(gold, ranked, k)
    return MetricValue(
        numerator,
        denominator,
        sum(values) / len(values) if values else None,
        {},
    )


def _ndcg_query_values(
    gold: Mapping[tuple[str, str], int], ranked: Mapping[str, Sequence[str]], k: int
) -> tuple[list[float], float, float]:
    values: list[float] = []
    total_dcg = 0.0
    total_ideal = 0.0
    papers = sorted(ranked)
    for query in papers:
        labels = [label for pair, label in gold.items() if query in pair]
        ideal_labels = sorted(labels, reverse=True)[:k]
        ideal = sum((2**label - 1) / math.log2(index + 2) for index, label in enumerate(ideal_labels))
        if ideal <= 0:
            continue
        results = list(ranked.get(query, ()))[:k]
        dcg = sum(
            (2 ** _pair_label(gold, query, target) - 1) / math.log2(index + 2)
            for index, target in enumerate(results)
        )
        total_dcg += dcg
        total_ideal += ideal
        values.append(dcg / ideal)
    return values, total_dcg, total_ideal


def ndcg_at_k(
    gold: Mapping[tuple[str, str], int], ranked: Mapping[str, Sequence[str]], *, k: int
) -> MetricValue:
    values, numerator, denominator = _ndcg_query_values(gold, ranked, k)
    return MetricValue(
        numerator,
        denominator,
        sum(values) / len(values) if values else None,
        {},
    )


def synthetic_gold_commitment(gold: dict[str, Any]) -> dict[str, Any]:
    pairs = gold.get("gold_pairs")
    if not isinstance(pairs, list) or not pairs:
        raise BenchmarkArtifactError("synthetic gold requires nonempty gold_pairs")
    freeze = gold.get("freeze")
    freeze_time = freeze.get("freeze_time") if isinstance(freeze, dict) else None
    if not isinstance(freeze_time, str):
        raise BenchmarkArtifactError("synthetic gold requires freeze_time")
    committed = {
        "benchmark_id": gold.get("benchmark_id"),
        "artifact_type": gold.get("artifact_type"),
        "gold_pairs": sorted(pairs, key=lambda row: row.get("pair_id", "")),
        "freeze_time": freeze_time,
        "synthetic": gold.get("synthetic"),
    }
    return {
        "algorithm": "sha256-canonical-json-v1",
        "private_gold_sha256": canonical_digest(committed),
        "schema_version": 1,
        "freeze_time": freeze_time,
    }


def _validate_synthetic_gold(gold: Any, run: dict[str, Any]) -> list[str]:
    if not isinstance(gold, dict):
        return ["/: expected object"]
    errors: list[str] = []
    expected = {
        "schema_version": 1,
        "artifact_type": "azoth_synthetic_gold",
        "benchmark_id": BENCHMARK_ID,
        "synthetic": True,
        "notice": SYNTHETIC_NOTICE,
    }
    for field, value in expected.items():
        if gold.get(field) != value:
            errors.append(f"/{field}: expected {value}")
    rows = gold.get("gold_pairs")
    if not isinstance(rows, list):
        return errors + ["/gold_pairs: expected array"]
    expected_rows = {row["pair_id"]: row for row in run["results"]}
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"/gold_pairs/{index}: expected object")
            continue
        identifier = row.get("pair_id")
        if identifier in seen:
            errors.append(f"/gold_pairs/{index}/pair_id: duplicate")
        elif identifier not in expected_rows:
            errors.append(f"/gold_pairs/{index}/pair_id: unknown pair")
        else:
            seen.add(identifier)
            expected_run = expected_rows[identifier]
            for field in ("paper_a_id", "paper_b_id"):
                if row.get(field) != expected_run[field]:
                    errors.append(f"/gold_pairs/{index}/{field}: does not match run")
        try:
            _numeric_label(row.get("label"), f"/gold_pairs/{index}/label")
        except BenchmarkArtifactError as exc:
            errors.append(str(exc))
    if seen != set(expected_rows):
        errors.append("/gold_pairs: exact run pair coverage required")
    return sorted(errors)


def _load_and_validate_commitment(
    benchmark_root: Path, run: dict[str, Any], gold: dict[str, Any]
) -> dict[str, Any]:
    if run.get("synthetic") is True:
        errors = _validate_synthetic_gold(gold, run)
        if errors:
            raise BenchmarkArtifactError("invalid synthetic gold: " + "; ".join(errors))
        commitment_path = benchmark_root / "synthetic" / "gold-commitment.json"
        try:
            expected_payload = json.loads(commitment_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BenchmarkArtifactError(f"cannot read synthetic gold commitment: {exc}") from None
        expected = expected_payload.get("commitment") if isinstance(expected_payload, dict) else None
        actual = synthetic_gold_commitment(gold)
    else:
        sources = load_mapping(benchmark_root / "sources.yaml")
        protocol = load_mapping(benchmark_root / "protocol.yaml")
        errors = validate_gold_packet(gold, sources, protocol)
        if errors:
            raise BenchmarkArtifactError("invalid private gold: " + "; ".join(sorted(errors)))
        expected = load_mapping(benchmark_root / "freeze-manifest.json").get(
            "private_gold_commitment"
        )
        actual = gold_commitment(gold)
    if actual != expected:
        raise BenchmarkArtifactError("private gold commitment does not match frozen benchmark")
    return actual


def _ranked_results(run: dict[str, Any]) -> dict[str, list[str]]:
    ranked_rows: dict[str, list[tuple[int, str]]] = {}
    for row in run["results"]:
        ranked_rows.setdefault(row["paper_a_id"], []).append((int(row["rank_a"]), row["paper_b_id"]))
        ranked_rows.setdefault(row["paper_b_id"], []).append((int(row["rank_b"]), row["paper_a_id"]))
    return {
        query: [target for _rank, target in sorted(rows)]
        for query, rows in ranked_rows.items()
    }


def _micro(values: Sequence[bool]) -> MetricValue:
    numerator = sum(values)
    denominator = len(values)
    interval = wilson_interval(numerator, denominator)
    return MetricValue(
        numerator,
        denominator,
        numerator / denominator if denominator else None,
        {
            "method": "Wilson 95% interval",
            "lower": interval[0] if interval else None,
            "upper": interval[1] if interval else None,
        },
    )


def _validate_annotations(annotations: Any, run: dict[str, Any]) -> dict[str, Any]:
    if annotations is None:
        return {"ood_assignments": [], "claims": [], "evidence_spans": [], "items": []}
    if not isinstance(annotations, dict):
        raise BenchmarkArtifactError("annotations: expected object")
    expected_top = {
        "schema_version",
        "artifact_type",
        "benchmark_id",
        "run_sha256",
        "ood_assignments",
        "claims",
        "evidence_spans",
        "items",
    }
    unexpected_top = sorted(set(annotations) - expected_top)
    if unexpected_top:
        raise BenchmarkArtifactError(
            f"/annotations/{unexpected_top[0]}: unexpected field"
        )
    if annotations.get("schema_version") != 1:
        raise BenchmarkArtifactError("/annotations/schema_version: expected 1")
    if annotations.get("artifact_type") != "azoth_benchmark_human_annotations":
        raise BenchmarkArtifactError(
            "/annotations/artifact_type: expected azoth_benchmark_human_annotations"
        )
    if annotations.get("run_sha256") != artifact_digest(run):
        raise BenchmarkArtifactError("/annotations/run_sha256: does not match locked run")
    if annotations.get("benchmark_id") != BENCHMARK_ID:
        raise BenchmarkArtifactError(f"/annotations/benchmark_id: expected {BENCHMARK_ID}")
    known_items = {
        item.get("item_id")
        for row in run["results"]
        for item in row.get("items", [])
        if isinstance(item, dict)
    }
    for field in ("ood_assignments", "claims", "evidence_spans", "items"):
        if not isinstance(annotations.get(field), list):
            raise BenchmarkArtifactError(f"/annotations/{field}: expected array")
    row_contracts = {
        "ood_assignments": ("decision_id", {"decision_id", "unsafe"}, ("unsafe",)),
        "claims": ("claim_id", {"claim_id", "supported"}, ("supported",)),
        "evidence_spans": ("span_id", {"span_id", "supported"}, ("supported",)),
        "items": (
            "item_id",
            {"item_id", "supported", "useful", "redundant", "confidence"},
            ("supported", "useful", "redundant"),
        ),
    }
    for field, (id_field, allowed, boolean_fields) in row_contracts.items():
        seen: set[str] = set()
        for index, row in enumerate(annotations[field]):
            if not isinstance(row, dict):
                raise BenchmarkArtifactError(f"/annotations/{field}/{index}: expected object")
            unexpected = sorted(set(row) - allowed)
            if unexpected:
                raise BenchmarkArtifactError(
                    f"/annotations/{field}/{index}/{unexpected[0]}: unexpected field"
                )
            identifier = row.get(id_field)
            if not isinstance(identifier, str) or not identifier:
                raise BenchmarkArtifactError(
                    f"/annotations/{field}/{index}/{id_field}: expected nonempty string"
                )
            if identifier in seen:
                raise BenchmarkArtifactError(
                    f"/annotations/{field}/{index}/{id_field}: duplicate"
                )
            seen.add(identifier)
            for boolean_field in boolean_fields:
                if not isinstance(row.get(boolean_field), bool):
                    raise BenchmarkArtifactError(
                        f"/annotations/{field}/{index}/{boolean_field}: expected boolean"
                    )
            if field == "items" and row.get("confidence") not in {
                "derived",
                "likely",
                "speculative",
            }:
                raise BenchmarkArtifactError(
                    f"/annotations/items/{index}/confidence: expected derived, likely, or speculative"
                )
    seen_items: set[str] = set()
    for index, item in enumerate(annotations["items"]):
        identifier = item.get("item_id") if isinstance(item, dict) else None
        if identifier not in known_items:
            raise BenchmarkArtifactError(f"/annotations/items/{index}/item_id: unknown run item")
        if identifier in seen_items:
            raise BenchmarkArtifactError(f"/annotations/items/{index}/item_id: duplicate")
        seen_items.add(identifier)
    return annotations


def _threshold_met(value: float | None, threshold: Mapping[str, Any]) -> bool | None:
    if value is None:
        return None
    operator = threshold["operator"]
    target = float(threshold["value"])
    if operator == ">=":
        return value >= target
    if operator == "<=":
        return value <= target
    if operator == "==":
        return math.isclose(value, target, rel_tol=0.0, abs_tol=1e-12)
    raise BenchmarkArtifactError(f"unknown threshold operator {operator}")


def _bootstrap_record(interval: tuple[float, float] | None, seed: int) -> dict[str, Any]:
    return {
        "method": "paired bootstrap 95% interval",
        "seed": seed,
        "samples": 2000,
        "lower": interval[0] if interval else None,
        "upper": interval[1] if interval else None,
    }


def score_run(
    benchmark_root: Path,
    run: dict[str, Any],
    gold: dict[str, Any],
    *,
    annotations: dict[str, Any] | None = None,
    bootstrap_seed: int = 5607,
    verified_lock: dict[str, Any] | None = None,
    lock_private_root: Path | None = None,
    execution_manifest: dict[str, Any] | None = None,
    expected_git_sha: str | None = None,
) -> dict[str, Any]:
    root = Path(benchmark_root)
    public_errors = validate_public_bundle(root)
    if public_errors:
        raise BenchmarkArtifactError("invalid public benchmark: " + "; ".join(sorted(public_errors)))
    run_errors = validate_run(run)
    if run_errors:
        raise BenchmarkArtifactError("invalid run artifact: " + "; ".join(run_errors))
    from athanasor.benchmark.evaluation import (
        validate_annotation_packet,
        verify_p7_score_lock,
    )

    p7_binding = verify_p7_score_lock(
        run,
        benchmark_root=root,
        verified_lock=verified_lock,
        lock_private_root=lock_private_root,
        execution_manifest=execution_manifest,
        expected_git_sha=expected_git_sha,
    )
    commitment = _load_and_validate_commitment(root, run, gold)
    if p7_binding is not None and any(row.get("items") for row in run["results"]):
        if annotations is None:
            raise BenchmarkArtifactError("P7 model run requires complete human annotations")
        annotation_errors = validate_annotation_packet(
            annotations, run, verified_lock, require_complete=True
        )
        if annotation_errors:
            raise BenchmarkArtifactError(
                "invalid P7 human annotations: " + "; ".join(annotation_errors)
            )
        annotations_payload = annotations
    elif p7_binding is not None and annotations is not None:
        annotation_errors = validate_annotation_packet(
            annotations, run, verified_lock, require_complete=True
        )
        if annotation_errors:
            raise BenchmarkArtifactError(
                "invalid P7 human annotations: " + "; ".join(annotation_errors)
            )
        annotations_payload = annotations
    else:
        annotations_payload = _validate_annotations(annotations, run)
    gold_rows = {row["pair_id"]: row for row in gold["gold_pairs"]}
    if set(gold_rows) != {row["pair_id"] for row in run["results"]}:
        raise BenchmarkArtifactError("gold and run require exact pair coverage")
    run_rows = sorted(run["results"], key=lambda row: row["pair_id"])
    gold_labels = [_numeric_label(gold_rows[row["pair_id"]]["label"], "/gold_pairs/label") for row in run_rows]
    predictions = [_numeric_label(row["predicted_label"], "/results/predicted_label") for row in run_rows]
    gold_by_papers = {
        tuple(sorted((row["paper_a_id"], row["paper_b_id"]))): int(row["label"])
        for row in gold_rows.values()
    }
    relevant = [label in (2, 3) for label in gold_labels]
    candidates = [bool(row["candidate"]) for row in run_rows]
    predicted_relevant = [label in (2, 3) for label in predictions]

    values: dict[str, MetricValue] = {}
    macro = macro_f1(gold_labels, predictions)
    macro_observations = list(zip(gold_labels, predictions))
    macro_interval = paired_bootstrap_interval(
        macro_observations,
        lambda rows: macro_f1([row[0] for row in rows], [row[1] for row in rows]).value,
        seed=bootstrap_seed,
    )
    values["macro_f1"] = MetricValue(
        macro.numerator,
        macro.denominator,
        macro.value,
        _bootstrap_record(macro_interval, bootstrap_seed) | macro.uncertainty,
    )
    relevant_count = sum(relevant)
    values["reference_recall"] = _micro(
        [predicted_relevant[index] for index, is_relevant in enumerate(relevant) if is_relevant]
    )
    values["candidate_recall"] = _micro(
        [candidates[index] for index, is_relevant in enumerate(relevant) if is_relevant]
    )
    excluded = [not candidate for candidate in candidates]
    workload_interval = paired_bootstrap_interval(
        excluded,
        lambda rows: sum(rows) / len(rows) if rows else None,
        seed=bootstrap_seed,
    )
    values["workload_reduction"] = MetricValue(
        sum(excluded),
        len(excluded),
        sum(excluded) / len(excluded) if excluded else None,
        _bootstrap_record(workload_interval, bootstrap_seed),
    )
    ranked = _ranked_results(run)
    precision = precision_at_k(gold_by_papers, ranked, k=5)
    precision_values, _, _ = _precision_query_values(gold_by_papers, ranked, 5)
    values["precision_at_5"] = MetricValue(
        precision.numerator,
        precision.denominator,
        precision.value,
        _bootstrap_record(
            paired_bootstrap_interval(
                precision_values,
                lambda rows: sum(rows) / len(rows) if rows else None,
                seed=bootstrap_seed,
            ),
            bootstrap_seed,
        ),
    )
    ndcg = ndcg_at_k(gold_by_papers, ranked, k=10)
    ndcg_values, _, _ = _ndcg_query_values(gold_by_papers, ranked, 10)
    values["ndcg_at_10"] = MetricValue(
        ndcg.numerator,
        ndcg.denominator,
        ndcg.value,
        _bootstrap_record(
            paired_bootstrap_interval(
                ndcg_values,
                lambda rows: sum(rows) / len(rows) if rows else None,
                seed=bootstrap_seed,
            ),
            bootstrap_seed,
        ),
    )

    values["unsafe_ood_assignment"] = _micro(
        [bool(row.get("unsafe")) for row in annotations_payload["ood_assignments"]]
    )
    values["claim_precision"] = _micro(
        [bool(row.get("supported")) for row in annotations_payload["claims"]]
    )
    values["evidence_support"] = _micro(
        [bool(row.get("supported")) for row in annotations_payload["evidence_spans"]]
    )
    item_annotations = annotations_payload["items"]
    values["supported_items"] = _micro([bool(row.get("supported")) for row in item_annotations])
    values["useful_items"] = _micro([bool(row.get("useful")) for row in item_annotations])
    values["redundancy"] = _micro([bool(row.get("redundant")) for row in item_annotations])
    derived = [row for row in item_annotations if row.get("confidence") == "derived"]
    values["unsupported_derived_items"] = _micro(
        [not bool(row.get("supported")) for row in derived]
    )

    protocol = load_mapping(root / "protocol.yaml")
    metrics: list[dict[str, Any]] = []
    for contract in protocol["metrics"]:
        name = contract["name"]
        calculated = values[name]
        frozen_contract = dict(contract)
        numerator_definition = frozen_contract.pop("numerator")
        denominator_definition = frozen_contract.pop("denominator")
        metrics.append(
            {
                **frozen_contract,
                "numerator_definition": numerator_definition,
                "denominator_definition": denominator_definition,
                "numerator": calculated.numerator,
                "denominator": calculated.denominator,
                "value": calculated.value,
                "uncertainty_result": calculated.uncertainty,
                "threshold_met": _threshold_met(calculated.value, contract["threshold"]),
            }
        )
    score = {
        "schema_version": 1,
        "artifact_type": SCORE_TYPE,
        "benchmark_id": BENCHMARK_ID,
        "synthetic": run["synthetic"],
        "run_sha256": artifact_digest(run),
        "gold_commitment": commitment,
        "annotation_sha256": artifact_digest(annotations_payload) if annotations is not None else None,
        "calculation": {
            "version": 1,
            "bootstrap_seed": bootstrap_seed,
            "bootstrap_samples": 2000,
        },
        "metrics": metrics,
        "status": "scored",
    }
    if run["synthetic"]:
        score["notice"] = SYNTHETIC_NOTICE
    if p7_binding is not None:
        score.update(p7_binding)
    score_errors = validate_score(score)
    if score_errors:
        raise BenchmarkArtifactError("invalid score artifact: " + "; ".join(score_errors))
    return score
