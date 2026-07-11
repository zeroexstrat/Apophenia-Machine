"""Registry robustness tests: atomicity, malformed input, transitions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from athanasor.registry import Registry


def _entry(paper_id: str, status: str = "ingested_only") -> dict:
    return {
        "paper_id": paper_id,
        "filename": f"{paper_id}.pdf",
        "domain": "ML",
        "domain_confidence": 0.9,
        "title": f"Paper {paper_id}",
        "authors": ["A. Author"],
        "year": 2026,
        "ingested": "2026-01-01T00:00:00Z",
        "status": status,
        "paths": {},
    }


def test_add_and_get_roundtrip(tmp_path: Path) -> None:
    registry = Registry(tmp_path / "registry.jsonl")
    registry.add(_entry("p1"))
    fetched = registry.get("p1")
    assert fetched is not None
    assert fetched["status"] == "ingested_only"


def test_add_rejects_duplicate(tmp_path: Path) -> None:
    registry = Registry(tmp_path / "registry.jsonl")
    registry.add(_entry("p1"))
    with pytest.raises(ValueError):
        registry.add(_entry("p1"))


def test_status_regression_rejected(tmp_path: Path) -> None:
    registry = Registry(tmp_path / "registry.jsonl")
    registry.add(_entry("p1"))
    registry.update("p1", {"status": "exhausted"})
    with pytest.raises(ValueError):
        registry.update("p1", {"status": "ingested_only"})


def test_malformed_lines_are_skipped_on_read(tmp_path: Path) -> None:
    path = tmp_path / "registry.jsonl"
    path.write_text(
        json.dumps(_entry("p1")) + "\n" + "{this is not json}\n" + json.dumps(_entry("p2")) + "\n",
        encoding="utf-8",
    )
    registry = Registry(path)
    ids = [entry["paper_id"] for entry in registry.list()]
    assert ids == ["p1", "p2"]


def test_write_failure_preserves_existing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A crash mid-rewrite must not destroy the existing registry file."""
    path = tmp_path / "registry.jsonl"
    registry = Registry(path)
    registry.add(_entry("p1"))
    registry.add(_entry("p2"))
    before = path.read_text(encoding="utf-8")
    assert before.count("\n") == 2

    real_dumps = json.dumps
    calls = {"n": 0}

    def exploding_dumps(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("simulated crash mid-serialization")
        return real_dumps(*args, **kwargs)

    monkeypatch.setattr("athanasor.registry.json.dumps", exploding_dumps)
    with pytest.raises(RuntimeError):
        registry.update("p1", {"status": "exhausted"})
    monkeypatch.undo()

    # The registry on disk must still hold both entries, unmodified or fully updated —
    # never truncated or partially written.
    survivors = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [e["paper_id"] for e in survivors] == ["p1", "p2"]


def test_update_missing_paper_raises_keyerror(tmp_path: Path) -> None:
    registry = Registry(tmp_path / "registry.jsonl")
    with pytest.raises(KeyError):
        registry.update("ghost", {"status": "exhausted"})
