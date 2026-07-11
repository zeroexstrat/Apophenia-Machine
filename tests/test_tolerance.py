"""One corrupted artifact must never brick a pipeline command."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from athanasor.config import Config
from athanasor.skills.detect import detect
from athanasor.embeddings import EmbeddingStore


REPO_ROOT = Path(__file__).resolve().parents[1]


def _config(root: Path) -> Config:
    return Config(
        llm={},
        embeddings={"store_path": "athanasor/embeddings.store"},
        paths={"project_root": str(root)},
        domains=["ML"],
        exhaustion={},
        project_root=str(root),
    )


def test_detect_skips_corrupted_connection_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZOTH_SKIP_VIGIL", "1")
    connections = tmp_path / "citrinitas" / "within_domain" / "ML"
    connections.mkdir(parents=True)
    (tmp_path / "rubedo" / "hypotheses").mkdir(parents=True)
    (tmp_path / "albedo" / "library").mkdir(parents=True)

    (connections / "corrupt.yaml").write_text("{{unbalanced: [", encoding="utf-8")
    with open(connections / "good.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(
            {"paper_a_id": "a", "paper_b_id": "b", "pair_scope": "within_domain"}, f
        )

    outputs = detect(config=_config(tmp_path), llm=None, domain="ML")
    assert outputs == []  # no >=3 cluster, but crucially: no crash


def _load_vigil_module():
    spec = importlib.util.spec_from_file_location(
        "vigil_verify_under_test", REPO_ROOT / "athanasor" / "vigil" / "verify.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_vigil_registry_gate_tolerates_malformed_lines(tmp_path: Path) -> None:
    vigil = _load_vigil_module()
    registry_path = tmp_path / "registry.jsonl"
    registry_path.write_text(
        json.dumps({"paper_id": "ok", "status": "ingested_only", "triage": None}) + "\n"
        + "{broken json\n"
        + json.dumps({"paper_id": "confirmed_no_review", "title": "t", "triage": {"outcome": "confirmed"}})
        + "\n",
        encoding="utf-8",
    )
    vigil.REGISTRY_PATH = registry_path

    passed, detail = vigil.check_registry()

    assert passed is False
    assert "unparseable" in detail.lower()
    assert "confirmed without review date" in detail


def test_embedding_store_resets_on_meta_vector_mismatch(tmp_path: Path) -> None:
    store_path = tmp_path / "embeddings.store"
    store = EmbeddingStore(store_path)
    store.add_batch(["a", "b"], ["text a", "text b"])
    store.save()

    # Corrupt: drop one id from the metadata while keeping both vectors.
    meta_path = store_path.with_suffix(".json")
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    payload["ids"] = payload["ids"][:1]
    meta_path.write_text(json.dumps(payload), encoding="utf-8")

    reloaded = EmbeddingStore(store_path)
    # A mismatched store must reset to empty rather than serve misaligned results.
    assert reloaded.size == 0
    assert reloaded.search("text a", top_k=3) == []
