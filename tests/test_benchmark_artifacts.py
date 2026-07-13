from __future__ import annotations

import hashlib
import json
from itertools import combinations
from copy import deepcopy
from pathlib import Path

import pytest

from athanasor.benchmark.artifacts import (
    BenchmarkArtifactError,
    PREPARED_TYPE,
    RUN_TYPE,
    SCORE_TYPE,
    artifact_digest,
    atomic_write_json,
    ensure_outside_repository,
    read_json_artifact,
    validate_prepared,
    validate_run,
    validate_score,
)
from athanasor.benchmark.protocol import (
    EXPECTED_P5_METRIC_CONTRACTS,
    EXPECTED_P5_THRESHOLDS,
    pair_id,
)


def prepared_fixture() -> dict[str, object]:
    paper_ids = [f"paper_{index:016x}" for index in range(1, 7)]
    packets = []
    for first, second in combinations(paper_ids, 2):
        identifier = pair_id(first, second)
        packets.append(
            {
                "schema_version": 1,
                "benchmark_id": "operations-decision-support-v1",
                "packet_id": f"packet_{identifier.split('_', 1)[1]}",
                "pair_id": identifier,
                "paper_a_id": first,
                "paper_b_id": second,
                "sources": [{"paper_id": first}, {"paper_id": second}],
                "status": "pending_review",
            }
        )
    return {
        "schema_version": 1,
        "artifact_type": PREPARED_TYPE,
        "benchmark_id": "operations-decision-support-v1",
        "synthetic": True,
        "notice": "SYNTHETIC CONTRACT TEST — NOT A PERFORMANCE CLAIM",
        "provenance": {
            "source_manifest_sha256": "1" * 64,
            "protocol_sha256": "2" * 64,
            "prompt_sha256": "3" * 64,
            "blinded_schema_sha256": "4" * 64,
            "freeze_manifest_sha256": "5" * 64,
        },
        "packets": packets,
        "status": "prepared",
    }


