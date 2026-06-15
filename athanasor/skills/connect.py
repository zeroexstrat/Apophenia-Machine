"""Connect skill: Citrinitas pair discovery and connection synthesis."""

from __future__ import annotations

import argparse
import json
import subprocess
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from ..config import Config, load_config
from ..embeddings import EmbeddingStore
from ..llm import LLMClient
from ..registry import Registry
from ..schemas import validate as validate_schema
from ..skills.common import ensure_dir, now_iso, write_yaml


CONNECT_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "CONNECT_SCHEMA.yaml"


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Find structural links between papers.")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--within", dest="within", help="Domain for within-domain pass.")
    scope.add_argument("--cross", nargs=2, metavar=("D1", "D2"), help="Domain pair for cross-domain pass.")
    scope.add_argument("--paper", dest="paper_id", help="Single paper id")
    scope.add_argument("--all", action="store_true", help="Run all scopes.")
    return parser


def _run_vigil(root: Path, phase: str) -> tuple[int, str]:
    result = subprocess.run(
        ["python3", str(root / "athanasor" / "vigil" / "verify.py"), phase],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return result.returncode, result.stderr or result.stdout
    return result.returncode, result.stdout


def connect(
    *,
    config: Config | None = None,
    llm: LLMClient | None = None,
    within: str | None = None,
    cross: tuple[str, str] | None = None,
    paper_id: str | None = None,
    all_scope: bool = False,
) -> list[dict[str, Any]]:
    cfg = config or load_config()
    root = Path(cfg.project_root).expanduser().resolve()
    _run_vigil(root, "start")

    registry = Registry(root / "albedo" / "registry.jsonl")
    store = EmbeddingStore(root / cfg.embeddings["store_path"], model_name=cfg.embeddings.get("model", "all-MiniLM-L6-v2"))
    schema = _load_schema()

    if paper_id:
        candidates = [registry.get(paper_id)] if registry.get(paper_id) else []
        candidates = [c for c in candidates if isinstance(c, dict)]
        pairs = _pairs_for_paper(candidates, registry)
    elif all_scope:
        pairs = _all_pairs(registry, include_cross=True)
    elif within:
        pairs = _within_domain_pairs(registry, within)
    elif cross:
        pairs = _cross_domain_pairs(registry, cross[0], cross[1])
    else:
        return []

    analyzed = _load_analyzed(root / "albedo" / "connections_analyzed.jsonl")
    output: list[dict[str, Any]] = []

    for a_id, b_id, pair_scope, pair_domain in pairs:
        a_id, b_id = sorted([str(a_id), str(b_id)])
        key = _pair_key(a_id, b_id)
        if key in analyzed:
            continue

        a_entry = registry.get(a_id)
        b_entry = registry.get(b_id)
        if not isinstance(a_entry, dict) or not isinstance(b_entry, dict):
            continue

        sim = _pair_similarity(a_id, b_id, store)
        if sim < cfg.embeddings.get("similarity_threshold", 0.82):
            analyzed.add(key)
            continue

        record_a = _load_library_record(root, a_entry.get("paths", {}).get("library"), a_id)
        record_b = _load_library_record(root, b_entry.get("paths", {}).get("library"), b_id)
        if not record_a or not record_b:
            analyzed.add(key)
            continue

        candidate = _analyze_pair(a_id, b_id, record_a, record_b, pair_scope, llm, schema)
        if not candidate:
            analyzed.add(key)
            continue

        confidence_raw = _coerce_confidence(candidate.get("confidence"), fallback=3)
        confidence = confidence_raw
        # Cross-domain penalty.
        if pair_scope == "cross_domain":
            pair_domain = f"{a_entry.get('domain')}↔{b_entry.get('domain')}"
            confidence = max(1, confidence_raw - 1)

        candidate["confidence_raw"] = confidence_raw
        candidate["confidence"] = max(1, min(5, confidence))
        candidate["pair_scope"] = pair_scope
        candidate["paper_a_id"] = a_id
        candidate["paper_b_id"] = b_id
        candidate["pair_domains"] = {
            "paper_a_domain": a_entry.get("domain"),
            "paper_b_domain": b_entry.get("domain"),
        }
        candidate.setdefault("status", "pending_review")
        candidate["status"] = candidate.get("status")
        if candidate["status"] not in {"pending_review", "accepted", "rejected", "investigate"}:
            candidate["status"] = "pending_review"
        candidate["score"] = _score_connection(candidate, novelty_weight=True)
        candidate["evidence_a"] = candidate.get("evidence_a") or "Unspecified"
        candidate["evidence_b"] = candidate.get("evidence_b") or "Unspecified"
        candidate["agent_notes"] = candidate.get("agent_notes", "") or (
            "Generated during connect pass."
        )
        candidate.setdefault("paper_a_id", a_id)
        candidate.setdefault("paper_b_id", b_id)
        candidate.setdefault("pair_scope", pair_scope)
        candidate.setdefault("pair_domains", {
            "paper_a_domain": a_entry.get("domain"),
            "paper_b_domain": b_entry.get("domain"),
        })
        candidate.setdefault("status", "pending_review")

        ok, errors, fixed, _ = validate_schema(candidate, schema, path=str(a_id), fix=True)
        if not ok:
            candidate["_schema_errors"] = errors
            continue
        candidate = fixed

        if candidate.get("novelty") == "speculative" and candidate["confidence"] < 4:
            analyzed.add(key)
            continue

        out_path = _write_connection(
            root / "citrinitas",
            a_id,
            b_id,
            pair_scope,
            pair_domain if pair_scope == "within_domain" else None,
            candidate,
        )

        record = _normalize_connection(candidate, out_path)
        if not record.get("status"):
            continue

        output.append(record)

        analyzed.add(key)
        _mark_connected(registry, a_entry, b_entry)
        _append_analyzed(root / "albedo" / "connections_analyzed.jsonl", a_id, b_id)

    _run_vigil(root, "verify")
    return output

def _load_schema() -> dict[str, Any]:
    with open(CONNECT_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _within_domain_pairs(registry: Registry, domain: str) -> list[tuple[str, str, str, str]]:
    entries = [entry for entry in registry.list_by_domain(domain) if entry.get("status") == "exhausted"]
    return [(a.get("paper_id"), b.get("paper_id"), "within_domain", domain)
            for a, b in combinations(entries, 2)
            if a.get("paper_id") and b.get("paper_id") and _has_shared_tags(a, b)]


def _cross_domain_pairs(registry: Registry, d1: str, d2: str) -> list[tuple[str, str, str, str]]:
    e1 = [entry for entry in registry.list_by_domain(d1) if entry.get("status") == "exhausted"]
    e2 = [entry for entry in registry.list_by_domain(d2) if entry.get("status") == "exhausted"]
    pairs: list[tuple[str, str, str, str]] = []
    for a in e1:
        for b in e2:
            if a.get("paper_id") and b.get("paper_id") and _has_shared_tags(a, b):
                pairs.append((a.get("paper_id"), b.get("paper_id"), "cross_domain", f"{d1}_{d2}"))
    return pairs


def _all_pairs(registry: Registry, include_cross: bool = True) -> list[tuple[str, str, str, str]]:
    exhausted = [entry for entry in registry.list() if entry.get("status") == "exhausted"]
    pairs: list[tuple[str, str, str, str]] = []
    for a, b in combinations(exhausted, 2):
        a_id = a.get("paper_id")
        b_id = b.get("paper_id")
        if not a_id or not b_id:
            continue
        if not _has_shared_tags(a, b):
            continue
        if a.get("domain") == b.get("domain"):
            pairs.append((a_id, b_id, "within_domain", str(a.get("domain"))))
        elif include_cross:
            pairs.append((a_id, b_id, "cross_domain", f"{a.get('domain')}_{b.get('domain')}"))
    return pairs


def _pairs_for_paper(entries: list[dict[str, Any]], registry: Registry) -> list[tuple[str, str, str, str]]:
    if not entries:
        return []
    target = entries[0]
    target_id = target.get("paper_id")
    same_domain = [
        entry
        for entry in registry.list_by_domain(str(target.get("domain")))
        if entry.get("status") == "exhausted" and entry.get("paper_id") != target_id
    ]
    cross = [entry for entry in registry.list() if entry.get("status") == "exhausted" and entry.get("paper_id") != target_id]
    pairs: list[tuple[str, str, str, str]] = []
    for entry in same_domain:
        if _has_shared_tags(target, entry):
            pairs.append((target_id, entry.get("paper_id"), "within_domain", str(target.get("domain"))))
    for entry in cross:
        if entry.get("domain") != target.get("domain") and _has_shared_tags(target, entry):
            pairs.append((target_id, entry.get("paper_id"), "cross_domain", f"{target.get('domain')}_{entry.get('domain')}"))
    return pairs


def _pair_key(a_id: str, b_id: str) -> str:
    a, b = sorted([a_id, b_id])
    return f"{a}::{b}"


def _load_analyzed(path: Path) -> set[str]:
    analyzed: set[str] = set()
    if not path.exists():
        return analyzed
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            try:
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    key = payload.get("pair")
                    if isinstance(key, str):
                        analyzed.add(key)
            except json.JSONDecodeError:
                continue
    return analyzed


def _append_analyzed(path: Path, a_id: str, b_id: str) -> None:
    ensure_dir(path.parent)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"pair": _pair_key(a_id, b_id), "analyzed_at": now_iso()}) + "\n")


