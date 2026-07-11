"""Agent-as-exhauster: the driving agent supplies exhaustion records, no backend."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from athanasor.config import Config
from athanasor.registry import Registry
from athanasor.skills.exhaust import apply_agent_exhaust


def _config(root: Path) -> Config:
    return Config(
        llm={},
        embeddings={"store_path": "athanasor/embeddings.store"},
        paths={
            "project_root": str(root),
            "nigredo": "nigredo",
            "albedo": "albedo",
            "citrinitas": "citrinitas",
            "rubedo": "rubedo",
            "athanasor": "athanasor",
        },
        domains=["ML", "biology", "unclassified"],
        exhaustion={},
        project_root=str(root),
    )


def _seed_ingested(root: Path, paper_id: str, *, domain: str = "ML", title: str = "A Paper") -> None:
    lib = root / "albedo" / "library"
    lib.mkdir(parents=True, exist_ok=True)
    (lib / f"{paper_id}.yaml").write_text(
        yaml.safe_dump({"id": paper_id, "source": {"title": title}, "claims": [], "tags": ["fixture"]}),
        encoding="utf-8",
    )
    reg = root / "albedo" / "registry.jsonl"
    reg.parent.mkdir(parents=True, exist_ok=True)
    with open(reg, "a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "paper_id": paper_id,
                    "filename": f"{paper_id}.pdf",
                    "domain": domain,
                    "status": "ingested_only",
                    "exhausted_at_depth": None,
                    "paths": {"library": f"albedo/library/{paper_id}.yaml"},
                }
            )
            + "\n"
        )


def _registry(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "albedo" / "registry.jsonl"
    return {
        json.loads(line)["paper_id"]: json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


@pytest.fixture(autouse=True)
def _skip_vigil(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZOTH_SKIP_VIGIL", "1")


def test_apply_agent_exhaust_writes_and_validates(tmp_path: Path) -> None:
    _seed_ingested(tmp_path, "agx_001", domain="ML", title="Sparse Attention")
    records = [
        {
            "paper_id": "agx_001",
            "depth": 4,
            "derivations": [
                {"statement": "Block-sparse routing keeps O(n log n) attention cost.", "confidence": "derived"}
            ],
            "missing_angles": [{"angle": "No analysis of routing collapse under distribution shift."}],
            "experiments": [{"hypothesis": "Sparsity harms long-range recall past 32k tokens."}],
        }
    ]
    results = apply_agent_exhaust(records, config=_config(tmp_path))

    assert results[0]["action"] == "exhausted"
    assert results[0]["depth"] == 4
    out = tmp_path / "albedo" / "exhaust" / "agx_001_exhaust.yaml"
    assert out.exists()
    payload = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["exhaustion"]["paper_id"] == "agx_001"
    assert payload["exhaustion"]["agent"] == "azoth-agent-exhaust"
    assert payload["exhaustion"]["termination"]["criterion"] == "completed"
    assert len(payload["derivations"]) == 1
    assert len(payload["missing_angles"]) == 1

    entry = _registry(tmp_path)["agx_001"]
    assert entry["status"] == "exhausted"
    assert entry["exhausted_at_depth"] == 4


def test_apply_agent_exhaust_normalizes_model_field_aliases(tmp_path: Path) -> None:
    """A model that uses 'content'/'answer' aliases instead of canonical fields still files."""
    _seed_ingested(tmp_path, "agx_002")
    records = [
        {
            "paper_id": "agx_002",
            "derivations": [{"content": "Aliased derivation body.", "confidence": "likely"}],
            "exercises": [{"item": "Aliased exercise prompt.", "answer": "Aliased solution."}],
        }
    ]
    results = apply_agent_exhaust(records, config=_config(tmp_path))
    assert results[0]["action"] == "exhausted"
    payload = yaml.safe_load(
        (tmp_path / "albedo" / "exhaust" / "agx_002_exhaust.yaml").read_text(encoding="utf-8")
    )
    # Canonical fields populated from aliases.
    assert payload["derivations"][0]["statement"] == "Aliased derivation body."
    assert payload["exercises"][0]["problem"] == "Aliased exercise prompt."


def test_apply_agent_exhaust_unknown_paper_reported(tmp_path: Path) -> None:
    _seed_ingested(tmp_path, "agx_real")
    results = apply_agent_exhaust(
        [{"paper_id": "ghost", "derivations": [{"statement": "x"}]}], config=_config(tmp_path)
    )
    assert results[0]["action"] == "not_found"
    assert _registry(tmp_path)["agx_real"]["status"] == "ingested_only"


def test_apply_agent_exhaust_empty_record_reported(tmp_path: Path) -> None:
    _seed_ingested(tmp_path, "agx_empty")
    results = apply_agent_exhaust(
        [{"paper_id": "agx_empty", "derivations": []}], config=_config(tmp_path)
    )
    assert results[0]["action"] == "empty"
    assert not (tmp_path / "albedo" / "exhaust" / "agx_empty_exhaust.yaml").exists()


def test_cli_exhaust_from_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from click.testing import CliRunner
    from athanasor import cli as cli_module

    monkeypatch.setenv("AZOTH_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AZOTH_SKIP_VIGIL", "1")
    _seed_ingested(tmp_path, "cli_agx", domain="ML", title="CLI paper")
    records_file = tmp_path / "exhaust.json"
    records_file.write_text(
        json.dumps(
            {"exhaustion": [{"paper_id": "cli_agx", "depth": 3, "derivations": [{"statement": "d"}]}]}
        ),
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        cli_module.main,
        ["exhaust", "--from-file", str(records_file), "--json", "--no-auto-checkpoint"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload[0]["action"] == "exhausted"
    assert (tmp_path / "albedo" / "exhaust" / "cli_agx_exhaust.yaml").exists()
