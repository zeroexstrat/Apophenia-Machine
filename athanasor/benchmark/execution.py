from __future__ import annotations

import hashlib
import math
import random
import re
import unicodedata
from pathlib import Path
from typing import Any

from athanasor.benchmark.artifacts import BenchmarkArtifactError, validate_prepared, validate_run
from athanasor.benchmark.pipeline import _assign_pair_ranks, _fallback_pair, _run_artifact
from athanasor.benchmark.protocol import (
    BENCHMARK_ID,
    BLINDED_FORBIDDEN_FIELDS,
    canonical_digest,
    load_mapping,
)


EXECUTION_MANIFEST_VERSION = 1
EXECUTION_MANIFEST_TYPE = "azoth_benchmark_execution_manifest"
RUN_IDS = (
    "model_5_6_sol",
    "deterministic_routing",
    "all_pairs",
    "shared_tag",
    "hash_embedding",
    "current_score",
    "fixed_seed_random",
)

_TOP_LEVEL_FIELDS = {
    "schema_version",
    "artifact_type",
    "benchmark_id",
    "status",
    "seed",
    "public_contracts",
    "pre_run_attestation",
    "runs",
    "baselines",
    "model_adapter",
    "lock_contract",
    "annotation_contract",
    "no_retuning",
}


def load_execution_manifest(path: Path) -> dict[str, Any]:
    return load_mapping(Path(path))


def _public_contract_digests(benchmark_root: Path) -> dict[str, str]:
    root = Path(benchmark_root)
    return {
        "source_manifest_sha256": canonical_digest(load_mapping(root / "sources.yaml")),
        "protocol_sha256": canonical_digest(load_mapping(root / "protocol.yaml")),
        "prompt_sha256": hashlib.sha256((root / "generation-prompt.md").read_bytes()).hexdigest(),
        "blinded_schema_sha256": canonical_digest(load_mapping(root / "blinded-packet-schema.yaml")),
        "freeze_manifest_sha256": canonical_digest(load_mapping(root / "freeze-manifest.json")),
    }


def _field_error(path: str, actual: Any, expected: Any) -> str:
    return f"{path}: expected {expected!r}, got {actual!r}"