def _has_shared_tags(a: dict[str, Any], b: dict[str, Any]) -> bool:
    a_tags = set(str(x).lower() for x in a.get("tags", []) if isinstance(x, str))
    b_tags = set(str(x).lower() for x in b.get("tags", []) if isinstance(x, str))
    if a_tags and b_tags and a_tags.intersection(b_tags):
        return True
    a_id = a.get("paper_id")
    b_id = b.get("paper_id")
    if not a_id or not b_id:
        return False
    return a_id[:2] == b_id[:2]


def _paper_embedding(store: EmbeddingStore, paper_id: str) -> np.ndarray:
    texts: list[str] = []
    for prefix in (f"{paper_id}_claim_", f"{paper_id}_method_", f"{paper_id}_technique_"):
        texts.extend(store.texts_with_prefix(prefix))
    if not texts:
        return np.zeros((store.dimension,), dtype=np.float32)
    vectors = []
    for text in texts[:9]:
        try:
            vectors.append(store.embed_text(text))
        except Exception:
            vectors.append(np.zeros((store.dimension,), dtype=np.float32))
    return np.mean(np.vstack(vectors), axis=0)


def _pair_similarity(a_id: str, b_id: str, store: EmbeddingStore) -> float:
    vec_a = _paper_embedding(store, a_id)
    vec_b = _paper_embedding(store, b_id)
    if vec_a.size == 0 or vec_b.size == 0:
        return 0.0
    denom = np.linalg.norm(vec_a) * np.linalg.norm(vec_b)
    if denom <= 0:
        return 0.0
    return float((vec_a @ vec_b) / denom)


