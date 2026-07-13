from __future__ import annotations

import os
import random
import re
import tempfile
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from athanasor.benchmark.protocol import (
    BenchmarkProtocolError,
    canonical_digest,
    canonical_json_bytes,
    canonical_pairs,
    validate_protocol,
    validate_sources,
)


_UTC_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


def build_adjudication_packet(
    sources: dict[str, Any], protocol: dict[str, Any]
) -> dict[str, Any]:
    pairs, anchor_ids, expected_presentations = _expected_topology(
        sources, protocol, operation="build adjudication packet"
    )
    return {
        "schema_version": 1,
        "artifact_type": "azoth_private_adjudication",
        "benchmark_id": sources["benchmark_id"],
        "source_manifest_sha256": canonical_digest(sources),
        "rubric_version": protocol["rubric_version"],
        "final_authority": protocol["adjudication"]["final_authority"],
        "canonical_pairs": pairs,
        "anchor_pair_ids": anchor_ids,
        "presentations": [
            {
                "presentation_id": presentation_id,
                "pair_id": pair_identifier,
                "label": None,
                "rationale": "",
                "evidence_spans": [],
            }
            for presentation_id, pair_identifier in expected_presentations.items()
        ],
        "gold_pairs": [],
        "freeze": None,
    }


def _expected_topology(
    sources: dict[str, Any], protocol: dict[str, Any], *, operation: str
) -> tuple[list[dict[str, str]], list[str], dict[str, str]]:
    errors = validate_sources(sources) + validate_protocol(protocol)
    if errors:
        raise BenchmarkProtocolError(f"cannot {operation}: " + "; ".join(errors))
    pairs = canonical_pairs([row["paper_id"] for row in sources["sources"]])
    repeat_count = int(protocol["adjudication"]["repeated_anchor_count"])
    anchors = sorted(row["pair_id"] for row in pairs)[:repeat_count]
    presentation_pairs = [row["pair_id"] for row in pairs] + anchors
    random.Random(int(protocol["adjudication"]["presentation_seed"])).shuffle(
        presentation_pairs
    )
    expected_presentations = {
        f"presentation_{index + 1:03d}": pair_identifier
        for index, pair_identifier in enumerate(presentation_pairs)
    }
    return pairs, anchors, expected_presentations


def _rating_errors(presentation: Any, index: int) -> list[str]:
    base = f"/presentations/{index}"
    if not isinstance(presentation, dict):
        return [f"{base}: expected object"]
    errors: list[str] = []
    label = presentation.get("label")
    if isinstance(label, bool) or not isinstance(label, int) or label not in range(4):
        errors.append(f"{base}/label: expected integer label 0-3")
    rationale = presentation.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        errors.append(f"{base}/rationale: expected nonempty rationale")
    spans = presentation.get("evidence_spans")
    if not isinstance(spans, list):
        errors.append(f"{base}/evidence_spans: expected evidence spans covering both papers")
    else:
        roles: set[str] = set()
        for span_index, span in enumerate(spans):
            span_base = f"{base}/evidence_spans/{span_index}"
            if not isinstance(span, dict):
                errors.append(f"{span_base}: expected object")
                continue
            role = span.get("paper_role")
            if role not in {"a", "b"}:
                errors.append(f"{span_base}/paper_role: expected a or b")
            else:
                roles.add(role)
            text = span.get("text")
            if not isinstance(text, str) or not text.strip():
                errors.append(f"{span_base}/text: expected nonempty evidence text")
        if roles != {"a", "b"}:
            errors.append(f"{base}/evidence_spans: must cover both papers")
    return errors