def run_fixture() -> dict[str, object]:
    prepared = prepared_fixture()
    results = []
    for index, packet in enumerate(prepared["packets"]):
        results.append(
            {
                "pair_id": packet["pair_id"],
                "paper_a_id": packet["paper_a_id"],
                "paper_b_id": packet["paper_b_id"],
                "predicted_label": index % 4,
                "candidate": index % 4 >= 2,
                "score": index / 15,
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
        for rank, (_score, row, field) in enumerate(sorted(rows, key=lambda value: -value[0]), start=1):
            row[field] = rank
    return {
        "schema_version": 1,
        "artifact_type": RUN_TYPE,
        "benchmark_id": "operations-decision-support-v1",
        "synthetic": True,
        "notice": "SYNTHETIC CONTRACT TEST — NOT A PERFORMANCE CLAIM",
        "prepared_sha256": artifact_digest(prepared),
        "backend": {"name": "deterministic_hash_fallback", "version": 1},
        "seed": 5607,
        "results": results,
        "status": "locked",
    }


def score_fixture() -> dict[str, object]:
    metrics = []
    for name, contract in EXPECTED_P5_METRIC_CONTRACTS.items():
        metric = dict(contract)
        metric["name"] = name
        metric["numerator_definition"] = metric.pop("numerator")
        metric["denominator_definition"] = metric.pop("denominator")
        compatible_value = 0.0 if metric["comparison"] in {"==", "<="} else 1.0
        metric.update(
            {
                "numerator": int(compatible_value),
                "denominator": 1,
                "value": compatible_value,
                "uncertainty_result": {
                    "method": "synthetic exact",
                    "lower": compatible_value,
                    "upper": compatible_value,
                },
                "threshold_met": True,
            }
        )
        metrics.append(metric)
    return {
        "schema_version": 1,
        "artifact_type": SCORE_TYPE,
        "benchmark_id": "operations-decision-support-v1",
        "synthetic": True,
        "notice": "SYNTHETIC CONTRACT TEST — NOT A PERFORMANCE CLAIM",
        "run_sha256": "6" * 64,
        "gold_commitment": {"private_gold_sha256": "7" * 64},
        "calculation": {"version": 1, "bootstrap_seed": 5607},
        "metrics": metrics,
        "status": "scored",
    }


def test_atomic_json_is_canonical_and_refuses_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "artifact.json"
    digest = atomic_write_json(target, {"schema_version": 1, "b": 2, "a": 1})
    assert target.read_bytes() == b'{"a":1,"b":2,"schema_version":1}\n'
    assert digest == hashlib.sha256(target.read_bytes()[:-1]).hexdigest()
    with pytest.raises(BenchmarkArtifactError, match="already exists"):
        atomic_write_json(target, {"schema_version": 1})


def test_atomic_json_force_replaces_and_can_be_read(tmp_path: Path) -> None:
    target = tmp_path / "artifact.json"
    atomic_write_json(target, {"schema_version": 1, "value": 1})
    atomic_write_json(target, {"schema_version": 1, "value": 2}, force=True)
    assert read_json_artifact(target) == {"schema_version": 1, "value": 2}


def test_read_json_artifact_requires_object_and_expected_type(tmp_path: Path) -> None:
    path = tmp_path / "value.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(BenchmarkArtifactError, match="expected object"):
        read_json_artifact(path)
    path.write_text(json.dumps(prepared_fixture()), encoding="utf-8")
    with pytest.raises(BenchmarkArtifactError, match="artifact_type"):
        read_json_artifact(path, artifact_type=RUN_TYPE)


def test_repository_boundary_resolves_symlink_alias(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(repo, target_is_directory=True)
    with pytest.raises(BenchmarkArtifactError, match="outside the repository"):
        ensure_outside_repository(alias / "private", repo, label="private root")
    external = tmp_path / "external"
    assert ensure_outside_repository(external, repo, label="private root") == external.resolve()


@pytest.mark.parametrize("field", ["gold_label", "gold_rationale", "target_thresholds"])
def test_generation_artifacts_reject_gold_fields_recursively(field: str) -> None:
    payload = prepared_fixture()
    packet = payload["packets"][0]  # type: ignore[index]
    packet["sources"][0]["nested"] = {field: 2}  # type: ignore[index]
    assert any(field in error for error in validate_prepared(payload))


def test_prepared_requires_unique_canonical_pair_rows() -> None:
    payload = prepared_fixture()
    payload["packets"].append(deepcopy(payload["packets"][0]))  # type: ignore[union-attr,index]
    assert any("duplicate pair_id" in error for error in validate_prepared(payload))


def test_prepared_requires_all_15_synthetic_pairs() -> None:
    payload = prepared_fixture()
    payload["packets"].pop()  # type: ignore[union-attr]
    assert any("expected exactly 15" in error for error in validate_prepared(payload))


def test_run_rejects_invalid_labels_and_duplicate_pairs() -> None:
    payload = run_fixture()
    payload["results"][0]["predicted_label"] = 4  # type: ignore[index]
    payload["results"].append(deepcopy(payload["results"][0]))  # type: ignore[union-attr,index]
    errors = validate_run(payload)
    assert any("predicted_label" in error for error in errors)
    assert any("duplicate pair_id" in error for error in errors)


def test_run_requires_complete_pair_coverage_and_integer_ranks() -> None:
    payload = run_fixture()
    payload["results"].pop()  # type: ignore[union-attr]
    payload["results"][0]["rank_a"] = 1.5  # type: ignore[index]
    errors = validate_run(payload)
    assert any("expected exactly 15" in error for error in errors)
    assert any("rank_a" in error for error in errors)


def test_score_rejects_boolean_numeric_values() -> None:
    payload = score_fixture()
    payload["metrics"][0]["numerator"] = True  # type: ignore[index]
    assert any("numerator" in error for error in validate_score(payload))


def test_score_requires_all_13_frozen_metrics() -> None:
    payload = score_fixture()
    payload["metrics"].pop()  # type: ignore[union-attr]
    assert any("exact frozen metric names" in error for error in validate_score(payload))


def test_score_rejects_frozen_metric_contract_tamper() -> None:
    payload = score_fixture()
    payload["metrics"][0]["population"] = "changed after freeze"  # type: ignore[index]
    assert any("population" in error for error in validate_score(payload))


def test_score_rejects_inconsistent_threshold_outcome() -> None:
    payload = score_fixture()
    payload["metrics"][0]["value"] = 0.0  # type: ignore[index]
    payload["metrics"][0]["threshold_met"] = True  # type: ignore[index]
    assert any("threshold_met" in error for error in validate_score(payload))


def test_valid_minimal_artifacts_pass() -> None:
    assert validate_prepared(prepared_fixture()) == []
    assert validate_run(run_fixture()) == []
    assert validate_score(score_fixture()) == []
