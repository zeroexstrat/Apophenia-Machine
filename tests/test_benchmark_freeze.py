from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path

import pytest

from athanasor.benchmark.freeze import (
    atomic_write_private,
    build_adjudication_packet,
    ensure_outside_repository,
    gold_commitment,
    reconcile_gold_packet,
    validate_gold_packet,
)
from athanasor.benchmark.protocol import BenchmarkProtocolError
from tests.benchmark_fixtures import (
    completed_packet_fixture,
    protocol_fixture,
    reconciled_packet_fixture,
    source_manifest_fixture,
)


def test_packet_has_66_pairs_plus_four_repeats() -> None:
    packet = build_adjudication_packet(source_manifest_fixture(), protocol_fixture())
    assert len(packet["canonical_pairs"]) == 66
    assert len(packet["presentations"]) == 70
    assert len({row["pair_id"] for row in packet["canonical_pairs"]}) == 66


def test_packet_construction_is_deterministic() -> None:
    first = build_adjudication_packet(source_manifest_fixture(), protocol_fixture())
    second = build_adjudication_packet(source_manifest_fixture(), protocol_fixture())
    assert first == second


def test_reconcile_refuses_inconsistent_anchors() -> None:
    packet = completed_packet_fixture(inconsistent_anchor=True)
    with pytest.raises(BenchmarkProtocolError, match="anchor ratings disagree"):
        reconcile_gold_packet(packet, source_manifest_fixture(), protocol_fixture())


def _second_anchor_presentation(packet: dict) -> dict:
    anchor = packet["anchor_pair_ids"][0]
    return [row for row in packet["presentations"] if row["pair_id"] == anchor][1]


def test_reconcile_refuses_anchor_rationale_drift() -> None:
    packet = completed_packet_fixture()
    _second_anchor_presentation(packet)["rationale"] = "A different synthetic rationale."
    with pytest.raises(
        BenchmarkProtocolError,
        match=r"anchor annotations disagree.*rationale",
    ):
        reconcile_gold_packet(packet, source_manifest_fixture(), protocol_fixture())


def test_reconcile_refuses_anchor_evidence_drift() -> None:
    packet = completed_packet_fixture()
    _second_anchor_presentation(packet)["evidence_spans"][0]["text"] = (
        "Different synthetic evidence."
    )
    with pytest.raises(
        BenchmarkProtocolError,
        match=r"anchor annotations disagree.*evidence_spans",
    ):
        reconcile_gold_packet(packet, source_manifest_fixture(), protocol_fixture())


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("label", True, "integer label 0-3"),
        ("label", [], "integer label 0-3"),
        ("label", 4, "integer label 0-3"),
        ("rationale", " ", "nonempty rationale"),
        ("evidence_spans", [{"paper_role": "a", "text": "only one"}], "both papers"),
    ],
)
def test_reconcile_validates_every_rating(field: str, value: object, message: str) -> None:
    packet = completed_packet_fixture()
    packet["presentations"][0][field] = value
    with pytest.raises(BenchmarkProtocolError, match=message):
        reconcile_gold_packet(packet, source_manifest_fixture(), protocol_fixture())


def test_reconcile_produces_66_sorted_gold_pairs() -> None:
    packet = reconciled_packet_fixture()
    assert len(packet["gold_pairs"]) == 66
    assert [row["pair_id"] for row in packet["gold_pairs"]] == sorted(
        row["pair_id"] for row in packet["gold_pairs"]
    )
    assert validate_gold_packet(packet, source_manifest_fixture(), protocol_fixture()) == []


@pytest.mark.parametrize("field", ["label", "rationale", "evidence_spans"])
def test_validate_rejects_post_reconciliation_anchor_tamper(field: str) -> None:
    packet = reconciled_packet_fixture()
    target = _second_anchor_presentation(packet)
    if field == "label":
        target[field] = 1
    elif field == "rationale":
        target[field] = "Tampered synthetic rationale."
    else:
        target[field][0]["text"] = "Tampered synthetic evidence."
    errors = validate_gold_packet(packet, source_manifest_fixture(), protocol_fixture())
    assert any("anchor" in error and field in error for error in errors)


@pytest.mark.parametrize("field", ["label", "rationale", "evidence_spans"])
def test_validate_rejects_consistent_post_reconciliation_anchor_tamper(field: str) -> None:
    packet = reconciled_packet_fixture()
    anchor = packet["anchor_pair_ids"][0]
    targets = [row for row in packet["presentations"] if row["pair_id"] == anchor]
    for target in targets:
        if field == "label":
            target[field] = 1
        elif field == "rationale":
            target[field] = "Consistently tampered synthetic rationale."
        else:
            target[field][0]["text"] = "Consistently tampered synthetic evidence."
    errors = validate_gold_packet(packet, source_manifest_fixture(), protocol_fixture())
    assert any("canonical reconciliation" in error for error in errors)