def validate_execution_manifest(payload: Any, benchmark_root: Path) -> list[str]:
    if not isinstance(payload, dict):
        return ["/: expected object"]
    errors: list[str] = []
    for field in sorted(set(payload) - _TOP_LEVEL_FIELDS):
        errors.append(f"/{field}: unexpected field")
    expected_scalars = {
        "schema_version": EXECUTION_MANIFEST_VERSION,
        "artifact_type": EXECUTION_MANIFEST_TYPE,
        "benchmark_id": BENCHMARK_ID,
        "status": "frozen_before_real_runs",
        "seed": 5607,
        "no_retuning": True,
    }
    for field, expected in expected_scalars.items():
        if payload.get(field) != expected:
            errors.append(_field_error(f"/{field}", payload.get(field), expected))

    contracts = payload.get("public_contracts")
    try:
        expected_contracts = _public_contract_digests(Path(benchmark_root))
    except (OSError, ValueError) as exc:
        errors.append(f"/public_contracts: cannot derive public digests: {exc}")
        expected_contracts = {}
    if not isinstance(contracts, dict):
        errors.append("/public_contracts: expected object")
    else:
        for field in sorted(set(contracts) - set(expected_contracts)):
            errors.append(f"/public_contracts/{field}: unexpected field")
        for field, expected in expected_contracts.items():
            if contracts.get(field) != expected:
                errors.append(
                    _field_error(f"/public_contracts/{field}", contracts.get(field), expected)
                )

    runs = payload.get("runs")
    actual_run_ids = (
        [row.get("run_id") for row in runs if isinstance(row, dict)]
        if isinstance(runs, list)
        else []
    )
    if actual_run_ids != list(RUN_IDS):
        errors.append("/runs: expected exact canonical run order")
    if not isinstance(runs, list) or len(runs) != len(RUN_IDS):
        errors.append(f"/runs: expected exactly {len(RUN_IDS)} run records")
    else:
        for index, row in enumerate(runs):
            if not isinstance(row, dict):
                errors.append(f"/runs/{index}: expected object")
                continue
            if set(row) != {"run_id", "kind", "backend_name"}:
                errors.append(f"/runs/{index}: expected exact run fields")
            expected_kind = "model" if index == 0 else "deterministic_baseline"
            if row.get("kind") != expected_kind:
                errors.append(_field_error(f"/runs/{index}/kind", row.get("kind"), expected_kind))
            if not isinstance(row.get("backend_name"), str) or not row["backend_name"]:
                errors.append(f"/runs/{index}/backend_name: expected nonempty string")

    baselines = payload.get("baselines")
    expected_baseline_ids = set(RUN_IDS[1:])
    if not isinstance(baselines, dict):
        errors.append("/baselines: expected object")
    elif set(baselines) != expected_baseline_ids:
        errors.append("/baselines: expected exact deterministic baseline IDs")
    else:
        exact_rules: dict[str, dict[str, Any]] = {
            "deterministic_routing": {
                "candidate_rule": "similarity_gte_threshold_or_high_signal_shared_or_shared_count_gte_strong_overlap",
                "label_rule": "candidate_2_else_0",
                "score_rule": "max_clamped_cosine_high_signal_or_shared_fraction",
                "similarity_threshold": 0.82,
                "strong_overlap_count": 2,
            },
            "all_pairs": {
                "candidate_rule": "always",
                "label_rule": "constant_2",
                "score_rule": "constant_1",
            },
            "shared_tag": {
                "candidate_rule": "meaningful_tag_intersection_nonempty",
                "label_rule": "candidate_2_else_0",
                "score_rule": "meaningful_tag_jaccard",
            },
            "hash_embedding": {
                "candidate_rule": "predicted_label_gte_2",
                "score_rule": "raw_cosine_rounded_12",
                "label_cut_points": [0.0, 0.25, 0.5],
            },
            "current_score": {
                "candidate_rule": "predicted_label_gte_2",
                "score_rule": "token_jaccard_plus_seeded_tie_break",
                "label_cut_points": [0.1, 0.25, 0.5],
            },
            "fixed_seed_random": {
                "candidate_rule": "predicted_label_gte_2",
                "score_rule": "random_draw_rounded_12",
                "draw_order": "randrange_4_then_random_per_pair",
            },
        }
        for baseline_id, rules in exact_rules.items():
            row = baselines[baseline_id]
            if not isinstance(row, dict):
                errors.append(f"/baselines/{baseline_id}: expected object")
                continue
            for field, expected in rules.items():
                if row.get(field) != expected:
                    errors.append(
                        _field_error(
                            f"/baselines/{baseline_id}/{field}", row.get(field), expected
                        )
                    )

    attestation = payload.get("pre_run_attestation")
    if not isinstance(attestation, dict):
        errors.append("/pre_run_attestation: expected object")
    else:
        for field in (
            "real_prepared_artifact_observed",
            "real_run_artifact_observed",
            "real_score_artifact_observed",
            "gold_content_opened",
        ):
            if attestation.get(field) is not False:
                errors.append(f"/pre_run_attestation/{field}: expected false")
        if attestation.get("implementation_git_sha_source") != "lock_manifest":
            errors.append(
                "/pre_run_attestation/implementation_git_sha_source: expected 'lock_manifest'"
            )

    for field in ("model_adapter", "lock_contract", "annotation_contract"):
        if not isinstance(payload.get(field), dict) or not payload[field]:
            errors.append(f"/{field}: expected nonempty object")
    return sorted(errors)


def execution_manifest_digest(payload: dict[str, Any], benchmark_root: Path) -> str:
    errors = validate_execution_manifest(payload, benchmark_root)
    if errors:
        raise BenchmarkArtifactError("invalid execution manifest: " + "; ".join(errors))
    return canonical_digest(payload)