def _reconciled_gold_pairs(
    packet: dict[str, Any], sources: dict[str, Any], protocol: dict[str, Any]
) -> list[dict[str, Any]]:
    if not isinstance(packet, dict):
        raise BenchmarkProtocolError("cannot reconcile gold packet: expected object")
    expected_pairs, expected_anchors, expected_presentations = _expected_topology(
        sources, protocol, operation="reconcile gold packet"
    )
    expected_metadata = {
        "schema_version": 1,
        "artifact_type": "azoth_private_adjudication",
        "benchmark_id": sources["benchmark_id"],
        "source_manifest_sha256": canonical_digest(sources),
        "rubric_version": protocol["rubric_version"],
        "final_authority": protocol["adjudication"]["final_authority"],
    }
    for field, expected in expected_metadata.items():
        if packet.get(field) != expected:
            raise BenchmarkProtocolError(
                f"cannot reconcile gold packet: /{field}: expected {expected}"
            )
    if packet.get("canonical_pairs") != expected_pairs:
        raise BenchmarkProtocolError(
            "cannot reconcile gold packet: /canonical_pairs must equal the 66 public-source pairs"
        )
    if packet.get("anchor_pair_ids") != expected_anchors:
        raise BenchmarkProtocolError(
            "cannot reconcile gold packet: /anchor_pair_ids must equal the four protocol anchors"
        )

    presentations = packet.get("presentations")
    if not isinstance(presentations, list):
        raise BenchmarkProtocolError("cannot reconcile gold packet: /presentations: expected array")
    if len(presentations) != len(expected_presentations):
        raise BenchmarkProtocolError(
            f"cannot reconcile gold packet: /presentations: expected {len(expected_presentations)} records"
        )

    by_pair: dict[str, list[dict[str, Any]]] = defaultdict(list)
    errors: list[str] = []
    seen_presentation_ids: set[str] = set()
    for index, presentation in enumerate(presentations):
        base = f"/presentations/{index}"
        if not isinstance(presentation, dict):
            errors.append(f"{base}: expected object")
            continue
        presentation_id = presentation.get("presentation_id")
        if not isinstance(presentation_id, str) or presentation_id not in expected_presentations:
            errors.append(f"{base}/presentation_id: expected deterministic presentation ID")
        elif presentation_id in seen_presentation_ids:
            errors.append(f"{base}/presentation_id: duplicate presentation ID")
        else:
            seen_presentation_ids.add(presentation_id)
            expected_pair_id = expected_presentations[presentation_id]
            if presentation.get("pair_id") != expected_pair_id:
                errors.append(
                    f"{base}/pair_id: does not match deterministic presentation ID"
                )
        errors.extend(_rating_errors(presentation, index))
        if isinstance(presentation.get("pair_id"), str):
            by_pair[presentation["pair_id"]].append(presentation)

    if seen_presentation_ids != set(expected_presentations):
        errors.append("/presentations: exact deterministic presentation IDs required")

    for pair_identifier in expected_anchors:
        ratings = by_pair.get(pair_identifier, [])
        labels = [row.get("label") for row in ratings]
        valid_labels = len(ratings) == 2 and all(
            isinstance(label, int)
            and not isinstance(label, bool)
            and label in range(4)
            for label in labels
        )
        valid_annotations = len(ratings) == 2 and all(
            not _rating_errors(row, 0) for row in ratings
        )
        if valid_labels and labels[0] != labels[1]:
            raise BenchmarkProtocolError(
                "cannot reconcile gold packet: anchor ratings disagree "
                f"for {pair_identifier} at /label"
            )
        if valid_annotations:
            rationales = [row.get("rationale") for row in ratings]
            if all(isinstance(value, str) and value.strip() for value in rationales):
                if rationales[0].strip() != rationales[1].strip():
                    raise BenchmarkProtocolError(
                        "cannot reconcile gold packet: anchor annotations disagree "
                        f"for {pair_identifier} at /rationale"
                    )
            evidence = [row.get("evidence_spans") for row in ratings]
            if all(isinstance(value, list) for value in evidence):
                if canonical_json_bytes(evidence[0]) != canonical_json_bytes(evidence[1]):
                    raise BenchmarkProtocolError(
                        "cannot reconcile gold packet: anchor annotations disagree "
                        f"for {pair_identifier} at /evidence_spans"
                    )
    if errors:
        raise BenchmarkProtocolError("cannot reconcile gold packet: " + "; ".join(errors))

    expected_counts = Counter({row["pair_id"]: 1 for row in expected_pairs})
    expected_counts.update(expected_anchors)
    actual_counts = Counter(
        {pair_identifier: len(rows) for pair_identifier, rows in by_pair.items()}
    )
    if actual_counts != expected_counts:
        raise BenchmarkProtocolError(
            "cannot reconcile gold packet: /presentations must contain all 66 pairs "
            "once and the four anchors twice"
        )

    pair_by_id = {row["pair_id"]: row for row in expected_pairs}
    gold_pairs: list[dict[str, Any]] = []
    for pair_identifier in sorted(pair_by_id):
        pair = pair_by_id[pair_identifier]
        ratings = by_pair[pair_identifier]
        if len({row["label"] for row in ratings}) != 1:
            if pair_identifier in expected_anchors:
                raise BenchmarkProtocolError(
                    "cannot reconcile gold packet: anchor ratings disagree "
                    f"for {pair_identifier} at /label"
                )
        # Repeated anchors reached here only after exact canonical annotation
        # agreement, so either presentation yields the same committed content.
        annotation = ratings[0]
        gold_pairs.append(
            {
                "pair_id": pair_identifier,
                "paper_a_id": pair["paper_a_id"],
                "paper_b_id": pair["paper_b_id"],
                "label": annotation["label"],
                "rationale": annotation["rationale"].strip(),
                "evidence_spans": deepcopy(annotation["evidence_spans"]),
            }
        )
    return gold_pairs


