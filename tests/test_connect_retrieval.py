"""Deterministic connect ranks retrieval candidates without inventing connections."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from click.testing import CliRunner

from athanasor import cli as cli_module
from athanasor.config import Config
from athanasor.registry import Registry
from athanasor.schemas import parse_schema, validate as validate_schema
from athanasor.skills.connect import connect
from tests.fixture_factory import (
    registry_entry,
    write_exhaust,
    write_library,
    write_registry,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _config(root: Path) -> Config:
    return Config(
        llm={},
        embeddings={
            "store_path": "athanasor/embeddings.store",
            "model": "all-MiniLM-L6-v2",
            "similarity_threshold": 0.82,
        },
        paths={},
        domains=["operations_research"],
        exhaustion={},
        project_root=str(root),
    )


def _workspace(root: Path) -> None:
    ids = ["synthetic_001", "synthetic_002"]
    write_registry(
        root,
        [
            registry_entry(
                paper_id,
                tags=["bounded_queue", "resource_allocation"],
            )
            for paper_id in ids
        ],
    )
    for paper_id in ids:
        write_library(root, paper_id)
        write_exhaust(root, paper_id)


def test_no_llm_connect_writes_only_retrieval_candidates(tmp_path: Path) -> None:
    _workspace(tmp_path)

    outputs = connect(config=_config(tmp_path), llm=None, all_scope=True)

    assert len(outputs) == 1
    candidate = outputs[0]
    assert candidate["artifact_type"] == "retrieval_candidate"
    assert candidate["pair_id"] == "synthetic_001::synthetic_002"
    assert candidate["paper_a_id"] == "synthetic_001"
    assert candidate["paper_b_id"] == "synthetic_002"
    assert candidate["shared_tags"] == ["bounded_queue", "resource_allocation"]
    assert candidate["status"] == "pending_assessment"
    assert candidate["metadata"]["method"] == "deterministic_retrieval"
    assert "connection_type" not in candidate
    assert "novelty" not in candidate
    assert "confidence" not in candidate

    paths = list((tmp_path / "citrinitas" / "retrieval_candidates").glob("*.yaml"))
    assert len(paths) == 1
    persisted = yaml.safe_load(paths[0].read_text(encoding="utf-8"))
    assert persisted == candidate
    assert not list((tmp_path / "citrinitas" / "within_domain").rglob("*.yaml"))
    assert not list((tmp_path / "citrinitas" / "cross_domain").rglob("*.yaml"))
    assert not (tmp_path / "albedo" / "connections_analyzed.jsonl").exists()

    registry = Registry(tmp_path / "albedo" / "registry.jsonl")
    assert registry.get("synthetic_001")["connected"] is False
    assert registry.get("synthetic_002")["connected"] is False


def test_retrieval_candidate_validates_against_dedicated_schema(tmp_path: Path) -> None:
    _workspace(tmp_path)
    candidate = connect(config=_config(tmp_path), llm=None, all_scope=True)[0]

    schema = parse_schema(REPO_ROOT / "RETRIEVAL_SCHEMA.yaml")
    ok, errors, _, changed = validate_schema(candidate, schema, path="/", fix=False)

    assert ok, errors
    assert changed is False


def test_no_llm_cli_labels_retrieval_candidates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _workspace(tmp_path)
    monkeypatch.setenv("AZOTH_PROJECT_ROOT", str(tmp_path))
    runner = CliRunner()

    result = runner.invoke(
        cli_module.main,
        ["connect", "--all", "--no-llm", "--no-auto-checkpoint"],
    )

    assert result.exit_code == 0, result.output
    assert "Generated 1 retrieval candidate(s)." in result.output
    assert "Generated 1 connection(s)." not in result.output


def test_no_llm_cli_json_contains_no_substantive_claim_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _workspace(tmp_path)
    monkeypatch.setenv("AZOTH_PROJECT_ROOT", str(tmp_path))
    runner = CliRunner()

    result = runner.invoke(
        cli_module.main,
        ["connect", "--all", "--no-llm", "--json", "--no-auto-checkpoint"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload[0]["artifact_type"] == "retrieval_candidate"
    assert "description" not in payload[0]
    assert "evidence_a" not in payload[0]
    assert "evidence_b" not in payload[0]
