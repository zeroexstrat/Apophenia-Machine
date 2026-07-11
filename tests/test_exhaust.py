"""Exhaust skill behavior: bucket handling, guardrails, stable keys."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from athanasor.config import Config
from athanasor.skills.exhaust import _item_key, _process_one


EXHAUST_SCHEMA = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "EXHAUST_SCHEMA.yaml").read_text(encoding="utf-8")
)


class FakeStore:
    size = 0

    def add(self, key: str, text: str) -> None:
        return None

    def search(self, text: str, top_k: int = 25) -> list[tuple[str, float]]:
        return []


class FakeRegistry:
    def __init__(self) -> None:
        self.updates: list[tuple[str, dict[str, Any]]] = []

    def update(self, paper_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        self.updates.append((paper_id, fields))
        return fields


def _config(root: Path, **exhaustion_overrides: Any) -> Config:
    exhaustion = {
        "depth_multipliers": {1: 2, 2: 4, 3: 6, 4: 8, 5: 12},
        "batch_size": 3,
        "llm_max_tokens": 384,
        "redundancy_stop_threshold": 3,
        "speculative_stop_count": 5,
    }
    exhaustion.update(exhaustion_overrides)
    return Config(
        llm={"max_tokens": 4096},
        embeddings={"redundancy_threshold": 0.99},
        paths={
            "project_root": str(root),
            "nigredo": "nigredo",
            "albedo": "albedo",
            "citrinitas": "citrinitas",
            "rubedo": "rubedo",
            "athanasor": "athanasor",
        },
        domains=["ML"],
        exhaustion=exhaustion,
        project_root=str(root),
    )


def _library_record(paper_id: str, claims: list[Any] | None = None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": paper_id,
        "source": {"title": "Fixture Paper"},
        "claims": claims
        if claims is not None
        else [{"statement": "Fixture claim.", "confidence": "demonstrated", "evidence": "table"}],
        "methods": [{"name": "fixture method", "description": "desc", "domain": "ML"}],
        "techniques": [],
        "equations": [],
        "tags": ["fixture"],
    }


def _setup_paper(root: Path, paper_id: str, claims: list[Any] | None = None) -> dict[str, Any]:
    library = root / "albedo" / "library"
    exhaust = root / "albedo" / "exhaust"
    library.mkdir(parents=True, exist_ok=True)
    exhaust.mkdir(parents=True, exist_ok=True)
    with open(library / f"{paper_id}.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(_library_record(paper_id, claims), f, sort_keys=False)
    return {
        "paper_id": paper_id,
        "domain": "ML",
        "status": "ingested_only",
        "exhausted_at_depth": None,
        "source": {"page_count": 1},
        "paths": {"library": f"albedo/library/{paper_id}.yaml"},
    }


def _run_process_one(root: Path, entry: dict[str, Any], llm: Any, config: Config, depth: int = 1):
    return _process_one(
        paper_id=entry["paper_id"],
        registry_entry=entry,
        library_root=root / "albedo" / "library",
        exhaust_root=root / "albedo" / "exhaust",
        depth=depth,
        llm=llm,
        schema=EXHAUST_SCHEMA,
        store=FakeStore(),
        config=_config(root) if config is None else config,
        registry=FakeRegistry(),
    )


def test_batch_keeps_later_buckets_when_first_bucket_empty(tmp_path: Path) -> None:
    """An LLM batch with empty derivations must not discard the other buckets."""

    class OneShotLLM:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
            self.calls += 1
            if self.calls > 1:
                return {key: [] for key in (
                    "derivations", "exercises", "missing_angles", "open_questions",
                    "unstated_assumptions", "experiments", "necessary_connections",
                )}
            return {
                "derivations": [],
                "exercises": [{"problem": "Verify the fixture invariant.", "solution": "Check it."}],
                "missing_angles": [{"angle": "An unexplored fixture angle.", "where_it_lands": "here"}],
                "open_questions": [],
                "unstated_assumptions": [],
                "experiments": [],
                "necessary_connections": [],
            }

    entry = _setup_paper(tmp_path, "bucketdrop_000000001")
    payload = _run_process_one(tmp_path, entry, OneShotLLM(), _config(tmp_path))
    assert payload is not None
    assert len(payload.get("exercises", [])) == 1
    assert len(payload.get("missing_angles", [])) == 1


def test_item_key_is_stable_across_processes() -> None:
    """Embedding item keys must not depend on Python's randomized hash()."""
    key = _item_key("derivations", {"statement": "A stable statement."})
    # sha1("A stable statement.")[:12] — a process-independent value.
    import hashlib

    expected = hashlib.sha1("A stable statement.".encode("utf-8")).hexdigest()[:12]
    assert key == expected


def test_speculative_ceiling_respects_configured_count(tmp_path: Path) -> None:
    """A speculative_stop_count above 5 must still terminate on the ceiling."""

    class SpeculativeLLM:
        def complete(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
            return {
                "derivations": [
                    {"statement": f"Speculative item {id(object())}.", "confidence": "speculative"}
                ],
                "exercises": [],
                "missing_angles": [],
                "open_questions": [],
                "unstated_assumptions": [],
                "experiments": [],
                "necessary_connections": [],
            }

    entry = _setup_paper(tmp_path, "speculative_000000001")
    entry["source"] = {"page_count": 4}  # hard cap (24) far above the ceiling window
    config = _config(tmp_path, speculative_stop_count=7)
    payload = _process_one(
        paper_id=entry["paper_id"],
        registry_entry=entry,
        library_root=tmp_path / "albedo" / "library",
        exhaust_root=tmp_path / "albedo" / "exhaust",
        depth=3,
        llm=SpeculativeLLM(),
        schema=EXHAUST_SCHEMA,
        store=FakeStore(),
        config=config,
        registry=FakeRegistry(),
    )
    assert payload is not None
    termination = payload["exhaustion"]["termination"]
    assert termination["criterion"] == "speculative_ceiling"


def test_process_one_tolerates_non_dict_claims(tmp_path: Path) -> None:
    """Hand-edited library YAML with string claims must not crash exhaustion."""
    entry = _setup_paper(
        tmp_path,
        "handedited_000000001",
        claims=["just a bare string claim", {"statement": "A real claim."}],
    )
    payload = _run_process_one(tmp_path, entry, None, _config(tmp_path))
    assert payload is not None
