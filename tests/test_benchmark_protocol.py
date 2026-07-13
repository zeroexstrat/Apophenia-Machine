import hashlib
import json
from pathlib import Path

import pytest
import yaml

from athanasor.benchmark.protocol import (
    EXPECTED_P5_METRIC_CONTRACTS,
    EXPECTED_P5_THRESHOLDS,
    FORBIDDEN_GOLD_FIELDS,
    BenchmarkProtocolError,
    canonical_digest,
    canonical_pairs,
    load_mapping,
    paper_id,
    pair_id,
    validate_blinded_packet,
    validate_blinded_schema,
    validate_freeze_manifest,
    validate_protocol,
    validate_public_bundle,
    validate_source_directory,
    validate_sources,
)
from tests.benchmark_fixtures import (
    protocol_fixture,
    reconciled_packet_fixture,
    source_manifest_fixture,
    write_private_source_fixture,
    write_valid_public_bundle,
)


BENCHMARK_ROOT = (
    Path(__file__).resolve().parents[1] / "benchmarks" / "operations-decision-support-v1"
)


def canonical_blinded_packet_fixture() -> dict[str, object]:
    packet = load_mapping(BENCHMARK_ROOT / "synthetic" / "blinded-packet.json")
    sources = packet["sources"]
    for source in sources:
        source["paper_id"] = paper_id(source["stable_identifier"], source["exact_version"])
    packet["paper_a_id"] = sources[0]["paper_id"]
    packet["paper_b_id"] = sources[1]["paper_id"]
    packet["pair_id"] = pair_id(packet["paper_a_id"], packet["paper_b_id"])
    packet["packet_id"] = f"packet_{packet['pair_id'].removeprefix('pair_')}"
    return packet


def test_live_source_manifest_is_valid_and_balanced() -> None:
    payload = load_mapping(BENCHMARK_ROOT / "sources.yaml")
    assert validate_sources(payload) == []
    assert len(payload["sources"]) == 12
    assert len(canonical_pairs([row["paper_id"] for row in payload["sources"]])) == 66
    assert {row["redistribution_status"] for row in payload["sources"]} == {"fetch_only"}


def test_live_protocol_is_valid_and_keeps_human_authority() -> None:
    payload = load_mapping(BENCHMARK_ROOT / "protocol.yaml")
    assert validate_protocol(payload) == []
    assert payload["adjudication"]["final_authority"] == "Rafael"
    assert payload["rubric"]["relevant_labels"] == [2, 3]


def test_live_blinded_schema_contains_no_gold_fields() -> None:
    payload = load_mapping(BENCHMARK_ROOT / "blinded-packet-schema.yaml")
    assert validate_blinded_schema(payload) == []
    assert FORBIDDEN_GOLD_FIELDS.issubset(payload["forbidden_fields"])


def test_blinded_packet_rejects_private_packet_vocabulary() -> None:
    packet = {
        "label": 3,
        "rationale": "secret",
        "evidence_spans": [{"paper_role": "a", "text": "secret"}],
    }
    errors = validate_blinded_packet(packet)
    assert any("/label" in error for error in errors)
    assert any("/rationale" in error for error in errors)
    assert any("/evidence_spans" in error for error in errors)


def test_blinded_packet_rejects_reconciled_private_topology() -> None:
    errors = validate_blinded_packet(reconciled_packet_fixture())
    assert any("/presentations" in error for error in errors)
    assert any("/gold_pairs" in error for error in errors)


def test_blinded_packet_recomputes_source_paper_identity() -> None:
    packet = canonical_blinded_packet_fixture()
    packet["sources"][0]["stable_identifier"] = "synthetic:mutated-identity"

    assert any("/sources/0/paper_id" in error for error in validate_blinded_packet(packet))


def test_blinded_packet_recomputes_pair_and_packet_identity() -> None:
    packet = canonical_blinded_packet_fixture()
    packet["pair_id"] = "pair_0000000000000000"
    packet["packet_id"] = "packet_arbitrary"
    errors = validate_blinded_packet(packet)

    assert any("/pair_id" in error for error in errors)
    assert any("/packet_id" in error for error in errors)


def test_blinded_packet_rejects_empty_explicit_citation() -> None:
    packet = canonical_blinded_packet_fixture()
    packet["sources"][0]["explicit_citations"] = [{}]

    assert any(
        "/sources/0/explicit_citations/0" in error
        for error in validate_blinded_packet(packet)
    )


