"""Durable Rubedo rejection fingerprints and promotion transactions."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from athanasor.config import Config
from athanasor.rejections import (
    append_rejection,
    candidate_fingerprint,
    evidence_fingerprint,
    is_rejected,
    load_rejections,
)
from athanasor.skills import promote as promote_module
from tests.fixture_factory import registry_entry, write_hypothesis, write_registry


@pytest.fixture(autouse=True)
def _skip_vigil_for_rejection_unit_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """These transaction tests use intentionally incomplete paper fixtures."""
    monkeypatch.setenv("AZOTH_SKIP_VIGIL", "1")


def _config(root: Path) -> Config:
    return Config(
        llm={},
        embeddings={},
        paths={},
        domains=["operations_research"],
        exhaustion={},
        project_root=str(root),
    )


def _hypothesis() -> dict:
    return {
        "schema_version": 1,
        "cluster_id": "cluster_synthetic",
        "paper_ids": ["synthetic_003", "synthetic_001", "synthetic_002"],
        "scope": "Operations Research",
        "novelty": False,
        "summary": "One synthetic allocation question remains unresolved.",
        "status": "pending_review",
        "gaps": [
            {
                "gap_type": "missing_experiment",
                "description": "Compare delay across demand regimes.",
                "novelty": False,
                "supporting_papers": ["synthetic_002", "synthetic_001"],
                "supporting_evidence": "Synthetic claims omit a demand-shift comparison.",
                "significance": "The comparison bounds an operational failure mode.",
                "feasibility": 5,
                "suggested_approach": "Run the fixed synthetic demand trace.",
                "confidence": 4,
                "references": ["Synthetic claim 2", "Synthetic claim 1"],
            }
        ],
    }


def _triage() -> dict:
    return {
        "decision": "rejected",
        "status_after": "rejected",
        "reviewer": "reviewer@example",
        "note": "The same evidence has already been adjudicated.",
        "reviewed_at": "2026-07-11T12:00:00+00:00",
        "command": "azoth promote",
    }


def test_candidate_fingerprint_ignores_order_wording_and_status() -> None:
    original = _hypothesis()
    reworded = deepcopy(original)
    reworded["paper_ids"] = list(reversed(reworded["paper_ids"]))
    reworded["scope"] = "  operations   research "
    reworded["summary"] = "Different generated wording."
    reworded["status"] = "investigate"
    reworded["gaps"][0]["description"] = "A differently worded gap."

    assert candidate_fingerprint(original) == candidate_fingerprint(reworded)


def test_evidence_fingerprint_is_order_stable() -> None:
    original = _hypothesis()
    reordered = deepcopy(original)
    reordered["gaps"][0]["supporting_papers"].reverse()
    reordered["gaps"][0]["references"].reverse()

    assert evidence_fingerprint(original) == evidence_fingerprint(reordered)


def test_evidence_fingerprint_changes_with_supporting_evidence() -> None:
    original = _hypothesis()
    changed = deepcopy(original)
    changed["gaps"][0]["supporting_evidence"] = "A new synthetic experiment now supports the gap."

    assert evidence_fingerprint(original) != evidence_fingerprint(changed)


def test_append_rejection_is_idempotent(tmp_path: Path) -> None:
    ledger = tmp_path / "rejections.jsonl"

    first = append_rejection(ledger, _hypothesis(), _triage())
    second = append_rejection(ledger, _hypothesis(), _triage())

    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert rows == [first]
    assert second == first
    assert is_rejected(ledger, _hypothesis()) is True


def test_load_rejections_reports_malformed_rows(tmp_path: Path) -> None:
    ledger = tmp_path / "rejections.jsonl"
    ledger.write_text('{"schema_version": 1}\nnot-json\n', encoding="utf-8")

    entries, errors = load_rejections(ledger)

    assert entries == []
    assert len(errors) == 2
    assert "line 1" in errors[0].lower()
    assert "line 2" in errors[1].lower()


def test_promote_rejected_records_fingerprint_before_completion(tmp_path: Path) -> None:
    ids = ["synthetic_001", "synthetic_002", "synthetic_003"]
    write_hypothesis(tmp_path, "cluster_synthetic", ids)
    write_registry(tmp_path, [registry_entry(paper_id, status="ingested_only", depth=None) for paper_id in ids])

    result = promote_module.run_promote(
        "cluster_synthetic",
        decision="rejected",
        reviewer="reviewer@example",
        note="The same evidence has already been adjudicated.",
        config=_config(tmp_path),
    )

    promoted = yaml.safe_load(result.read_text(encoding="utf-8"))
    ledger = tmp_path / "athanasor" / "lapis" / "rejections.jsonl"
    entries, errors = load_rejections(ledger)
    assert errors == []
    assert len(entries) == 1
    assert promoted["status"] == "rejected"
    assert entries[0]["candidate_fingerprint"] == candidate_fingerprint(promoted)
    assert entries[0]["evidence_fingerprint"] == evidence_fingerprint(promoted)


def test_promote_accepted_does_not_write_rejection_ledger(tmp_path: Path) -> None:
    ids = ["synthetic_001", "synthetic_002", "synthetic_003"]
    write_hypothesis(tmp_path, "cluster_synthetic", ids)
    write_registry(tmp_path, [registry_entry(paper_id, status="ingested_only", depth=None) for paper_id in ids])

    promote_module.run_promote(
        "cluster_synthetic",
        decision="accepted",
        reviewer="reviewer@example",
        note="Accepted for a synthetic workflow check.",
        config=_config(tmp_path),
    )

    assert not (tmp_path / "athanasor" / "lapis" / "rejections.jsonl").exists()


def test_promote_rolls_back_hypothesis_registry_and_ledger_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = ["synthetic_001", "synthetic_002", "synthetic_003"]
    hypothesis_path = write_hypothesis(tmp_path, "cluster_synthetic", ids)
    registry_path = write_registry(
        tmp_path,
        [registry_entry(paper_id, status="ingested_only", depth=None) for paper_id in ids],
    )
    hypothesis_before = hypothesis_path.read_bytes()
    registry_before = registry_path.read_bytes()

    def fail_registry_update(root: Path, paper_ids: list[str], decision: str, timestamp: str) -> None:
        raise RuntimeError("simulated registry failure")

    monkeypatch.setattr(promote_module, "_mark_registry_triaged", fail_registry_update)

    with pytest.raises(RuntimeError, match="simulated registry failure"):
        promote_module.run_promote(
            "cluster_synthetic",
            decision="rejected",
            reviewer="reviewer@example",
            note="The same evidence has already been adjudicated.",
            config=_config(tmp_path),
        )

    assert hypothesis_path.read_bytes() == hypothesis_before
    assert registry_path.read_bytes() == registry_before
    assert not (tmp_path / "athanasor" / "lapis" / "rejections.jsonl").exists()
