"""Audit integrity errors and release-version consistency."""

from __future__ import annotations

import importlib.util
import json
import re
import tomllib
from pathlib import Path

import yaml

from athanasor.skills.connect import load_agent_connections
from athanasor.skills.detect import load_agent_hypotheses, stable_cluster_id

REPO_ROOT = Path(__file__).resolve().parents[1]


def _audit():
    spec = importlib.util.spec_from_file_location(
        "audit_under_test", REPO_ROOT / "scripts" / "hardening_audit.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exhausted_entry_with_missing_artifact_is_an_error(tmp_path: Path) -> None:
    """status=exhausted + declared exhaust file absent = broken durable state."""
    audit = _audit()
    reg = tmp_path / "albedo" / "registry.jsonl"
    reg.parent.mkdir(parents=True)
    reg.write_text(json.dumps({
        "paper_id": "gone", "status": "exhausted",
        "paths": {"library": "albedo/library/gone.yaml", "exhaust": "albedo/exhaust/gone_exhaust.yaml"},
    }) + "\n", encoding="utf-8")
    (tmp_path / "albedo" / "library").mkdir()
    (tmp_path / "albedo" / "library" / "gone.yaml").write_text("id: gone\n", encoding="utf-8")

    errors, warnings = audit._validate_registry_state(tmp_path)
    assert any("exhaust" in e and "gone" in e for e in errors), (errors, warnings)


def test_ingested_only_missing_declared_exhaust_stays_warning(tmp_path: Path) -> None:
    audit = _audit()
    reg = tmp_path / "albedo" / "registry.jsonl"
    reg.parent.mkdir(parents=True)
    reg.write_text(json.dumps({
        "paper_id": "early", "status": "ingested_only",
        "paths": {"exhaust": "albedo/exhaust/early_exhaust.yaml"},
    }) + "\n", encoding="utf-8")
    errors, warnings = audit._validate_registry_state(tmp_path)
    assert not any("early" in e for e in errors)
    assert any("early" in w for w in warnings)


def _pyproject_version() -> str:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version\s*=\s*"([^"]+)"', text, re.M).group(1)


def test_release_pins_match_pyproject_version() -> None:
    """One version source: every pinned install ref must match pyproject."""
    version = _pyproject_version()
    expected = f"@v{version}"
    offenders: list[str] = []
    for path in [REPO_ROOT / "skills" / "azoth" / "scripts" / "preflight.py",
                 *(REPO_ROOT / "skills" / "azoth" / "reference").glob("*.md")]:
        for match in re.findall(r"@v\d+\.\d+\.\d+", path.read_text(encoding="utf-8")):
            if match != expected:
                offenders.append(f"{path.name}: {match} != {expected}")
    assert not offenders, offenders


def test_apache_license_metadata_is_consistent() -> None:
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    classifiers = set(project["classifiers"])

    assert project["license"] == "Apache-2.0"
    assert "License :: OSI Approved :: Apache Software License" not in classifiers
    assert {
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    }.issubset(classifiers)
    license_text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert license_text.startswith("Apache License\nVersion 2.0, January 2004")
    assert "GNU AFFERO" not in license_text
    assert "Apache License 2.0" in (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def test_synthetic_agent_input_examples_parse_and_use_stable_cluster_id() -> None:
    example_root = REPO_ROOT / "examples" / "synthetic-agent-input"
    connections = load_agent_connections(example_root / "connections.json")
    hypotheses = load_agent_hypotheses(example_root / "hypotheses.json")

    assert len(connections) == 2
    assert len(hypotheses) == 1
    hypothesis = hypotheses[0]
    assert hypothesis["paper_ids"] == ["synthetic_001", "synthetic_002", "synthetic_003"]
    assert hypothesis["cluster_id"] == stable_cluster_id(hypothesis["paper_ids"])
    assert all(item["status"] == "pending_review" for item in connections + hypotheses)