def test_blinded_schema_rejects_empty_or_weakened_contract() -> None:
    assert validate_blinded_schema({})
    schema = load_mapping(BENCHMARK_ROOT / "blinded-packet-schema.yaml")
    schema["forbidden_fields"].remove("label")
    assert any("/forbidden_fields" in error for error in validate_blinded_schema(schema))


def test_metric_thresholds_match_preregistration() -> None:
    payload = load_mapping(BENCHMARK_ROOT / "protocol.yaml")
    assert {
        row["name"]: row["threshold"] for row in payload["metrics"]
    } == EXPECTED_P5_THRESHOLDS


def test_pair_label_annotation_sufficiency_mapping_is_frozen() -> None:
    payload = load_mapping(BENCHMARK_ROOT / "protocol.yaml")
    expected = {
        "macro_f1": True,
        "unsafe_ood_assignment": False,
        "claim_precision": False,
        "reference_recall": True,
        "candidate_recall": True,
        "workload_reduction": True,
        "precision_at_5": True,
        "ndcg_at_10": True,
        "evidence_support": False,
        "supported_items": False,
        "useful_items": False,
        "redundancy": False,
        "unsupported_derived_items": False,
    }
    assert {
        row["name"]: row["pair_labels_are_sufficient_evaluation_annotations"]
        for row in payload["metrics"]
    } == expected


def test_pair_label_annotation_sufficiency_has_exact_definition() -> None:
    payload = load_mapping(BENCHMARK_ROOT / "protocol.yaml")
    assert payload["metric_annotation_definitions"][
        "pair_labels_are_sufficient_evaluation_annotations"
    ] == (
        "the boolean means the frozen 66 pair labels are sufficient human evaluation "
        "annotations for the metric when combined with locked system outputs; it does "
        "not mean the metric can be computed without system outputs."
    )
    assert all("computable_from_66_labels_alone" not in row for row in payload["metrics"])


def test_live_generation_prompt_preserves_blinding_and_review_boundary() -> None:
    prompt = (BENCHMARK_ROOT / "generation-prompt.md").read_text(encoding="utf-8")
    folded = prompt.casefold()
    assert "5.6 sol" in folded
    assert "pending_review" in prompt
    for leaked_term in (
        "gold",
        "threshold",
        "expected positive",
        "selection note",
        "benchmark acceptance",
    ):
        assert leaked_term not in folded


def test_live_freeze_matches_public_digests() -> None:
    sources = load_mapping(BENCHMARK_ROOT / "sources.yaml")
    protocol = load_mapping(BENCHMARK_ROOT / "protocol.yaml")
    blinded_schema = load_mapping(BENCHMARK_ROOT / "blinded-packet-schema.yaml")
    freeze = load_mapping(BENCHMARK_ROOT / "freeze-manifest.json")
    assert validate_public_bundle(BENCHMARK_ROOT) == []
    assert validate_freeze_manifest(
        freeze,
        source_digest=canonical_digest(sources),
        protocol_digest=canonical_digest(protocol),
        prompt_digest=hashlib.sha256(
            (BENCHMARK_ROOT / "generation-prompt.md").read_bytes()
        ).hexdigest(),
        blinded_schema_digest=canonical_digest(blinded_schema),
    ) == []
    assert freeze["status"] == "frozen"
    assert freeze["pair_count"] == 66
    assert freeze["label_authority"] == "Rafael"
    assert freeze["private_gold_commitment"]["algorithm"] == (
        "sha256-canonical-json-v1"
    )


def test_paper_and_pair_ids_are_order_stable() -> None:
    first = paper_id("doi:10.3386/w23180", "nber-working-paper-23180-2017-02")
    second = paper_id("arxiv:1809.05504", "v1")
    assert first.startswith("paper_") and len(first) == 22
    assert pair_id(first, second) == pair_id(second, first)


def test_canonical_pairs_produce_exactly_66_unique_pairs() -> None:
    ids = [f"paper_{index:016x}" for index in range(12)]
    pairs = canonical_pairs(ids)
    assert len(pairs) == 66
    assert len({row["pair_id"] for row in pairs}) == 66
    assert all(row["paper_a_id"] < row["paper_b_id"] for row in pairs)


def test_canonical_pairs_reject_duplicates() -> None:
    with pytest.raises(BenchmarkProtocolError, match="12 unique paper IDs"):
        canonical_pairs(["paper_0000000000000000"] * 12)


def test_canonical_digest_ignores_mapping_order() -> None:
    assert canonical_digest({"b": 2, "a": 1}) == canonical_digest({"a": 1, "b": 2})