def reconcile_gold_packet(
    packet: dict[str, Any], sources: dict[str, Any], protocol: dict[str, Any]
) -> dict[str, Any]:
    gold_pairs = _reconciled_gold_pairs(packet, sources, protocol)

    reconciled = deepcopy(packet)
    reconciled["gold_pairs"] = gold_pairs
    reconciled["freeze"] = {
        "freeze_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    return reconciled


def validate_gold_packet(
    payload: Any, sources: dict[str, Any], protocol: dict[str, Any]
) -> list[str]:
    errors = validate_sources(sources) + validate_protocol(protocol)
    if not isinstance(payload, dict):
        return errors + ["/: expected object"]
    try:
        reconciled_gold = _reconciled_gold_pairs(payload, sources, protocol)
    except BenchmarkProtocolError as exc:
        errors.append(str(exc))
    else:
        if payload.get("gold_pairs") != reconciled_gold:
            errors.append(
                "/gold_pairs: must exactly equal canonical reconciliation of presentations"
            )

    freeze = payload.get("freeze")
    freeze_time = freeze.get("freeze_time") if isinstance(freeze, dict) else None
    if not isinstance(freeze_time, str) or not _UTC_TIMESTAMP.fullmatch(freeze_time):
        errors.append("/freeze/freeze_time: expected UTC timestamp")
    return errors


def gold_commitment(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise BenchmarkProtocolError("cannot commit gold packet: expected object")
    freeze = payload.get("freeze")
    freeze_time = freeze.get("freeze_time") if isinstance(freeze, dict) else None
    if not isinstance(freeze_time, str) or not _UTC_TIMESTAMP.fullmatch(freeze_time):
        raise BenchmarkProtocolError("cannot commit gold packet: missing valid UTC freeze time")
    gold_pairs = payload.get("gold_pairs")
    if not isinstance(gold_pairs, list) or len(gold_pairs) != 66:
        raise BenchmarkProtocolError("cannot commit gold packet: expected 66 gold pairs")
    try:
        ordered_gold = sorted(gold_pairs, key=lambda row: row["pair_id"])
    except (KeyError, TypeError):
        raise BenchmarkProtocolError("cannot commit gold packet: malformed gold pairs") from None
    committed = {
        "benchmark_id": payload.get("benchmark_id"),
        "source_manifest_sha256": payload.get("source_manifest_sha256"),
        "rubric_version": payload.get("rubric_version"),
        "final_authority": payload.get("final_authority"),
        "gold_pairs": ordered_gold,
        "freeze_time": freeze_time,
    }
    return {
        "algorithm": "sha256-canonical-json-v1",
        "private_gold_sha256": canonical_digest(committed),
        "schema_version": 1,
        "freeze_time": freeze_time,
    }


def ensure_outside_repository(path: Path, repo_root: Path) -> Path:
    resolved_path = Path(path).expanduser().resolve()
    resolved_repo = Path(repo_root).expanduser().resolve()
    if resolved_path == resolved_repo or resolved_path.is_relative_to(resolved_repo):
        raise BenchmarkProtocolError("private output must be outside the repository")
    return resolved_path


def atomic_write_private(path: Path, payload: Any, repo_root: Path) -> Path:
    destination = ensure_outside_repository(path, repo_root)
    parent = destination.parent
    parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    parent.chmod(0o700)
    # Resolve again after creating the parent so an existing parent symlink
    # cannot redirect the write into the repository.
    destination = ensure_outside_repository(destination, repo_root)
    descriptor = -1
    temporary_name: str | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=parent)
        os.fchmod(descriptor, 0o600)
        rendered = canonical_json_bytes(payload) + b"\n"
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
        temporary_name = None
        destination.chmod(0o600)
        directory_descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as exc:
        raise BenchmarkProtocolError(f"cannot atomically write private packet: {exc}") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass
    return destination