@pytest.mark.parametrize("field", ["label", "rationale", "evidence_spans"])
def test_validate_rejects_post_reconciliation_nonanchor_tamper(field: str) -> None:
    packet = reconciled_packet_fixture()
    target = next(
        row
        for row in packet["presentations"]
        if row["pair_id"] not in packet["anchor_pair_ids"]
    )
    if field == "label":
        target[field] = 1
    elif field == "rationale":
        target[field] = "Tampered synthetic rationale."
    else:
        target[field][0]["text"] = "Tampered synthetic evidence."
    errors = validate_gold_packet(packet, source_manifest_fixture(), protocol_fixture())
    assert any("canonical reconciliation" in error for error in errors)


def test_validate_rejects_independently_injected_gold() -> None:
    packet = reconciled_packet_fixture()
    packet["gold_pairs"][0]["label"] = 3
    errors = validate_gold_packet(packet, source_manifest_fixture(), protocol_fixture())
    assert any("canonical reconciliation" in error for error in errors)


def test_reconcile_rejects_removed_anchor_definition() -> None:
    packet = completed_packet_fixture()
    packet["anchor_pair_ids"].pop()
    with pytest.raises(BenchmarkProtocolError, match="anchor_pair_ids"):
        reconcile_gold_packet(packet, source_manifest_fixture(), protocol_fixture())


def test_reconcile_rejects_removed_anchor_repeat() -> None:
    packet = completed_packet_fixture()
    repeated = packet["anchor_pair_ids"][0]
    matching = [
        index
        for index, row in enumerate(packet["presentations"])
        if row["pair_id"] == repeated
    ]
    packet["presentations"].pop(matching[-1])
    with pytest.raises(BenchmarkProtocolError, match="presentations"):
        reconcile_gold_packet(packet, source_manifest_fixture(), protocol_fixture())


def test_reconcile_rejects_consistently_shrunken_canonical_topology() -> None:
    packet = completed_packet_fixture()
    removed = packet["canonical_pairs"].pop()
    packet["presentations"] = [
        row for row in packet["presentations"] if row["pair_id"] != removed["pair_id"]
    ]
    with pytest.raises(BenchmarkProtocolError, match="canonical_pairs"):
        reconcile_gold_packet(packet, source_manifest_fixture(), protocol_fixture())


@pytest.mark.parametrize("duplicate_id", [False, True])
def test_reconcile_rejects_extra_or_duplicate_presentation(duplicate_id: bool) -> None:
    packet = completed_packet_fixture()
    extra = deepcopy(packet["presentations"][0])
    if not duplicate_id:
        extra["presentation_id"] = "presentation_071"
    packet["presentations"].append(extra)
    with pytest.raises(BenchmarkProtocolError, match="presentations"):
        reconcile_gold_packet(packet, source_manifest_fixture(), protocol_fixture())


def test_reconcile_rejects_bad_presentation_id() -> None:
    packet = completed_packet_fixture()
    packet["presentations"][0]["presentation_id"] = "presentation_bad"
    with pytest.raises(BenchmarkProtocolError, match="presentation_id"):
        reconcile_gold_packet(packet, source_manifest_fixture(), protocol_fixture())


def test_reconcile_rejects_malformed_presentation() -> None:
    packet = completed_packet_fixture()
    packet["presentations"][0] = {"presentation_id": "presentation_001"}
    with pytest.raises(BenchmarkProtocolError, match="presentations/0"):
        reconcile_gold_packet(packet, source_manifest_fixture(), protocol_fixture())


def test_validate_preserves_presentation_order_independence() -> None:
    packet = reconciled_packet_fixture()
    packet["presentations"].reverse()
    assert validate_gold_packet(packet, source_manifest_fixture(), protocol_fixture()) == []


def test_commitment_changes_when_one_label_changes() -> None:
    original = reconciled_packet_fixture()
    changed = deepcopy(original)
    changed["gold_pairs"][0]["label"] = 3
    assert gold_commitment(original) != gold_commitment(changed)


def test_commitment_excludes_presentations_and_paths() -> None:
    original = reconciled_packet_fixture()
    changed = deepcopy(original)
    changed["presentations"].reverse()
    changed["private_path"] = "synthetic-private-location"
    assert gold_commitment(original) == gold_commitment(changed)


def test_private_write_refuses_repo_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(BenchmarkProtocolError, match="outside the repository"):
        atomic_write_private(repo / "gold.json", {}, repo)


def test_private_boundary_rejects_repo_equality_and_symlink_escape(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "repo-link").symlink_to(repo, target_is_directory=True)
    with pytest.raises(BenchmarkProtocolError, match="outside the repository"):
        ensure_outside_repository(repo, repo)
    with pytest.raises(BenchmarkProtocolError, match="outside the repository"):
        ensure_outside_repository(outside / "repo-link" / "gold.json", repo)


def test_atomic_private_write_sets_permissions_and_replaces_content(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    destination = tmp_path / "private" / "gold.json"
    resolved = atomic_write_private(destination, {"synthetic": 1}, repo)
    atomic_write_private(destination, {"synthetic": 2}, repo)
    assert resolved == destination.resolve()
    assert json.loads(destination.read_text(encoding="utf-8")) == {"synthetic": 2}
    assert os.stat(destination.parent).st_mode & 0o777 == 0o700
    assert os.stat(destination).st_mode & 0o777 == 0o600
    assert list(destination.parent.iterdir()) == [destination]