def test_source_manifest_requires_12_papers_at_four_per_lane() -> None:
    payload = source_manifest_fixture()
    payload["sources"].pop()
    errors = validate_sources(payload)
    assert "/sources: expected exactly 12 records" in errors
    assert any("lane balance" in error for error in errors)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("lane", []),
        ("retrieval", []),
        ("retrieval", {"method": [], "redirect_policy": {}, "final_url": 7, "redirect_chain": {}}),
    ],
)
def test_source_manifest_malformed_nested_values_return_errors(
    field: str, value: object
) -> None:
    payload = source_manifest_fixture()
    payload["sources"][0][field] = value
    errors = validate_sources(payload)
    assert errors
    assert any(f"/sources/0/{field}" in error for error in errors)


@pytest.mark.parametrize(
    "field", ["gold_label", "gold_rationale", "gold_evidence_spans", "adjudication_notes"]
)
def test_blinded_packet_rejects_gold_fields_at_any_depth(field: str) -> None:
    packet = {"records": [{"metadata": {field: 2}}]}
    assert any(field in error for error in validate_blinded_packet(packet))


def test_metric_contract_requires_denominator_and_undefined_rule() -> None:
    payload = protocol_fixture()
    del payload["metrics"][0]["denominator"]
    assert any("/metrics/0/denominator" in error for error in validate_protocol(payload))


def test_private_source_directory_detects_byte_and_retrieval_drift(tmp_path: Path) -> None:
    payload = source_manifest_fixture()
    write_private_source_fixture(tmp_path, payload)
    first = payload["sources"][0]
    (tmp_path / f"{first['paper_id']}.pdf").write_bytes(b"changed")
    errors = validate_source_directory(payload, tmp_path)
    assert any("sha256 mismatch" in error for error in errors)


def test_private_source_directory_accepts_publicly_recorded_redirect_chain(tmp_path: Path) -> None:
    payload = source_manifest_fixture()
    write_private_source_fixture(tmp_path, payload)
    assert validate_source_directory(payload, tmp_path) == []


@pytest.mark.parametrize("mutation", ["missing", "extra", "reordered", "substituted"])
def test_private_source_directory_rejects_any_redirect_chain_drift(
    tmp_path: Path, mutation: str
) -> None:
    payload = source_manifest_fixture()
    write_private_source_fixture(tmp_path, payload)
    first = payload["sources"][0]
    retrieval_path = tmp_path / f"{first['paper_id']}.retrieval.json"
    retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
    chain = retrieval["redirect_chain"]
    if mutation == "missing":
        chain.pop(1)
    elif mutation == "extra":
        chain.insert(-1, "https://extra.example.invalid/hop")
    elif mutation == "reordered":
        chain[1], chain[2] = chain[2], chain[1]
    else:
        chain[1] = "https://substitute.example.invalid/hop"
    retrieval_path.write_text(json.dumps(retrieval), encoding="utf-8")
    errors = validate_source_directory(payload, tmp_path)
    assert any("/sources/0/retrieval_record/redirect_chain" in error for error in errors)


def test_public_source_requires_exact_redirect_fields() -> None:
    payload = source_manifest_fixture()
    del payload["sources"][0]["retrieval"]["final_url"]
    del payload["sources"][1]["retrieval"]["redirect_chain"]
    errors = validate_sources(payload)
    assert any("/sources/0/retrieval/final_url" in error for error in errors)
    assert any("/sources/1/retrieval/redirect_chain" in error for error in errors)


def test_source_directory_malformed_public_retrieval_returns_errors(tmp_path: Path) -> None:
    payload = source_manifest_fixture()
    payload["sources"][0]["retrieval"] = []
    errors = validate_source_directory(payload, tmp_path)
    assert any("/sources/0/retrieval" in error for error in errors)


def test_sources_reject_identity_routes_rights_and_paths() -> None:
    payload = source_manifest_fixture()
    source = payload["sources"][0]
    source["paper_id"] = "paper_0000000000000000"
    source["canonical_url"] = "http://example.invalid/source"
    source["license_evidence_url"] = ""
    source["private_path"] = "/private/source.pdf"
    errors = validate_sources(payload)
    assert any("/sources/0/paper_id" in error for error in errors)
    assert any("/sources/0/canonical_url" in error for error in errors)
    assert any("/sources/0/license_evidence_url" in error for error in errors)
    assert any("/sources/0/private_path" in error for error in errors)


