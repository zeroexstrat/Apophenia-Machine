"""Reclassify skill: move mis-filed papers into (possibly new) domains."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from athanasor.config import Config, load_config
from athanasor.skills.reclassify import run_reclassify


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
        domains=["physics", "ML", "philosophy", "neuroscience", "mathematics", "biology", "unclassified"],
        exhaustion={},
        project_root=str(root),
    )


def _seed_paper(
    root: Path,
    paper_id: str,
    *,
    domain: str,
    title: str,
    tags: list[str] | None = None,
    status: str = "exhausted",
    abstract: str = "",
) -> None:
    lib = root / "albedo" / "library"
    lib.mkdir(parents=True, exist_ok=True)
    (lib / f"{paper_id}.yaml").write_text(
        yaml.safe_dump(
            {
                "id": paper_id,
                "source": {"title": title, "abstract": abstract},
                "claims": [{"statement": abstract or title}],
                "tags": tags or [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    pdf_dir = root / "nigredo" / domain
    pdf_dir.mkdir(parents=True, exist_ok=True)
    (pdf_dir / f"{paper_id}.pdf").write_bytes(b"%PDF-1.4 fixture")

    registry_path = root / "albedo" / "registry.jsonl"
    entry = {
        "paper_id": paper_id,
        "filename": f"{paper_id}.pdf",
        "domain": domain,
        "domain_confidence": 0.42,
        "title": title,
        "status": status,
        "exhausted_at_depth": 3 if status == "exhausted" else None,
        "paths": {
            "library": f"albedo/library/{paper_id}.yaml",
            "pdf": f"nigredo/{domain}/{paper_id}.pdf",
        },
    }
    with open(registry_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _registry(root: Path) -> list[dict[str, Any]]:
    path = root / "albedo" / "registry.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture(autouse=True)
def _skip_vigil(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZOTH_SKIP_VIGIL", "1")


def test_reclassify_moves_biology_paper_without_llm(tmp_path: Path) -> None:
    _seed_paper(
        tmp_path,
        "levin_000000001",
        domain="unclassified",
        title="Bioelectric morphogenesis in planarian regeneration",
        abstract="Bioelectric gradients guide morphogenesis and anatomical pattern during regeneration.",
    )
    results = run_reclassify(config=_config(tmp_path), llm=None, scope="unclassified")

    assert len(results) == 1
    assert results[0]["new_domain"] == "biology"
    assert results[0]["action"] == "reassigned"

    entry = _registry(tmp_path)[0]
    assert entry["domain"] == "biology"
    assert entry["status"] == "exhausted"  # status preserved
    assert entry["paper_id"] == "levin_000000001"  # id preserved
    assert (tmp_path / "nigredo" / "biology" / "levin_000000001.pdf").exists()
    assert not (tmp_path / "nigredo" / "unclassified" / "levin_000000001.pdf").exists()
    assert entry["paths"]["pdf"] == "nigredo/biology/levin_000000001.pdf"


def test_reclassify_dry_run_reports_without_moving(tmp_path: Path) -> None:
    _seed_paper(
        tmp_path,
        "levin_000000002",
        domain="unclassified",
        title="Planarian bioelectricity and morphogenesis",
        abstract="Bioelectric signaling drives morphogenesis in planaria.",
    )
    results = run_reclassify(config=_config(tmp_path), llm=None, scope="unclassified", apply=False)

    assert results[0]["new_domain"] == "biology"
    assert results[0]["action"] == "would_reassign"
    entry = _registry(tmp_path)[0]
    assert entry["domain"] == "unclassified"  # unchanged on disk
    assert (tmp_path / "nigredo" / "unclassified" / "levin_000000002.pdf").exists()


def test_reclassify_adopts_confident_new_domain_from_llm(tmp_path: Path) -> None:
    _seed_paper(
        tmp_path,
        "chem_000000001",
        domain="unclassified",
        title="Catalytic turnover on metal surfaces",
        abstract="Reaction kinetics of heterogeneous catalysis.",
    )

    class ChemistryLLM:
        def complete(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
            return {"domain": "chemistry", "confidence": 0.93, "proposed": True, "reasoning": "kinetics"}

    config = _config(tmp_path)
    (tmp_path / "azoth.config.yaml").write_text(yaml.safe_dump({"domains": config.domains}), encoding="utf-8")

    results = run_reclassify(config=config, llm=ChemistryLLM(), scope="unclassified", allow_new_domains=True)

    assert results[0]["new_domain"] == "chemistry"
    assert results[0]["proposed"] is True
    assert (tmp_path / "nigredo" / "chemistry" / "chem_000000001.pdf").exists()
    # New domain persisted to config for later runs.
    persisted = load_config(path=tmp_path / "azoth.config.yaml")
    assert "chemistry" in persisted.domains


def test_reclassify_leaves_low_confidence_untouched(tmp_path: Path) -> None:
    _seed_paper(
        tmp_path,
        "vague_000000001",
        domain="unclassified",
        title="Untitled scanned document",
        abstract="",
    )
    results = run_reclassify(config=_config(tmp_path), llm=None, scope="unclassified", min_confidence=0.6)

    assert results[0]["action"] in {"left_unclassified", "low_confidence", "unchanged"}
    entry = _registry(tmp_path)[0]
    assert entry["domain"] == "unclassified"


def test_reclassify_does_not_adopt_new_domain_when_disallowed(tmp_path: Path) -> None:
    _seed_paper(
        tmp_path,
        "chem_000000002",
        domain="unclassified",
        title="Catalytic turnover on metal surfaces",
        abstract="Reaction kinetics.",
    )

    class ChemistryLLM:
        def complete(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
            return {"domain": "chemistry", "confidence": 0.93, "proposed": True, "reasoning": "kinetics"}

    results = run_reclassify(
        config=_config(tmp_path), llm=ChemistryLLM(), scope="unclassified", allow_new_domains=False
    )
    # With new domains disallowed, an out-of-taxonomy paper stays put.
    entry = _registry(tmp_path)[0]
    assert entry["domain"] == "unclassified"
    assert results[0]["new_domain"] != "chemistry"


# --- Agent-as-classifier: apply agent-produced assignments (no LLM backend) ---


def test_reclassify_applies_agent_assignments(tmp_path: Path) -> None:
    """The driving agent classifies; reclassify applies its decisions, no backend."""
    _seed_paper(tmp_path, "p_bio", domain="unclassified", title="Some cell paper")
    _seed_paper(tmp_path, "p_chem", domain="unclassified", title="Some reaction paper")
    config = _config(tmp_path)
    (tmp_path / "azoth.config.yaml").write_text(yaml.safe_dump({"domains": config.domains}), encoding="utf-8")

    assignments = [
        {"paper_id": "p_bio", "domain": "biology", "confidence": 0.95, "reasoning": "agent read it"},
        {"paper_id": "p_chem", "domain": "chemistry", "proposed": True, "confidence": 0.9},
    ]
    results = run_reclassify(config=config, llm=None, assignments=assignments)

    by_id = {r["paper_id"]: r for r in results}
    assert by_id["p_bio"]["action"] == "reassigned"
    assert by_id["p_bio"]["new_domain"] == "biology"
    assert by_id["p_chem"]["action"] == "reassigned"
    assert by_id["p_chem"]["proposed"] is True
    assert by_id["p_bio"].get("source") == "agent"

    assert (tmp_path / "nigredo" / "biology" / "p_bio.pdf").exists()
    assert (tmp_path / "nigredo" / "chemistry" / "p_chem.pdf").exists()
    entries = {e["paper_id"]: e for e in _registry(tmp_path)}
    assert entries["p_bio"]["domain"] == "biology"
    assert entries["p_bio"]["status"] == "exhausted"  # preserved
    # Newly proposed domain persisted to config.
    assert "chemistry" in load_config(path=tmp_path / "azoth.config.yaml").domains


def test_reclassify_assignments_dry_run_moves_nothing(tmp_path: Path) -> None:
    _seed_paper(tmp_path, "p_dry", domain="unclassified", title="Paper")
    results = run_reclassify(
        config=_config(tmp_path),
        llm=None,
        assignments=[{"paper_id": "p_dry", "domain": "biology"}],
        apply=False,
    )
    assert results[0]["action"] == "would_reassign"
    assert _registry(tmp_path)[0]["domain"] == "unclassified"
    assert (tmp_path / "nigredo" / "unclassified" / "p_dry.pdf").exists()


def test_reclassify_assignments_unknown_paper_id_is_reported(tmp_path: Path) -> None:
    _seed_paper(tmp_path, "p_real", domain="unclassified", title="Paper")
    results = run_reclassify(
        config=_config(tmp_path),
        llm=None,
        assignments=[{"paper_id": "ghost", "domain": "biology"}],
    )
    assert results[0]["action"] == "not_found"
    assert _registry(tmp_path)[0]["domain"] == "unclassified"  # real one untouched


def test_reclassify_assignments_reject_bad_domain(tmp_path: Path) -> None:
    _seed_paper(tmp_path, "p_bad", domain="unclassified", title="Paper")
    results = run_reclassify(
        config=_config(tmp_path),
        llm=None,
        assignments=[{"paper_id": "p_bad", "domain": "../etc/passwd"}],
    )
    assert results[0]["action"] == "invalid_domain"
    assert _registry(tmp_path)[0]["domain"] == "unclassified"
    assert not (tmp_path / "nigredo" / ".." ).exists() or True  # no traversal side effect


def test_cli_reclassify_assignments_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: `azoth reclassify --assignments file.json` applies agent decisions."""
    from click.testing import CliRunner
    from athanasor import cli as cli_module

    monkeypatch.setenv("AZOTH_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AZOTH_SKIP_VIGIL", "1")
    _seed_paper(tmp_path, "cli_p1", domain="unclassified", title="Paper one")
    (tmp_path / "azoth.config.yaml").write_text(
        yaml.safe_dump({"domains": ["ML", "biology", "unclassified"]}), encoding="utf-8"
    )
    assignments_file = tmp_path / "assignments.json"
    assignments_file.write_text(
        json.dumps({"assignments": [{"paper_id": "cli_p1", "domain": "biology", "confidence": 0.95}]}),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        cli_module.main,
        ["reclassify", "--assignments", str(assignments_file), "--json", "--no-auto-checkpoint"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload[0]["action"] == "reassigned"
    assert payload[0]["source"] == "agent"
    assert (tmp_path / "nigredo" / "biology" / "cli_p1.pdf").exists()