def _load_library_record(root: Path, rel_path: str | None, paper_id: str) -> dict[str, Any] | None:
    if rel_path:
        candidate = root / rel_path
        if candidate.exists():
            with open(candidate, "r", encoding="utf-8") as f:
                payload = yaml.safe_load(f)
            if isinstance(payload, dict):
                return payload
    fallback = root / "albedo" / "library" / f"{paper_id}.yaml"
    if fallback.exists():
        with open(fallback, "r", encoding="utf-8") as f:
            payload = yaml.safe_load(f)
        if isinstance(payload, dict):
            return payload
    return None


def _coerce_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _coerce_confidence(value: Any, fallback: int = 0) -> int:
    """Normalize arbitrary confidence payloads into integer 1..5 scale."""
    if isinstance(value, bool):
        return fallback

    text = str(value).strip().lower()
    if not text:
        return fallback

    label_map = {
        "low": 2,
        "medium": 3,
        "high": 4,
        "very_high": 5,
        "veryhigh": 5,
        "very high": 5,
        "low_to_medium": 2,
        "moderate": 3,
        "very low": 1,
    }
    if text in label_map:
        return label_map[text]

    try:
        parsed = int(float(text))
    except ValueError:
        return fallback

    return max(1, min(5, parsed))


def _analyze_pair(
    a_id: str,
    b_id: str,
    record_a: dict[str, Any],
    record_b: dict[str, Any],
    pair_scope: str,
    llm: LLMClient | None,
    schema: dict[str, Any],
) -> dict[str, Any] | None:
    if llm is None:
        return {
            "pair_scope": pair_scope,
            "paper_a_id": a_id,
            "paper_b_id": b_id,
            "connection_type": "complementary_techniques",
            "description": "LLM unavailable; fallback connection created for overlap review.",
            "evidence_a": "shared top-level tags in registry",
            "evidence_b": "shared top-level tags in registry",
            "confidence": 3,
            "novelty": "non-obvious",
            "significance": "Potentially similar conceptual framing.",
            "status": "pending_review",
        }

    prompt = (
        f"Paper A: {record_a.get('source', {}).get('title', a_id)}\n"
        f"Claims: {[item.get('statement') for item in record_a.get('claims', [])[:5]]}\n"
        f"Methods: {[item.get('name') for item in record_a.get('methods', [])[:5]]}\n"
        f"Techniques: {[item.get('name') for item in record_a.get('techniques', [])[:5]]}\n\n"
        f"Paper B: {record_b.get('source', {}).get('title', b_id)}\n"
        f"Claims: {[item.get('statement') for item in record_b.get('claims', [])[:5]]}\n"
        f"Methods: {[item.get('name') for item in record_b.get('methods', [])[:5]]}\n"
        f"Techniques: {[item.get('name') for item in record_b.get('techniques', [])[:5]]}\n"
    )
    response = llm.complete(
        (
            "Analyze whether these two papers share a substantive structural connection.\n\n"
            + prompt
            + "\nIf no connection exists return {}."
        ),
        structured=True,
        schema=schema,
        temperature=0.25,
        max_tokens=2048,
    )
    if not isinstance(response, dict):
        return None
    if response == {}:
        return None

    response["pair_scope"] = pair_scope
    response["paper_a_id"] = a_id
    response["paper_b_id"] = b_id
    response["confidence_raw"] = _coerce_confidence(response.get("confidence"), fallback=3)
    response["confidence"] = response["confidence_raw"]
    if response.get("novelty") not in {"obvious", "non-obvious", "speculative"}:
        response["novelty"] = "non-obvious"
    ok, errors, fixed, _ = validate_schema(response, schema, path="/", fix=True)
    if not ok:
        fixed.setdefault("_schema_errors", errors)
    else:
        fixed.setdefault("status", "pending_review")
    return fixed