def _manifest_digest_for_prepared(
    prepared: dict[str, Any], manifest: dict[str, Any]
) -> str:
    prepared_errors = validate_prepared(prepared)
    if prepared_errors:
        raise BenchmarkArtifactError("invalid prepared artifact: " + "; ".join(prepared_errors))
    if not isinstance(manifest, dict):
        raise BenchmarkArtifactError("execution manifest: expected object")
    if manifest.get("schema_version") != 1 or manifest.get("artifact_type") != EXECUTION_MANIFEST_TYPE:
        raise BenchmarkArtifactError("execution manifest: invalid identity")
    if manifest.get("status") != "frozen_before_real_runs" or manifest.get("seed") != 5607:
        raise BenchmarkArtifactError("execution manifest: invalid frozen state")
    run_rows = manifest.get("runs")
    if not isinstance(run_rows, list) or [row.get("run_id") for row in run_rows if isinstance(row, dict)] != list(RUN_IDS):
        raise BenchmarkArtifactError("execution manifest: exact canonical run order required")
    contracts = manifest.get("public_contracts")
    provenance = prepared.get("provenance")
    if not isinstance(contracts, dict) or not isinstance(provenance, dict):
        raise BenchmarkArtifactError("execution manifest and prepared provenance are required")
    mappings = {
        "source_manifest_sha256": "frozen_source_manifest_sha256",
        "protocol_sha256": "protocol_sha256",
        "prompt_sha256": "prompt_sha256",
        "blinded_schema_sha256": "blinded_schema_sha256",
        "freeze_manifest_sha256": "freeze_manifest_sha256",
    }
    for contract_field, provenance_field in mappings.items():
        if contracts.get(contract_field) != provenance.get(provenance_field):
            raise BenchmarkArtifactError(
                f"execution manifest /public_contracts/{contract_field} does not match prepared provenance"
            )
    return canonical_digest(manifest)


def _normalized_text(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value)).split()).casefold()


def _visible_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        result: list[str] = []
        for child in value:
            result.extend(_visible_strings(child))
        return result
    if isinstance(value, dict):
        result = []
        for key in sorted(value):
            result.extend(_visible_strings(value[key]))
        return result
    return []


def _visible_text(source: dict[str, Any]) -> str:
    values: list[str] = []
    for field in ("abstract", "claims", "methods", "tags", "extracted_record"):
        values.extend(_visible_strings(source.get(field)))
    return _normalized_text(" ".join(values))


def _meaningful_tags(source: dict[str, Any], generic_tags: set[str]) -> set[str]:
    tags = source.get("tags")
    if not isinstance(tags, list):
        return set()
    return {
        normalized
        for tag in tags
        if isinstance(tag, str)
        for normalized in (_normalized_text(tag),)
        if normalized and normalized not in generic_tags
    }


def _hash_vector(text: str, dimension: int = 384) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = [(digest[index % len(digest)] / 255.0) - 0.5 for index in range(dimension)]
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values] if norm else [0.0] * dimension


def _cosine(first: dict[str, Any], second: dict[str, Any], dimension: int = 384) -> float:
    a = _hash_vector(_visible_text(first), dimension)
    b = _hash_vector(_visible_text(second), dimension)
    return round(sum(left * right for left, right in zip(a, b)), 12)


def _label_from_cut_points(score: float, cut_points: list[float]) -> int:
    if score < cut_points[0]:
        return 0
    if score < cut_points[1]:
        return 1
    if score < cut_points[2]:
        return 2
    return 3


def _base_row(packet: dict[str, Any], *, label: int, score: float) -> dict[str, Any]:
    return {
        "pair_id": packet["pair_id"],
        "paper_a_id": packet["paper_a_id"],
        "paper_b_id": packet["paper_b_id"],
        "predicted_label": label,
        "candidate": label >= 2,
        "score": round(float(score), 12),
        "rank_a": 0,
        "rank_b": 0,
        "items": [],
        "status": "pending_review",
    }