def test_protocol_requires_exact_threshold_contract() -> None:
    payload = protocol_fixture()
    payload["metrics"][0]["threshold"]["value"] = 0.79
    errors = validate_protocol(payload)
    assert any("/metrics/0/threshold" in error for error in errors)
    assert len(EXPECTED_P5_THRESHOLDS) == 13


@pytest.mark.parametrize(
    "field",
    [
        "population",
        "numerator",
        "denominator",
        "averaging",
        "undefined_case",
        "uncertainty",
        "future_artifact",
        "comparison",
        "threshold",
    ],
)
def test_protocol_rejects_every_metric_semantic_mutation(field: str) -> None:
    payload = protocol_fixture()
    payload["metrics"][0][field] = "mutated"
    errors = validate_protocol(payload)
    assert any(f"/metrics/0/{field}" in error for error in errors)


@pytest.mark.parametrize("name", [[], {}, 7, None])
def test_protocol_malformed_metric_names_return_field_errors(name: object) -> None:
    payload = protocol_fixture()
    payload["metrics"][0]["name"] = name
    errors = validate_protocol(payload)
    assert any("/metrics/0/name" in error for error in errors)


def test_preregistered_threshold_contract_is_immutable() -> None:
    with pytest.raises(TypeError):
        EXPECTED_P5_THRESHOLDS["macro_f1"]["value"] = 0.79


def test_full_metric_contract_is_deeply_immutable() -> None:
    with pytest.raises(TypeError):
        EXPECTED_P5_METRIC_CONTRACTS["macro_f1"]["population"] = "mutated"
    with pytest.raises(TypeError):
        EXPECTED_P5_METRIC_CONTRACTS["macro_f1"]["threshold"]["value"] = 0.79


def test_protocol_accepts_descriptive_zero_to_three_rubric() -> None:
    payload = protocol_fixture()
    payload["rubric"]["scale"] = {
        0: "no meaningful structural relationship for this benchmark",
        1: "topical or lexical overlap without an actionable structural relation",
        2: "meaningful shared mechanism, method, or decision structure",
        3: "strong structural relation with a concrete transferable implication",
    }
    assert validate_protocol(payload) == []


def test_freeze_manifest_accepts_pending_without_gold_commitment() -> None:
    payload = {
        "schema_version": 1,
        "artifact_type": "azoth_benchmark_freeze",
        "benchmark_id": "operations-decision-support-v1",
        "status": "pending_human_adjudication",
        "source_manifest_sha256": "a" * 64,
        "protocol_sha256": "b" * 64,
        "prompt_sha256": "c" * 64,
        "blinded_schema_sha256": "d" * 64,
        "pair_count": 66,
        "label_authority": "Rafael",
        "private_gold_commitment": None,
        "no_retuning": True,
    }
    assert validate_freeze_manifest(
        payload,
        source_digest="a" * 64,
        protocol_digest="b" * 64,
        prompt_digest="c" * 64,
        blinded_schema_digest="d" * 64,
    ) == []


def test_freeze_manifest_requires_complete_frozen_commitment() -> None:
    payload = {
        "schema_version": 1,
        "artifact_type": "azoth_benchmark_freeze",
        "benchmark_id": "operations-decision-support-v1",
        "status": "frozen",
        "source_manifest_sha256": "a" * 64,
        "protocol_sha256": "b" * 64,
        "prompt_sha256": "c" * 64,
        "blinded_schema_sha256": "d" * 64,
        "pair_count": 66,
        "label_authority": "Rafael",
        "private_gold_commitment": {"private_gold_sha256": "d" * 64},
        "no_retuning": True,
    }
    errors = validate_freeze_manifest(
        payload,
        source_digest="a" * 64,
        protocol_digest="b" * 64,
        prompt_digest="c" * 64,
        blinded_schema_digest="d" * 64,
    )
    assert any("/private_gold_commitment/algorithm" in error for error in errors)


