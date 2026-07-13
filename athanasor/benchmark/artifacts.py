from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from collections.abc import Mapping
from itertools import combinations
from pathlib import Path
from typing import Any

from athanasor.benchmark.protocol import (
    BENCHMARK_ID,
    EXPECTED_P5_METRIC_CONTRACTS,
    EXPECTED_P5_THRESHOLDS,
    FORBIDDEN_GOLD_FIELDS,
    canonical_digest,
    canonical_json_bytes,
    pair_id,
)


SCHEMA_VERSION = 1
PREPARED_TYPE = "azoth_benchmark_prepared"
RUN_TYPE = "azoth_benchmark_run"
SCORE_TYPE = "azoth_benchmark_score"
EXECUTION_MANIFEST_TYPE = "azoth_benchmark_execution_manifest"
LOCK_TYPE = "azoth_benchmark_run_lock"
SYNTHETIC_NOTICE = "SYNTHETIC CONTRACT TEST — NOT A PERFORMANCE CLAIM"

_SHA256 = re.compile(r"[0-9a-f]{64}")
_PAPER_ID = re.compile(r"paper_[0-9a-f]{16}")
_PAIR_ID = re.compile(r"pair_[0-9a-f]{16}")


class BenchmarkArtifactError(ValueError):
    """A P6 artifact or path violates the benchmark contract."""


def artifact_digest(payload: Any) -> str:
    return canonical_digest(payload)


def read_json_artifact(path: Path, *, artifact_type: str | None = None) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BenchmarkArtifactError(f"cannot read {Path(path).name}: {exc}") from None
    if not isinstance(payload, dict):
        raise BenchmarkArtifactError(f"cannot read {Path(path).name}: expected object")
    if artifact_type is not None and payload.get("artifact_type") != artifact_type:
        raise BenchmarkArtifactError(
            f"/{Path(path).name}/artifact_type: expected {artifact_type}"
        )
    return payload


def atomic_write_json(path: Path, payload: dict[str, Any], *, force: bool = False) -> str:
    destination = Path(path)
    if destination.exists() and not force:
        raise BenchmarkArtifactError(f"destination already exists: {destination.name}")
    try:
        encoded = canonical_json_bytes(payload)
    except (TypeError, ValueError, RecursionError) as exc:
        raise BenchmarkArtifactError(f"cannot serialize {destination.name}: {exc}") from None
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, destination)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return hashlib.sha256(encoded).hexdigest()


def atomic_write_text(path: Path, content: str, *, force: bool = False) -> str:
    destination = Path(path)
    if destination.exists() and not force:
        raise BenchmarkArtifactError(f"destination already exists: {destination.name}")
    encoded = content.encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, destination)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return hashlib.sha256(encoded).hexdigest()


def ensure_outside_repository(path: Path, repo_root: Path, *, label: str) -> Path:
    candidate = Path(path).expanduser().resolve(strict=False)
    repository = Path(repo_root).expanduser().resolve(strict=False)
    if candidate == repository or repository in candidate.parents:
        raise BenchmarkArtifactError(f"{label} must be outside the repository")
    return candidate