def _score_connection(connection: dict[str, Any], novelty_weight: bool = True) -> float:
    confidence = _coerce_confidence(connection.get("confidence"), fallback=1)
    weight = 1.0
    if novelty_weight:
        novelty = connection.get("novelty")
        if novelty == "non-obvious":
            weight = 2.0
        elif novelty == "obvious":
            weight = 1.0
        elif novelty == "speculative":
            weight = 0.5
    return confidence * weight


def _write_connection(
    base: Path,
    a_id: str,
    b_id: str,
    pair_scope: str,
    within_domain: str | None,
    payload: dict[str, Any],
) -> Path:
    if pair_scope == "within_domain":
        out = base / "within_domain" / str(within_domain or "general")
    else:
        out = base / "cross_domain"
    ensure_dir(out)
    out_path = out / f"{a_id}_{b_id}.yaml"
    write_yaml(out_path, payload)
    return out_path


def _normalize_connection(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    payload["status"] = payload.get("status", "pending_review")
    payload.setdefault("schema_version", 1)
    payload["pair_scope"] = payload.get("pair_scope", "within_domain")
    payload.setdefault("significance", "No significance provided.")
    payload["file"] = str(path)
    return payload


def _mark_connected(registry: Registry, a_entry: dict[str, Any], b_entry: dict[str, Any]) -> None:
    if a_entry.get("paper_id"):
        registry.update(a_entry["paper_id"], {"connected": True})
    if b_entry.get("paper_id"):
        registry.update(b_entry["paper_id"], {"connected": True})
