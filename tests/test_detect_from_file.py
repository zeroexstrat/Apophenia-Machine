"""Agent-produced hypotheses enter through an atomic validated adapter."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from athanasor import cli as cli_module
from athanasor.config import Config
from athanasor.rejections import append_rejection
from athanasor.registry import Registry
from athanasor.skills import detect as detect_module
from tests.fixture_factory import (
    registry_entry,
    write_connection,
    write_exhaust,
    write_library,
    write_registry,
)


def _config(root: Path) -> Config:
    return Config(
        llm={},
        embeddings={"store_path": "athanasor/embeddings.store"},
        paths={},
        domains=["operations_research"],
        exhaustion={},
        project_root=str(root),
    )


def _workspace(root: Path, *, exhausted: bool = False) -> list[str]:
    ids = ["synthetic_003", "synthetic_001", "synthetic_002"]
    write_registry(
        root,
        [
            registry_entry(
                paper_id,
                status="exhausted" if exhausted else "ingested_only",
                depth=3 if exhausted else None,
            )
            for paper_id in ids
        ],
    )
    for paper_id in ids:
        write_library(root, paper_id)
        if exhausted:
            write_exhaust(root, paper_id)
    return ids


def _record() -> dict:
    ids = ["synthetic_003", "synthetic_001", "synthetic_002"]
    return {
        "schema_version": 1,
        "cluster_id": detect_module.stable_cluster_id(ids),
        "paper_ids": ids,
        "scope": "operations_research",
        "novelty": False,
        "summary": "Synthetic queue policies leave one allocation question unresolved.",
        "status": "accepted",
        "gaps": [
            {
                "gap_type": "missing_experiment",
                "description": "The synthetic records do not compare delay under demand shifts.",
                "novelty": False,
                "supporting_papers": ["synthetic_003", "synthetic_001"],
                "supporting_evidence": "Synthetic claims describe policies but no demand-shift comparison.",
                "significance": "The comparison would bound an operational failure mode.",
                "feasibility": 5,
                "suggested_approach": "Simulate both policies under a fixed three-regime demand trace.",
                "confidence": 4,
                "rank": 1,
                "references": ["Synthetic claim 1"],
            }
        ],
    }


def _triage() -> dict:
    return {
        "decision": "rejected",
        "reviewer": "reviewer@example",
        "note": "The same synthetic evidence was already adjudicated.",
        "reviewed_at": "2026-07-11T12:00:00+00:00",
    }


def test_stable_cluster_id_is_order_independent_and_bounded() -> None:
    first = detect_module.stable_cluster_id(["synthetic_003", "synthetic_001", "synthetic_002"])
    second = detect_module.stable_cluster_id(["synthetic_002", "synthetic_003", "synthetic_001"])

    assert first == second
    assert first.startswith("cluster_")
    assert len(first) == len("cluster_") + 12


def test_load_agent_hypotheses_accepts_list_and_exact_wrapper(tmp_path: Path) -> None:
    bare = tmp_path / "bare.json"
    wrapped = tmp_path / "wrapped.json"
    bare.write_text(json.dumps([_record()]), encoding="utf-8")
    wrapped.write_text(json.dumps({"hypotheses": [_record()]}), encoding="utf-8")

    assert detect_module.load_agent_hypotheses(bare) == [_record()]
    assert detect_module.load_agent_hypotheses(wrapped) == [_record()]


@pytest.mark.parametrize(
    "payload",
    ["not-json", json.dumps({"records": []}), json.dumps(["not-an-object"])],
)
def test_load_agent_hypotheses_rejects_invalid_packets(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError):
        detect_module.load_agent_hypotheses(path)


def test_apply_agent_hypotheses_normalizes_and_persists_pending_record(tmp_path: Path) -> None:
    ids = _workspace(tmp_path)

    outputs = detect_module.apply_agent_hypotheses([_record()], config=_config(tmp_path))

    assert len(outputs) == 1
    output = outputs[0]
    assert output["cluster_id"] == detect_module.stable_cluster_id(ids)
    assert output["paper_ids"] == sorted(ids)
    assert output["status"] == "pending_review"
    destination = Path(output["file"])
    persisted = yaml.safe_load(destination.read_text(encoding="utf-8"))
    assert "file" not in persisted
    assert persisted["status"] == "pending_review"
    registry = Registry(tmp_path / "albedo" / "registry.jsonl")
    assert all(registry.get(paper_id)["detected"] is True for paper_id in ids)


def test_apply_agent_hypotheses_is_idempotent(tmp_path: Path) -> None:
    _workspace(tmp_path)

    first = detect_module.apply_agent_hypotheses([_record()], config=_config(tmp_path))[0]
    registry_before = (tmp_path / "albedo" / "registry.jsonl").read_bytes()
    second = detect_module.apply_agent_hypotheses([first], config=_config(tmp_path))[0]

    assert second == first
    assert (tmp_path / "albedo" / "registry.jsonl").read_bytes() == registry_before


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda record: record.update(paper_ids=["synthetic_001", "synthetic_002"]), "three distinct"),
        (
            lambda record: record.update(
                paper_ids=["synthetic_001", "synthetic_002", "synthetic_999"],
                cluster_id=detect_module.stable_cluster_id(
                    ["synthetic_001", "synthetic_002", "synthetic_999"]
                ),
            ),
            "registry",
        ),
        (lambda record: record.update(cluster_id="cluster_wrong"), "cluster_id"),
        (lambda record: record["gaps"][0].update(supporting_papers=["synthetic_999"]), "outside cluster"),
        (lambda record: record.pop("summary"), "summary"),
    ],
)
def test_apply_agent_hypotheses_rejects_invalid_records(
    tmp_path: Path,
    mutation,
    message: str,
) -> None:
    _workspace(tmp_path)
    record = _record()
    mutation(record)

    with pytest.raises(ValueError, match=message):
        detect_module.apply_agent_hypotheses([record], config=_config(tmp_path))

    assert not list((tmp_path / "rubedo" / "hypotheses").glob("*.yaml"))


def test_apply_agent_hypotheses_rejects_duplicate_cluster_atomically(tmp_path: Path) -> None:
    _workspace(tmp_path)
    registry_path = tmp_path / "albedo" / "registry.jsonl"
    registry_before = registry_path.read_bytes()

    with pytest.raises(ValueError, match="duplicate cluster"):
        detect_module.apply_agent_hypotheses([_record(), _record()], config=_config(tmp_path))

    assert registry_path.read_bytes() == registry_before
    assert not list((tmp_path / "rubedo" / "hypotheses").glob("*.yaml"))


def test_apply_agent_hypotheses_validates_entire_packet_before_writes(tmp_path: Path) -> None:
    _workspace(tmp_path)
    invalid = _record()
    invalid["paper_ids"] = ["synthetic_001", "synthetic_002", "synthetic_999"]
    registry_path = tmp_path / "albedo" / "registry.jsonl"
    registry_before = registry_path.read_bytes()

    with pytest.raises(ValueError, match="record 2"):
        detect_module.apply_agent_hypotheses([_record(), invalid], config=_config(tmp_path))

    assert registry_path.read_bytes() == registry_before
    assert not list((tmp_path / "rubedo" / "hypotheses").glob("*.yaml"))


def test_apply_agent_hypotheses_suppresses_same_rejected_evidence(tmp_path: Path) -> None:
    _workspace(tmp_path)
    record = _record()
    append_rejection(
        tmp_path / "athanasor" / "lapis" / "rejections.jsonl",
        record,
        _triage(),
    )

    outputs = detect_module.apply_agent_hypotheses([record], config=_config(tmp_path))

    assert outputs == [
        {"cluster_id": record["cluster_id"], "status": "suppressed_rejection"}
    ]
    assert not list((tmp_path / "rubedo" / "hypotheses").glob("*.yaml"))


def test_apply_agent_hypotheses_allows_changed_evidence(tmp_path: Path) -> None:
    _workspace(tmp_path)
    record = _record()
    append_rejection(
        tmp_path / "athanasor" / "lapis" / "rejections.jsonl",
        record,
        _triage(),
    )
    changed = deepcopy(record)
    changed["gaps"][0]["supporting_evidence"] = "A new synthetic run changes the evidence packet."

    output = detect_module.apply_agent_hypotheses([changed], config=_config(tmp_path))[0]

    assert output["status"] == "pending_review"
    assert Path(output["file"]).exists()


def test_apply_agent_hypotheses_rejects_conflicting_collision(tmp_path: Path) -> None:
    _workspace(tmp_path)
    detect_module.apply_agent_hypotheses([_record()], config=_config(tmp_path))
    changed = _record()
    changed["summary"] = "Conflicting generated wording for the same cluster."

    with pytest.raises(ValueError, match="collision"):
        detect_module.apply_agent_hypotheses([changed], config=_config(tmp_path))


def test_apply_agent_hypotheses_rolls_back_commit_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path)
    registry_path = tmp_path / "albedo" / "registry.jsonl"
    registry_before = registry_path.read_bytes()
    original_update = Registry.update
    calls = 0

    def fail_second_update(self, paper_id, fields):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated registry failure")
        return original_update(self, paper_id, fields)

    monkeypatch.setattr(Registry, "update", fail_second_update)

    with pytest.raises(RuntimeError, match="simulated registry failure"):
        detect_module.apply_agent_hypotheses([_record()], config=_config(tmp_path))

    assert registry_path.read_bytes() == registry_before
    assert not list((tmp_path / "rubedo" / "hypotheses").glob("*.yaml"))


def test_no_llm_detect_writes_no_hypothesis(tmp_path: Path) -> None:
    ids = _workspace(tmp_path, exhausted=True)
    write_connection(tmp_path, ids[0], ids[1])
    write_connection(tmp_path, ids[1], ids[2])

    outputs = detect_module.detect(config=_config(tmp_path), llm=None, all_scope=True)

    assert outputs == []
    assert not list((tmp_path / "rubedo" / "hypotheses").glob("*.yaml"))


def test_detect_from_file_cli_avoids_llm_and_rejects_flag_mixing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path)
    packet = tmp_path / "hypotheses.json"
    packet.write_text(json.dumps([_record()]), encoding="utf-8")
    monkeypatch.setenv("AZOTH_PROJECT_ROOT", str(tmp_path))

    def fail_llm_load(no_llm: bool):
        raise AssertionError("file import must not load an LLM")

    monkeypatch.setattr(cli_module, "_load_skill_config", fail_llm_load)
    runner = CliRunner()

    success = runner.invoke(
        cli_module.main,
        ["detect", "--from-file", str(packet), "--json", "--no-auto-checkpoint"],
    )
    mixed = runner.invoke(
        cli_module.main,
        ["detect", "--from-file", str(packet), "--all", "--no-auto-checkpoint"],
    )
    no_llm = runner.invoke(
        cli_module.main,
        ["detect", "--from-file", str(packet), "--no-llm", "--no-auto-checkpoint"],
    )

    assert success.exit_code == 0, success.output
    assert json.loads(success.output)[0]["status"] == "pending_review"
    assert mixed.exit_code != 0
    assert "exactly one mode" in mixed.output.lower()
    assert no_llm.exit_code != 0
    assert "cannot be combined" in no_llm.output.lower()