def _forbidden_errors(value: Any, path: str = "") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}/{key}"
            if isinstance(key, str) and key.casefold() in FORBIDDEN_GOLD_FIELDS:
                errors.append(f"{child_path}: gold-only field is forbidden")
            errors.extend(_forbidden_errors(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_forbidden_errors(child, f"{path}/{index}"))
    return errors


def _base_errors(payload: Any, artifact_type: str) -> list[str]:
    if not isinstance(payload, dict):
        return ["/: expected object"]
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("/schema_version: expected 1")
    if payload.get("artifact_type") != artifact_type:
        errors.append(f"/artifact_type: expected {artifact_type}")
    if payload.get("benchmark_id") != BENCHMARK_ID:
        errors.append(f"/benchmark_id: expected {BENCHMARK_ID}")
    synthetic = payload.get("synthetic")
    if not isinstance(synthetic, bool):
        errors.append("/synthetic: expected boolean")
    elif synthetic and payload.get("notice") != SYNTHETIC_NOTICE:
        errors.append(f"/notice: expected {SYNTHETIC_NOTICE}")
    return errors


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_pair_rows(
    rows: Any, *, path: str, run: bool, synthetic: bool
) -> list[str]:
    if not isinstance(rows, list):
        return [f"{path}: expected array"]
    errors: list[str] = []
    seen: set[str] = set()
    paper_ids: set[str] = set()
    rank_rows: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        base = f"{path}/{index}"
        if not isinstance(row, dict):
            errors.append(f"{base}: expected object")
            continue
        identifier = row.get("pair_id")
        if not isinstance(identifier, str) or not _PAIR_ID.fullmatch(identifier):
            errors.append(f"{base}/pair_id: invalid pair ID")
        elif identifier in seen:
            errors.append(f"{base}/pair_id: duplicate pair_id {identifier}")
        else:
            seen.add(identifier)
        for field in ("paper_a_id", "paper_b_id"):
            value = row.get(field)
            if not isinstance(value, str) or not _PAPER_ID.fullmatch(value):
                errors.append(f"{base}/{field}: invalid paper ID")
            else:
                paper_ids.add(value)
        if row.get("paper_a_id") == row.get("paper_b_id"):
            errors.append(f"{base}: pair papers must be distinct")
        if run:
            label = row.get("predicted_label")
            if isinstance(label, bool) or not isinstance(label, int) or label not in range(4):
                errors.append(f"{base}/predicted_label: expected integer label 0-3")
            if not isinstance(row.get("candidate"), bool):
                errors.append(f"{base}/candidate: expected boolean")
            if not _is_number(row.get("score")):
                errors.append(f"{base}/score: expected number")
            for paper_field, rank_field in (("paper_a_id", "rank_a"), ("paper_b_id", "rank_b")):
                rank = row.get(rank_field)
                if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
                    errors.append(f"{base}/{rank_field}: expected positive integer")
                elif isinstance(row.get(paper_field), str):
                    rank_rows.setdefault(row[paper_field], []).append(rank)
            if not isinstance(row.get("items"), list):
                errors.append(f"{base}/items: expected array")
            if row.get("status") != "pending_review":
                errors.append(f"{base}/status: expected pending_review")
        else:
            expected_packet_id = (
                f"packet_{identifier.split('_', 1)[1]}"
                if isinstance(identifier, str) and _PAIR_ID.fullmatch(identifier)
                else None
            )
            if row.get("packet_id") != expected_packet_id:
                errors.append(f"{base}/packet_id: does not match pair ID")
            if row.get("schema_version") != 1:
                errors.append(f"{base}/schema_version: expected 1")
            if row.get("benchmark_id") != BENCHMARK_ID:
                errors.append(f"{base}/benchmark_id: expected {BENCHMARK_ID}")
            if row.get("status") != "pending_review":
                errors.append(f"{base}/status: expected pending_review")
            sources = row.get("sources")
            expected_source_ids = {row.get("paper_a_id"), row.get("paper_b_id")}
            if (
                not isinstance(sources, list)
                or len(sources) != 2
                or not all(isinstance(source, dict) for source in sources)
                or {source.get("paper_id") for source in sources} != expected_source_ids
            ):
                errors.append(f"{base}/sources: expected exact two pair sources")
    expected_paper_count = 6 if synthetic else 12
    expected_pair_count = 15 if synthetic else 66
    if len(rows) != expected_pair_count:
        errors.append(f"{path}: expected exactly {expected_pair_count} pair records")
    if len(paper_ids) != expected_paper_count:
        errors.append(f"{path}: expected exactly {expected_paper_count} unique paper IDs")
    if len(paper_ids) == expected_paper_count:
        expected_pairs = {
            pair_id(first, second) for first, second in combinations(sorted(paper_ids), 2)
        }
        if seen != expected_pairs:
            errors.append(f"{path}: exact canonical pair closure required")
    if run:
        for paper, ranks in rank_rows.items():
            if sorted(ranks) != list(range(1, len(ranks) + 1)):
                errors.append(f"{path}: ranks for {paper} must be unique contiguous integers")
    return errors


def validate_prepared(payload: Any) -> list[str]:
    errors = _base_errors(payload, PREPARED_TYPE)
    if not isinstance(payload, dict):
        return errors
    errors.extend(_forbidden_errors(payload))
    provenance = payload.get("provenance")
    required_digests = (
        "source_manifest_sha256",
        "protocol_sha256",
        "prompt_sha256",
        "blinded_schema_sha256",
        "freeze_manifest_sha256",
    )
    if not isinstance(provenance, dict):
        errors.append("/provenance: expected object")
    else:
        for field in required_digests:
            value = provenance.get(field)
            if not isinstance(value, str) or not _SHA256.fullmatch(value):
                errors.append(f"/provenance/{field}: expected lowercase SHA-256")
    errors.extend(
        _validate_pair_rows(
            payload.get("packets"),
            path="/packets",
            run=False,
            synthetic=payload.get("synthetic") is True,
        )
    )
    if payload.get("status") != "prepared":
        errors.append("/status: expected prepared")
    return sorted(errors)


def validate_run(payload: Any) -> list[str]:
    errors = _base_errors(payload, RUN_TYPE)
    if not isinstance(payload, dict):
        return errors
    errors.extend(_forbidden_errors(payload))
    digest = payload.get("prepared_sha256")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        errors.append("/prepared_sha256: expected lowercase SHA-256")
    backend = payload.get("backend")
    if not isinstance(backend, dict) or not isinstance(backend.get("name"), str):
        errors.append("/backend: expected named backend object")
    seed = payload.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        errors.append("/seed: expected integer")
    errors.extend(
        _validate_pair_rows(
            payload.get("results"),
            path="/results",
            run=True,
            synthetic=payload.get("synthetic") is True,
        )
    )
    if payload.get("status") != "locked":
        errors.append("/status: expected locked")
    return sorted(errors)


def validate_score(payload: Any) -> list[str]:
    errors = _base_errors(payload, SCORE_TYPE)
    if not isinstance(payload, dict):
        return errors
    digest = payload.get("run_sha256")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        errors.append("/run_sha256: expected lowercase SHA-256")
    commitment = payload.get("gold_commitment")
    if not isinstance(commitment, dict):
        errors.append("/gold_commitment: expected object")
    else:
        digest = commitment.get("private_gold_sha256")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            errors.append("/gold_commitment/private_gold_sha256: expected lowercase SHA-256")
    calculation = payload.get("calculation")
    if not isinstance(calculation, dict):
        errors.append("/calculation: expected object")
    p7_digests = (
        payload.get("execution_manifest_sha256"),
        payload.get("lock_manifest_sha256"),
    )
    if any(value is not None for value in p7_digests):
        for field in ("execution_manifest_sha256", "lock_manifest_sha256"):
            value = payload.get(field)
            if not isinstance(value, str) or not _SHA256.fullmatch(value):
                errors.append(f"/{field}: expected lowercase SHA-256")
    metrics = payload.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        errors.append("/metrics: expected nonempty array")
    else:
        names: set[str] = set()
        for index, metric in enumerate(metrics):
            base = f"/metrics/{index}"
            if not isinstance(metric, dict):
                errors.append(f"{base}: expected object")
                continue
            name = metric.get("name")
            if not isinstance(name, str) or not name:
                errors.append(f"{base}/name: expected metric name")
            elif name in names:
                errors.append(f"{base}/name: duplicate metric name {name}")
            else:
                names.add(name)
            for field in ("numerator", "denominator"):
                if not _is_number(metric.get(field)) or metric.get(field) < 0:
                    errors.append(f"{base}/{field}: expected number")
            value = metric.get("value")
            if value is not None and not _is_number(value):
                errors.append(f"{base}/value: expected number or null")
            threshold_met = metric.get("threshold_met")
            if threshold_met is not None and not isinstance(threshold_met, bool):
                errors.append(f"{base}/threshold_met: expected boolean or null")
            if isinstance(name, str) and name in EXPECTED_P5_METRIC_CONTRACTS:
                expected_contract = EXPECTED_P5_METRIC_CONTRACTS[name]
                for field, expected_value in expected_contract.items():
                    output_field = {
                        "numerator": "numerator_definition",
                        "denominator": "denominator_definition",
                    }.get(field, field)
                    if metric.get(output_field) != expected_value:
                        errors.append(
                            f"{base}/{output_field}: does not match frozen metric contract"
                        )
                if not isinstance(metric.get("uncertainty_result"), dict):
                    errors.append(f"{base}/uncertainty_result: expected object")
            if _is_number(metric.get("numerator")) and _is_number(
                metric.get("denominator")
            ) and metric["numerator"] > metric["denominator"]:
                errors.append(f"{base}/numerator: cannot exceed denominator")
            if _is_number(value) and not 0.0 <= float(value) <= 1.0:
                errors.append(f"{base}/value: expected proportion between zero and one")
            if value is None and threshold_met is not None:
                errors.append(f"{base}/threshold_met: must be null when value is null")
            if value is not None and not isinstance(threshold_met, bool):
                errors.append(f"{base}/threshold_met: boolean required when value is defined")
            threshold = metric.get("threshold")
            if _is_number(value) and isinstance(threshold, Mapping) and isinstance(
                threshold_met, bool
            ):
                operator = threshold.get("operator")
                target = threshold.get("value")
                if _is_number(target):
                    expected_outcome = {
                        ">=": float(value) >= float(target),
                        "<=": float(value) <= float(target),
                        "==": math.isclose(
                            float(value), float(target), rel_tol=0.0, abs_tol=1e-12
                        ),
                    }.get(operator)
                    if expected_outcome is not None and threshold_met != expected_outcome:
                        errors.append(
                            f"{base}/threshold_met: inconsistent with value and frozen threshold"
                        )
        if names != set(EXPECTED_P5_THRESHOLDS) or len(metrics) != len(
            EXPECTED_P5_THRESHOLDS
        ):
            errors.append("/metrics: expected exact frozen metric names")
    if payload.get("status") != "scored":
        errors.append("/status: expected scored")
    return sorted(errors)
