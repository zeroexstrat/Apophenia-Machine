"""Agent-produced connection records enter through an atomic validated adapter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from athanasor import cli as cli_module
from athanasor.config import Config
from athanasor.registry import Registry
from athanasor.skills import connect as connect_module
from tests.fixture_factory import registry_entry, write_library, write_registry


def _config(root: Path) -> Config:
    return Config(
        llm={},
        embeddings={
            "store_path": "athanasor/embeddings.store",
            "model": "all-MiniLM-L6-v2",
            "similarity_threshold": 0.82,
        },
        paths={},
        domains=["operations_research", "ML"],
        exhaustion={},
        project_root=str(root),
    )


def _workspace(root: Path, *, cross_domain: bool = False) -> None:
    a_domain = "operations_research"
    b_domain = "ML" if cross_domain else a_domain
    write_registry(
        root,
        [
            registry_entry("synthetic_001", status="ingested_only", depth=None, domain=a_domain),
            registry_entry("synthetic_002", status="ingested_only", depth=None, domain=b_domain),
        ],
    )
    write_library(root, "synthetic_001", domain=a_domain)
    write_library(root, "synthetic_002", domain=b_domain)


def _record(*, cross_domain: bool = False) -> dict:
    return {
        "schema_version": 1,
        "pair_scope": "cross_domain" if cross_domain else "within_domain",
        "paper_a_id": "synthetic_002",
        "paper_b_id": "synthetic_001",
        "pair_domains": {
            "paper_a_domain": "wrong-input-domain",
            "paper_b_domain": "wrong-input-domain",
        },
        "connection_type": "complementary_techniques",
        "description": "A bounded queue complements staged allocation under demand shifts.",
        "evidence_a": "Synthetic claim 1 defines the staged allocation rule.",
        "evidence_b": "Synthetic claim 1 defines the bounded queue invariant.",
        "confidence": 5,
        "confidence_raw": 5,
        "novelty": "non-obvious",
        "significance": "The combination exposes a measurable delay-capacity tradeoff.",
        "status": "accepted",
        "tags": ["bounded_queue", "resource_allocation"],
    }


def test_load_agent_connections_accepts_list_and_exact_wrapper(tmp_path: Path) -> None:
    bare = tmp_path / "bare.json"
    wrapped = tmp_path / "wrapped.json"
    bare.write_text(json.dumps([_record()]), encoding="utf-8")
    wrapped.write_text(json.dumps({"connections": [_record()]}), encoding="utf-8")

    assert connect_module.load_agent_connections(bare) == [_record()]
    assert connect_module.load_agent_connections(wrapped) == [_record()]


@pytest.mark.parametrize(
    "payload",
    ["not-json", json.dumps({"records": [_record()]}), json.dumps(["not-an-object"])],
)
def test_load_agent_connections_rejects_invalid_packets(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError):
        connect_module.load_agent_connections(path)


def test_apply_agent_connections_normalizes_and_persists_pending_record(tmp_path: Path) -> None:
    _workspace(tmp_path)

    outputs = connect_module.apply_agent_connections([_record()], config=_config(tmp_path))

    assert len(outputs) == 1
    output = outputs[0]
    assert output["paper_a_id"] == "synthetic_001"
    assert output["paper_b_id"] == "synthetic_002"
    assert output["status"] == "pending_review"
    assert output["confidence_raw"] == 5
    assert output["confidence"] == 5
    assert output["pair_domains"] == {
        "paper_a_domain": "operations_research",
        "paper_b_domain": "operations_research",
    }
    destination = Path(output["file"])
    persisted = yaml.safe_load(destination.read_text(encoding="utf-8"))
    assert "file" not in persisted
    assert persisted["status"] == "pending_review"

    registry = Registry(tmp_path / "albedo" / "registry.jsonl")
    assert registry.get("synthetic_001")["connected"] is True
    assert registry.get("synthetic_002")["connected"] is True
    analyzed = (tmp_path / "albedo" / "connections_analyzed.jsonl").read_text(encoding="utf-8")
    assert analyzed.count("synthetic_001::synthetic_002") == 1


def test_apply_agent_connections_applies_cross_domain_penalty_once(tmp_path: Path) -> None:
    _workspace(tmp_path, cross_domain=True)
    record = _record(cross_domain=True)
    record["confidence"] = 1
    record["confidence_raw"] = 5

    first = connect_module.apply_agent_connections([record], config=_config(tmp_path))[0]
    second = connect_module.apply_agent_connections([first], config=_config(tmp_path))[0]

    assert first["confidence_raw"] == 5
    assert first["confidence"] == 4
    assert second["confidence"] == 4
    analyzed = (tmp_path / "albedo" / "connections_analyzed.jsonl").read_text(encoding="utf-8")
    assert analyzed.count("synthetic_001::synthetic_002") == 1


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda record: record.update(paper_b_id="synthetic_002"), "distinct"),
        (lambda record: record.update(paper_b_id="synthetic_999"), "registry"),
        (lambda record: record.update(evidence_a="Unspecified"), "evidence_a"),
        (lambda record: record.pop("significance"), "significance"),
    ],
)
def test_apply_agent_connections_rejects_invalid_records(
    tmp_path: Path,
    mutation,
    message: str,
) -> None:
    _workspace(tmp_path)
    record = _record()
    mutation(record)

    with pytest.raises(ValueError, match=message):
        connect_module.apply_agent_connections([record], config=_config(tmp_path))

    assert not list((tmp_path / "citrinitas").rglob("*.yaml"))


def test_apply_agent_connections_rejects_duplicate_pair_atomically(tmp_path: Path) -> None:
    _workspace(tmp_path)
    registry_before = (tmp_path / "albedo" / "registry.jsonl").read_bytes()

    with pytest.raises(ValueError, match="duplicate pair"):
        connect_module.apply_agent_connections(
            [_record(), _record()],
            config=_config(tmp_path),
        )

    assert (tmp_path / "albedo" / "registry.jsonl").read_bytes() == registry_before
    assert not list((tmp_path / "citrinitas").rglob("*.yaml"))
    assert not (tmp_path / "albedo" / "connections_analyzed.jsonl").exists()


def test_apply_agent_connections_validates_entire_packet_before_writes(tmp_path: Path) -> None:
    _workspace(tmp_path)
    valid = _record()
    invalid = _record()
    invalid["paper_b_id"] = "synthetic_999"
    registry_before = (tmp_path / "albedo" / "registry.jsonl").read_bytes()

    with pytest.raises(ValueError, match="record 2"):
        connect_module.apply_agent_connections([valid, invalid], config=_config(tmp_path))

    assert (tmp_path / "albedo" / "registry.jsonl").read_bytes() == registry_before
    assert not list((tmp_path / "citrinitas").rglob("*.yaml"))
    assert not (tmp_path / "albedo" / "connections_analyzed.jsonl").exists()


def test_apply_agent_connections_rolls_back_commit_failure(
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
        connect_module.apply_agent_connections([_record()], config=_config(tmp_path))

    assert registry_path.read_bytes() == registry_before
    assert not list((tmp_path / "citrinitas").rglob("*.yaml"))
    assert not (tmp_path / "albedo" / "connections_analyzed.jsonl").exists()


def test_connect_from_file_cli_avoids_llm_and_rejects_flag_mixing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path)
    packet = tmp_path / "connections.json"
    packet.write_text(json.dumps([_record()]), encoding="utf-8")
    monkeypatch.setenv("AZOTH_PROJECT_ROOT", str(tmp_path))

    def fail_llm_load(no_llm: bool):
        raise AssertionError("file import must not load an LLM")

    monkeypatch.setattr(cli_module, "_load_skill_config", fail_llm_load)
    runner = CliRunner()

    success = runner.invoke(
        cli_module.main,
        ["connect", "--from-file", str(packet), "--json", "--no-auto-checkpoint"],
    )
    mixed = runner.invoke(
        cli_module.main,
        ["connect", "--from-file", str(packet), "--all", "--no-auto-checkpoint"],
    )
    no_llm = runner.invoke(
        cli_module.main,
        ["connect", "--from-file", str(packet), "--no-llm", "--no-auto-checkpoint"],
    )

    assert success.exit_code == 0, success.output
    assert json.loads(success.output)[0]["status"] == "pending_review"
    assert mixed.exit_code != 0
    assert "exactly one mode" in mixed.output.lower()
    assert no_llm.exit_code != 0
    assert "cannot be combined" in no_llm.output.lower()