def _baseline_row(
    packet: dict[str, Any],
    *,
    run_id: str,
    manifest: dict[str, Any],
    generator: random.Random | None,
) -> dict[str, Any]:
    first, second = packet["sources"]
    rule = manifest["baselines"][run_id]
    if run_id == "all_pairs":
        return _base_row(packet, label=2, score=1.0)
    if run_id == "fixed_seed_random":
        if generator is None:
            raise BenchmarkArtifactError("fixed-seed random baseline requires a generator")
        label = generator.randrange(4)
        return _base_row(packet, label=label, score=generator.random())
    if run_id == "current_score":
        row = _fallback_pair(packet, seed=int(manifest["seed"]))
        row["items"] = []
        return row

    generic_tags = set(rule.get("generic_tags", []))
    first_tags = _meaningful_tags(first, generic_tags)
    second_tags = _meaningful_tags(second, generic_tags)
    shared = first_tags & second_tags
    if run_id == "shared_tag":
        union = first_tags | second_tags
        score = len(shared) / len(union) if union else 0.0
        return _base_row(packet, label=2 if shared else 0, score=score)

    similarity = _cosine(first, second, int(rule.get("dimension", 384)))
    if run_id == "hash_embedding":
        label = _label_from_cut_points(similarity, [float(value) for value in rule["label_cut_points"]])
        return _base_row(packet, label=label, score=similarity)
    if run_id == "deterministic_routing":
        high_signal = bool(shared & set(rule["high_signal_tags"]))
        strong_count = int(rule["strong_overlap_count"])
        candidate = (
            similarity >= float(rule["similarity_threshold"])
            or high_signal
            or len(shared) >= strong_count
        )
        score = max(
            max(0.0, similarity),
            1.0 if high_signal else 0.0,
            min(1.0, len(shared) / strong_count),
        )
        return _base_row(packet, label=2 if candidate else 0, score=score)
    raise BenchmarkArtifactError(f"unsupported deterministic baseline {run_id}")


def generate_baseline(
    prepared: dict[str, Any], manifest: dict[str, Any], run_id: str
) -> dict[str, Any]:
    if run_id not in RUN_IDS[1:]:
        raise BenchmarkArtifactError(f"unsupported deterministic baseline {run_id}")
    manifest_digest = _manifest_digest_for_prepared(prepared, manifest)
    packets = sorted(prepared["packets"], key=lambda packet: packet["pair_id"])
    generator = random.Random(int(manifest["seed"])) if run_id == "fixed_seed_random" else None
    results = [
        _baseline_row(packet, run_id=run_id, manifest=manifest, generator=generator)
        for packet in packets
    ]
    _assign_pair_ranks(results)
    run_record = next(row for row in manifest["runs"] if row["run_id"] == run_id)
    run = _run_artifact(
        prepared,
        backend={
            "name": run_record["backend_name"],
            "version": 1,
            "run_id": run_id,
            "execution_manifest_sha256": manifest_digest,
        },
        seed=int(manifest["seed"]),
        results=results,
    )
    errors = validate_run(run)
    if errors:
        raise BenchmarkArtifactError("invalid baseline run: " + "; ".join(errors))
    return run


_MODEL_RESPONSE_FIELDS = {
    "pair_id",
    "paper_a_id",
    "paper_b_id",
    "predicted_label",
    "structural_relation",
    "status",
}
_RELATION_FIELDS = {
    "assessment",
    "shared_structure",
    "transferable_implication",
    "evidence",
    "caveats",
}
_EVIDENCE_FIELDS = {"paper_id", "visible_field", "excerpt_or_paraphrase"}
_PROVENANCE_FIELDS = {
    "client",
    "execution_surface",
    "task_id",
    "declared_backend_label",
    "provider_model_identity",
    "provider_model_identity_verified",
}


