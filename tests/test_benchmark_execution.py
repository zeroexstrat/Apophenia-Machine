from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from athanasor.benchmark.artifacts import BenchmarkArtifactError, validate_run
from athanasor.benchmark.execution import (
    RUN_IDS,
    adapt_model_responses,
    generate_baseline,
    load_execution_manifest,
    validate_model_response,
    validate_execution_manifest,
)
from athanasor.benchmark.pipeline import FetchResponse, fetch_sources, prepare_benchmark
from athanasor.benchmark.protocol import FORBIDDEN_GOLD_FIELDS, canonical_json_bytes, load_mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = REPO_ROOT / "benchmarks" / "operations-decision-support-v1"
SYNTHETIC_ROOT = BENCHMARK_ROOT / "synthetic"


def _recursive_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(_recursive_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_recursive_keys(child))
    return keys


def _prepared_fixture(tmp_path: Path) -> dict[str, object]:
    manifest = load_mapping(SYNTHETIC_ROOT / "sources.yaml")
    responses: dict[str, FetchResponse] = {}
    for source in manifest["sources"]:
        source["download_url"] = f"https://example.invalid/{source['paper_id']}"
        source["canonical_url"] = source["download_url"]
        source["publication_date"] = "2026-01-01"
        source["access_date"] = "2026-07-12"
        source["license_evidence_url"] = "https://example.invalid/license"
        responses[source["download_url"]] = FetchResponse(
            body=source["source_text"].encode("utf-8"),
            requested_url=source["download_url"],
            redirect_chain=(source["download_url"],),
            final_url=source["download_url"],
            media_type="application/pdf",
        )
    source_root = tmp_path / "sources"
    fetch_sources(manifest, source_root, fetcher=responses.__getitem__)

    def extractor(body: bytes, source: dict[str, object]) -> dict[str, object]:
        text = body.decode("utf-8")
        return {
            "abstract": text,
            "extracted_record": {"visible_field": "source_text", "visible_text": text},
            "claims": list(source["claims"]),
            "methods": [f"Synthetic method for {source['stable_identifier']}"],
            "caveats": ["Synthetic fixture only."],
            "tags": [str(source["lane"])],
            "explicit_citations": [],
        }

    return prepare_benchmark(
        BENCHMARK_ROOT,
        manifest,
        source_root,
        tmp_path / "prepared.json",
        extractor=extractor,
    )


def test_live_execution_manifest_binds_public_freeze_before_runs() -> None:
    payload = load_execution_manifest(BENCHMARK_ROOT / "execution-manifest.yaml")
    assert validate_execution_manifest(payload, BENCHMARK_ROOT) == []
    assert payload["status"] == "frozen_before_real_runs"
    assert payload["seed"] == 5607
    assert [row["run_id"] for row in payload["runs"]] == list(RUN_IDS)


def test_manifest_rejects_formula_drift() -> None:
    payload = load_execution_manifest(BENCHMARK_ROOT / "execution-manifest.yaml")
    changed = deepcopy(payload)
    changed["baselines"]["shared_tag"]["candidate_rule"] = "always"
    assert any(
        "/baselines/shared_tag/candidate_rule" in error
        for error in validate_execution_manifest(changed, BENCHMARK_ROOT)
    )


def test_manifest_rejects_public_digest_drift() -> None:
    payload = load_execution_manifest(BENCHMARK_ROOT / "execution-manifest.yaml")
    changed = deepcopy(payload)
    changed["public_contracts"]["freeze_manifest_sha256"] = "0" * 64
    assert any(
        "/public_contracts/freeze_manifest_sha256" in error
        for error in validate_execution_manifest(changed, BENCHMARK_ROOT)
    )


def test_manifest_rejects_unknown_fields_and_run_order_drift() -> None:
    payload = load_execution_manifest(BENCHMARK_ROOT / "execution-manifest.yaml")
    changed = deepcopy(payload)
    changed["unexpected"] = True
    changed["runs"] = list(reversed(changed["runs"]))
    errors = validate_execution_manifest(changed, BENCHMARK_ROOT)
    assert "/unexpected: unexpected field" in errors
    assert "/runs: expected exact canonical run order" in errors


@pytest.mark.parametrize("run_id", RUN_IDS[1:])
def test_each_baseline_is_complete_deterministic_and_gold_blind(
    run_id: str, tmp_path: Path
) -> None:
    prepared = _prepared_fixture(tmp_path)
    manifest = load_execution_manifest(BENCHMARK_ROOT / "execution-manifest.yaml")
    first = generate_baseline(prepared, manifest, run_id)
    second = generate_baseline(deepcopy(prepared), deepcopy(manifest), run_id)
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert validate_run(first) == []
    assert len(first["results"]) == 15
    assert not _recursive_keys(first) & set(FORBIDDEN_GOLD_FIELDS)
    assert first["backend"]["run_id"] == run_id