def test_freeze_manifest_rejects_unexpected_gold_commitment_content() -> None:
    payload = {
        "schema_version": 1,
        "artifact_type": "azoth_benchmark_freeze",
        "benchmark_id": "operations-decision-support-v1",
        "status": "frozen",
        "source_manifest_sha256": "a" * 64,
        "protocol_sha256": "b" * 64,
        "prompt_sha256": "c" * 64,
        "blinded_schema_sha256": "d" * 64,
        "pair_count": 66,
        "label_authority": "Rafael",
        "private_gold_commitment": {
            "algorithm": "sha256-canonical-json-v1",
            "private_gold_sha256": "d" * 64,
            "schema_version": 1,
            "freeze_time": "2026-07-11T12:00:00Z",
            "gold_pairs": [{"label": 3}],
        },
        "no_retuning": True,
    }
    errors = validate_freeze_manifest(
        payload,
        source_digest="a" * 64,
        protocol_digest="b" * 64,
        prompt_digest="c" * 64,
        blinded_schema_digest="d" * 64,
    )
    assert any("/private_gold_commitment/gold_pairs" in error for error in errors)


def test_load_mapping_rejects_non_mapping(tmp_path: Path) -> None:
    path = tmp_path / "value.yaml"
    path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    with pytest.raises(BenchmarkProtocolError, match="expected top-level object"):
        load_mapping(path)


def test_public_bundle_combines_validation_errors(tmp_path: Path) -> None:
    sources = source_manifest_fixture()
    protocol = protocol_fixture()
    (tmp_path / "sources.yaml").write_text(yaml.safe_dump(sources), encoding="utf-8")
    (tmp_path / "protocol.yaml").write_text(yaml.safe_dump(protocol), encoding="utf-8")
    (tmp_path / "blinded-packet-schema.yaml").write_text(
        yaml.safe_dump({"gold_label": "forbidden"}), encoding="utf-8"
    )
    prompt = b"Synthetic prompt.\n"
    (tmp_path / "generation-prompt.md").write_bytes(prompt)
    freeze = {
        "schema_version": 1,
        "artifact_type": "azoth_benchmark_freeze",
        "benchmark_id": "operations-decision-support-v1",
        "status": "pending_human_adjudication",
        "source_manifest_sha256": canonical_digest(sources),
        "protocol_sha256": canonical_digest(protocol),
        "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
        "pair_count": 66,
        "label_authority": "Rafael",
        "private_gold_commitment": None,
        "no_retuning": True,
    }
    (tmp_path / "freeze-manifest.json").write_text(json.dumps(freeze), encoding="utf-8")
    assert any("gold_label" in error for error in validate_public_bundle(tmp_path))


def test_public_bundle_rejects_blinded_schema_drift_after_freeze(
    tmp_path: Path,
) -> None:
    benchmark = write_valid_public_bundle(tmp_path)
    schema_path = benchmark / "blinded-packet-schema.yaml"
    schema = load_mapping(schema_path)
    schema["forbidden_fields"].remove("label")
    schema_path.write_text(yaml.safe_dump(schema, sort_keys=False), encoding="utf-8")
    errors = validate_public_bundle(benchmark)
    assert any("/blinded_schema_sha256" in error for error in errors)


@pytest.mark.parametrize("surface", ["sources", "protocol", "blinded_schema", "freeze"])
def test_public_bundle_rejects_gold_fields_on_every_mapping_surface(
    tmp_path: Path, surface: str
) -> None:
    sources = source_manifest_fixture()
    protocol = protocol_fixture()
    blinded_schema = {"schema_version": 1, "allowed_fields": ["paper_id", "pair_id"]}
    prompt = b"Synthetic prompt.\n"
    freeze = {
        "schema_version": 1,
        "artifact_type": "azoth_benchmark_freeze",
        "benchmark_id": "operations-decision-support-v1",
        "status": "pending_human_adjudication",
        "source_manifest_sha256": canonical_digest(sources),
        "protocol_sha256": canonical_digest(protocol),
        "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
        "pair_count": 66,
        "label_authority": "Rafael",
        "private_gold_commitment": None,
        "no_retuning": True,
    }
    target = {
        "sources": sources,
        "protocol": protocol,
        "blinded_schema": blinded_schema,
        "freeze": freeze,
    }[surface]
    target["nested"] = {"gold_rationale": "forbidden"}
    (tmp_path / "sources.yaml").write_text(yaml.safe_dump(sources), encoding="utf-8")
    (tmp_path / "protocol.yaml").write_text(yaml.safe_dump(protocol), encoding="utf-8")
    (tmp_path / "blinded-packet-schema.yaml").write_text(
        yaml.safe_dump(blinded_schema), encoding="utf-8"
    )
    (tmp_path / "generation-prompt.md").write_bytes(prompt)
    (tmp_path / "freeze-manifest.json").write_text(json.dumps(freeze), encoding="utf-8")
    errors = validate_public_bundle(tmp_path)
    assert any("gold_rationale" in error for error in errors)