def _recursive_forbidden_fields(value: Any, path: str = "") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}/{key}"
            if key in BLINDED_FORBIDDEN_FIELDS:
                errors.append(f"{child_path}: forbidden gold or authority field")
            errors.extend(_recursive_forbidden_fields(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_recursive_forbidden_fields(child, f"{path}/{index}"))
    return errors


def validate_model_response(response: Any, packet: dict[str, Any]) -> list[str]:
    if not isinstance(response, dict):
        return ["/: expected object"]
    errors = _recursive_forbidden_fields(response)
    for field in sorted(set(response) - _MODEL_RESPONSE_FIELDS):
        errors.append(f"/{field}: unexpected field")
    for field in ("pair_id", "paper_a_id", "paper_b_id"):
        if response.get(field) != packet.get(field):
            errors.append(f"/{field}: does not match blinded packet")
    label = response.get("predicted_label")
    if isinstance(label, bool) or not isinstance(label, int) or label not in range(4):
        errors.append("/predicted_label: expected integer label 0-3")
    if response.get("status") != "pending_review":
        errors.append("/status: expected pending_review")

    relation = response.get("structural_relation")
    if not isinstance(relation, dict):
        errors.append("/structural_relation: expected object")
        return sorted(errors)
    for field in sorted(set(relation) - _RELATION_FIELDS):
        errors.append(f"/structural_relation/{field}: unexpected field")
    for field in ("assessment", "shared_structure"):
        if not isinstance(relation.get(field), str) or not relation[field].strip():
            errors.append(f"/structural_relation/{field}: expected nonempty string")
    implication = relation.get("transferable_implication")
    if implication is not None and (
        not isinstance(implication, str) or not implication.strip()
    ):
        errors.append(
            "/structural_relation/transferable_implication: expected nonempty string or null"
        )
    caveats = relation.get("caveats")
    if not isinstance(caveats, list) or not caveats or not all(
        isinstance(value, str) and value.strip() for value in caveats
    ):
        errors.append("/structural_relation/caveats: expected nonempty string array")

    source_by_id = {
        source.get("paper_id"): source
        for source in packet.get("sources", [])
        if isinstance(source, dict)
    }
    evidence = relation.get("evidence")
    seen_papers: set[str] = set()
    if not isinstance(evidence, list) or not evidence:
        errors.append("/structural_relation/evidence: expected nonempty array")
    else:
        for index, row in enumerate(evidence):
            base = f"/structural_relation/evidence/{index}"
            if not isinstance(row, dict):
                errors.append(f"{base}: expected object")
                continue
            for field in sorted(set(row) - _EVIDENCE_FIELDS):
                errors.append(f"{base}/{field}: unexpected field")
            paper_identifier = row.get("paper_id")
            source = source_by_id.get(paper_identifier)
            if source is None:
                errors.append(f"{base}/paper_id: evidence paper is not in blinded packet")
            else:
                seen_papers.add(str(paper_identifier))
                visible_field = row.get("visible_field")
                if not isinstance(visible_field, str) or visible_field not in source:
                    errors.append(f"{base}/visible_field: evidence field is not visible in packet")
            excerpt = row.get("excerpt_or_paraphrase")
            if not isinstance(excerpt, str) or not excerpt.strip():
                errors.append(f"{base}/excerpt_or_paraphrase: expected nonempty string")
    if source_by_id and seen_papers != set(source_by_id):
        errors.append("/structural_relation/evidence: must cover both packet papers")
    return sorted(errors)


def _validate_provenance(provenance: Any) -> dict[str, Any]:
    if not isinstance(provenance, dict):
        raise BenchmarkArtifactError("model provenance: expected object")
    unexpected = sorted(set(provenance) - _PROVENANCE_FIELDS)
    missing = sorted(_PROVENANCE_FIELDS - set(provenance))
    if unexpected or missing:
        details = []
        if unexpected:
            details.append(f"unexpected field {unexpected[0]}")
        if missing:
            details.append(f"missing field {missing[0]}")
        raise BenchmarkArtifactError("model provenance: " + "; ".join(details))
    for field in ("client", "execution_surface", "task_id"):
        if not isinstance(provenance.get(field), str) or not provenance[field].strip():
            raise BenchmarkArtifactError(f"model provenance /{field}: expected nonempty string")
    if provenance.get("declared_backend_label") != "5.6 Sol":
        raise BenchmarkArtifactError("model provenance: declared backend label must be 5.6 Sol")
    if provenance.get("provider_model_identity") is not None:
        raise BenchmarkArtifactError(
            "model provenance: provider model identity is not exposed by this runtime"
        )
    if provenance.get("provider_model_identity_verified") is not False:
        raise BenchmarkArtifactError(
            "model provenance: provider model identity must remain unverified"
        )
    return dict(provenance)


def adapt_model_responses(
    prepared: dict[str, Any],
    manifest: dict[str, Any],
    responses: dict[str, dict[str, Any]],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    manifest_digest = _manifest_digest_for_prepared(prepared, manifest)
    proved_provenance = _validate_provenance(provenance)
    if not isinstance(responses, dict):
        raise BenchmarkArtifactError("model responses: expected pair-keyed object")
    packets = {packet["pair_id"]: packet for packet in prepared["packets"]}
    if set(responses) != set(packets):
        raise BenchmarkArtifactError("model responses: exact canonical pair coverage required")

    results: list[dict[str, Any]] = []
    for pair_identifier in sorted(packets):
        packet = packets[pair_identifier]
        response = responses[pair_identifier]
        errors = validate_model_response(response, packet)
        if errors:
            raise BenchmarkArtifactError(
                f"invalid model response {pair_identifier}: " + "; ".join(errors)
            )
        label = int(response["predicted_label"])
        relation = response["structural_relation"]
        item_suffix = pair_identifier.split("_", 1)[1]
        item_evidence = [
            {
                "span_id": f"span_{item_suffix}_{index + 1:02d}",
                "paper_id": row["paper_id"],
                "visible_field": row["visible_field"],
                "excerpt_or_paraphrase": row["excerpt_or_paraphrase"].strip(),
            }
            for index, row in enumerate(relation["evidence"])
        ]
        item = {
            "item_id": f"item_{item_suffix}",
            "claim_id": f"claim_{item_suffix}",
            "assessment": relation["assessment"].strip(),
            "shared_structure": relation["shared_structure"].strip(),
            "transferable_implication": (
                relation["transferable_implication"].strip()
                if isinstance(relation["transferable_implication"], str)
                else None
            ),
            "evidence": item_evidence,
            "caveats": [value.strip() for value in relation["caveats"]],
            "confidence": "likely" if label == 3 else "speculative",
            "status": "pending_review",
        }
        results.append(
            {
                "pair_id": pair_identifier,
                "paper_a_id": packet["paper_a_id"],
                "paper_b_id": packet["paper_b_id"],
                "predicted_label": label,
                "candidate": label >= 2,
                "score": round(label / 3, 12),
                "rank_a": 0,
                "rank_b": 0,
                "items": [item],
                "status": "pending_review",
            }
        )
    _assign_pair_ranks(results)
    run_record = next(row for row in manifest["runs"] if row["run_id"] == RUN_IDS[0])
    run = _run_artifact(
        prepared,
        backend={
            "name": run_record["backend_name"],
            "version": 1,
            "run_id": RUN_IDS[0],
            "declared_model_label": "5.6 Sol",
            "execution_manifest_sha256": manifest_digest,
            "provenance": proved_provenance,
        },
        seed=int(manifest["seed"]),
        results=results,
    )
    errors = validate_run(run)
    if errors:
        raise BenchmarkArtifactError("invalid adapted model run: " + "; ".join(errors))
    return run