def test_fixed_seed_random_sequence_is_frozen(tmp_path: Path) -> None:
    prepared = _prepared_fixture(tmp_path)
    manifest = load_execution_manifest(BENCHMARK_ROOT / "execution-manifest.yaml")
    run = generate_baseline(prepared, manifest, "fixed_seed_random")
    assert [row["predicted_label"] for row in run["results"]] == [
        2,
        2,
        2,
        0,
        2,
        3,
        2,
        1,
        3,
        2,
        1,
        3,
        1,
        3,
        3,
    ]


def test_all_pairs_and_shared_tag_follow_frozen_candidate_rules(tmp_path: Path) -> None:
    prepared = _prepared_fixture(tmp_path)
    manifest = load_execution_manifest(BENCHMARK_ROOT / "execution-manifest.yaml")
    all_pairs = generate_baseline(prepared, manifest, "all_pairs")
    shared_tag = generate_baseline(prepared, manifest, "shared_tag")
    assert all(row["candidate"] and row["predicted_label"] == 2 for row in all_pairs["results"])
    assert all(row["score"] == 1.0 for row in all_pairs["results"])
    assert any(row["candidate"] for row in shared_tag["results"])
    assert any(not row["candidate"] for row in shared_tag["results"])


def _model_responses(
    prepared: dict[str, object], *, predicted_label: int = 3
) -> dict[str, dict[str, object]]:
    responses: dict[str, dict[str, object]] = {}
    for packet in prepared["packets"]:  # type: ignore[index]
        first, second = packet["sources"]
        responses[packet["pair_id"]] = {
            "pair_id": packet["pair_id"],
            "paper_a_id": packet["paper_a_id"],
            "paper_b_id": packet["paper_b_id"],
            "predicted_label": predicted_label,
            "structural_relation": {
                "assessment": "The visible records support a synthetic structural comparison.",
                "shared_structure": "Both expose a bounded decision under uncertainty.",
                "transferable_implication": "Compare their synthetic decision rules.",
                "evidence": [
                    {
                        "paper_id": first["paper_id"],
                        "visible_field": "claims",
                        "excerpt_or_paraphrase": str(first["claims"][0]),
                    },
                    {
                        "paper_id": second["paper_id"],
                        "visible_field": "claims",
                        "excerpt_or_paraphrase": str(second["claims"][0]),
                    },
                ],
                "caveats": ["Synthetic contract fixture only."],
            },
            "status": "pending_review",
        }
    return responses


def _proved_provenance() -> dict[str, object]:
    return {
        "client": "Codex",
        "execution_surface": "Codex desktop task",
        "task_id": "synthetic-task-id",
        "declared_backend_label": "5.6 Sol",
        "provider_model_identity": None,
        "provider_model_identity_verified": False,
    }


def test_model_adapter_preserves_assessment_and_maps_label(tmp_path: Path) -> None:
    prepared = _prepared_fixture(tmp_path)
    manifest = load_execution_manifest(BENCHMARK_ROOT / "execution-manifest.yaml")
    responses = _model_responses(prepared, predicted_label=3)
    run = adapt_model_responses(prepared, manifest, responses, _proved_provenance())
    row = run["results"][0]
    response = responses[row["pair_id"]]
    assert row["candidate"] is True
    assert row["score"] == 1.0
    assert row["items"][0]["assessment"] == response["structural_relation"]["assessment"]
    assert row["items"][0]["confidence"] == "likely"
    assert row["items"][0]["status"] == "pending_review"
    assert validate_run(run) == []


def test_model_adapter_rejects_unresolved_evidence(tmp_path: Path) -> None:
    prepared = _prepared_fixture(tmp_path)
    manifest = load_execution_manifest(BENCHMARK_ROOT / "execution-manifest.yaml")
    responses = _model_responses(prepared)
    first = responses[sorted(responses)[0]]
    first["structural_relation"]["evidence"][0]["paper_id"] = "paper_0000000000000000"  # type: ignore[index]
    with pytest.raises(BenchmarkArtifactError, match="evidence"):
        adapt_model_responses(prepared, manifest, responses, _proved_provenance())


def test_model_response_rejects_unknown_and_forbidden_fields(tmp_path: Path) -> None:
    prepared = _prepared_fixture(tmp_path)
    packet = prepared["packets"][0]  # type: ignore[index]
    response = _model_responses(prepared)[packet["pair_id"]]
    response["gold_label"] = 3
    errors = validate_model_response(response, packet)
    assert any("gold_label" in error for error in errors)


def test_model_adapter_rejects_unproved_provider_identity(tmp_path: Path) -> None:
    prepared = _prepared_fixture(tmp_path)
    manifest = load_execution_manifest(BENCHMARK_ROOT / "execution-manifest.yaml")
    provenance = _proved_provenance()
    provenance["provider_model_identity"] = "provider/model-secret"
    provenance["provider_model_identity_verified"] = False
    with pytest.raises(BenchmarkArtifactError, match="provider model identity"):
        adapt_model_responses(prepared, manifest, _model_responses(prepared), provenance)
