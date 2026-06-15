"""Detect skill: identify gaps from connected paper clusters."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

from ..config import Config, load_config
from ..llm import LLMClient
from ..registry import Registry
from ..schemas import validate as validate_schema
from ..skills.common import ensure_dir, now_iso, write_yaml


DETECT_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "DETECT_SCHEMA.yaml"


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect candidate gaps from connection clusters.")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--domain", help="Find intra-domain clusters.")
    scope.add_argument("--cross", nargs=2, metavar=("D1", "D2"), help="Find cross-domain clusters.")
    scope.add_argument("--all", action="store_true", help="Run on all connections.")
    scope.add_argument("--cluster", dest="cluster", help="Force one existing cluster id.")
    return parser


def _run_vigil(root: Path, phase: str) -> tuple[int, str]:
    result = subprocess.run(
        ["python3", str(root / "athanasor" / "vigil" / "verify.py"), phase],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    return result.returncode, (result.stdout + result.stderr)


def detect(
    *,
    config: Config | None = None,
    llm: LLMClient | None = None,
    domain: str | None = None,
    cross: tuple[str, str] | None = None,
    all_scope: bool = False,
    cluster: str | None = None,
) -> list[dict[str, Any]]:
    root = (config or load_config()).project_root
    root = Path(root).expanduser().resolve()
    _run_vigil(root, "start")

    registry = Registry(root / "albedo" / "registry.jsonl")
    paths = list(
        _collect_connection_paths(
            root,
            domain=domain,
            cross=cross,
            all_scope=all_scope,
            cluster=cluster,
        )
    )

    # Keep non-empty candidate pool for full scans and domain/filter runs.
    if not paths and not cluster:
        return []

    target_cluster = _resolve_cluster_override(root, cluster)

    graph: dict[str, set[str]] = defaultdict(set)
    edge_payload: dict[frozenset[str], dict[str, Any]] = {}
    for path in paths:
        payload = _load_yaml(path)
        if not payload:
            continue
        a_id = str(payload.get("paper_a_id") or "")
        b_id = str(payload.get("paper_b_id") or "")
        if not a_id or not b_id:
            continue
        if domain and payload.get("pair_scope") == "cross_domain":
            continue
        if cross and not _pair_matches_cross(payload, cross[0], cross[1]):
            continue
        graph[a_id].add(b_id)
        graph[b_id].add(a_id)
        edge_payload[frozenset({a_id, b_id})] = payload

    clusters = _connected_components(graph)
    if target_cluster is not None and all(paper_ids := sorted(target_cluster)):
        clusters = [set(paper_ids)]
    elif cluster:
        cluster_tokens = _normalize_cluster_hint(cluster)
        if cluster_tokens:
            clusters = [c for c in clusters if _cluster_matches_hint(c, cluster_tokens)]

    schema = _load_schema()
    outputs: list[dict[str, Any]] = []
    for papers in clusters:
        if len(papers) < 3:
            continue

        paper_records = [_load_library(root, p) for p in papers]
        exhaustion_records = [_load_exhaustion(root, p) for p in papers]
        connections = [payload for key, payload in edge_payload.items() if key.issubset(set(papers))]
        if not paper_records:
            continue

        cluster_id = "cluster_" + "_".join(sorted(papers)[:2]) + f"_{len(papers)}"
        if cluster_id not in _existing_hypothesis_ids(root):
            hypothesis = _synthesize_cluster(
                cluster_id=cluster_id,
                paper_records=paper_records,
                connections=connections,
                exhaustion_records=exhaustion_records,
                domain=domain,
                cross=cross,
                llm=llm,
                schema=schema,
            )
            if hypothesis:
                out_path = root / "rubedo" / "hypotheses" / f"{cluster_id}.yaml"
                write_yaml(out_path, hypothesis)
                _mark_detected(registry, papers)
                outputs.append(hypothesis)
                for paper_id in papers:
                    for entry in registry.list():
                        if entry.get("paper_id") == paper_id:
                            registry.update(paper_id, {"detected": True})

    _run_vigil(root, "verify")
    return outputs


def _collect_connection_paths(
    root: Path,
    *,
    domain: str | None,
    cross: tuple[str, str] | None,
    all_scope: bool,
    cluster: str | None,
) -> Iterable[Path]:
    if cluster and not all_scope and not domain and not cross:
        yield from root.joinpath("citrinitas", "within_domain").rglob("*.yaml")
        yield from root.joinpath("citrinitas", "cross_domain").rglob("*.yaml")
        return

    if all_scope:
        yield from root.joinpath("citrinitas", "within_domain").rglob("*.yaml")
        yield from root.joinpath("citrinitas", "cross_domain").rglob("*.yaml")
        return
    if domain:
        yield from (root / "citrinitas" / "within_domain" / domain).rglob("*.yaml")
        return
    if cross:
        yield from (root / "citrinitas" / "cross_domain").rglob("*.yaml")


def _normalize_cluster_hint(cluster: str) -> set[str]:
    if not cluster:
        return set()

    # Strip leading style tags such as ``cluster_`` and keep tokens stable.
    raw = cluster.strip()
    raw = raw.removeprefix("cluster_").strip("_")
    tokens = [token for token in raw.split("_") if token]
    return {token for token in tokens}


def _cluster_matches_hint(cluster: set[str], tokens: set[str]) -> bool:
    if not cluster or not tokens:
        return False
    return bool(cluster.intersection(tokens))


def _resolve_cluster_override(root: Path, cluster: str | None) -> set[str] | None:
    if not cluster:
        return None

    hypothesis_path = root / "rubedo" / "hypotheses" / f"{cluster}.yaml"
    if not hypothesis_path.exists():
        return None

    payload = _load_yaml(hypothesis_path)
    if not payload:
        return None

    paper_ids = payload.get("paper_ids")
    if not isinstance(paper_ids, list):
        return None

    resolved: set[str] = set()
    for paper_id in paper_ids:
        if isinstance(paper_id, str) and paper_id.strip():
            resolved.add(paper_id.strip())

    return resolved if len(resolved) >= 3 else None


def _pair_matches_cross(payload: dict[str, Any], d1: str, d2: str) -> bool:
    pd = payload.get("pair_domains") or {}
    return (
        (str(pd.get("paper_a_domain")) == d1 and str(pd.get("paper_b_domain")) == d2)
        or (str(pd.get("paper_a_domain")) == d2 and str(pd.get("paper_b_domain")) == d1)
    )


def _connected_components(graph: dict[str, set[str]]) -> list[set[str]]:
    visited = set()
    components: list[set[str]] = []

    for node in graph:
        if node in visited:
            continue
        stack = [node]
        component: set[str] = set()
        visited.add(node)
        while stack:
            curr = stack.pop()
            component.add(curr)
            for nxt in graph[curr]:
                if nxt not in visited:
                    visited.add(nxt)
                    stack.append(nxt)
        components.append(component)
    return components


def _existing_hypothesis_ids(root: Path) -> set[str]:
    out: set[str] = set()
    for path in (root / "rubedo" / "hypotheses").glob("*.yaml"):
        out.add(path.stem)
    return out


def _load_yaml(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        payload = yaml.safe_load(f)
    if isinstance(payload, dict):
        return payload
    return None


def _load_library(root: Path, paper_id: str) -> dict[str, Any] | None:
    path = root / "albedo" / "library" / f"{paper_id}.yaml"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        payload = yaml.safe_load(f)
    return payload if isinstance(payload, dict) else None


def _load_exhaustion(root: Path, paper_id: str) -> dict[str, Any] | None:
    path = root / "albedo" / "exhaust" / f"{paper_id}_exhaust.yaml"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        payload = yaml.safe_load(f)
    return payload if isinstance(payload, dict) else None


def _load_schema() -> dict[str, Any]:
    with open(DETECT_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _synthesize_cluster(
    cluster_id: str,
    paper_records: list[dict[str, Any] | None],
    connections: list[dict[str, Any]],
    exhaustion_records: list[dict[str, Any] | None],
    domain: str | None,
    cross: tuple[str, str] | None,
    llm: LLMClient | None,
    schema: dict[str, Any],
) -> dict[str, Any] | None:
    paper_records = [record for record in paper_records if isinstance(record, dict)]
    paper_ids = [str(record.get("id") or (record.get("source") or {}).get("title", "")) for record in paper_records]
    paper_titles = [str((record.get("source") or {}).get("title", paper_id)) for record, paper_id in zip(paper_records, paper_ids)]
    connection_summaries = [
        {
            "type": payload.get("connection_type"),
            "description": payload.get("description"),
            "score": payload.get("score"),
        }
        for payload in connections[:8]
        if isinstance(payload, dict)
    ]

    if not paper_records:
        return None

    if llm is None:
        return _fallback_detect(
            cluster_id,
            paper_records,
            connections,
            exhaustion_records,
            schema,
        )

    prompt = (
        "You are analyzing a cluster of papers.\n\n"
        f"Paper count: {len(paper_records)}\n"
        f"Domain filter: {domain or 'mixed'}{(' / ' + '↔'.join(cross)) if cross else ''}\n\n"
        f"Paper IDs: {', '.join(paper_ids)}\n"
        f"Paper titles: {', '.join(paper_titles)}\n"
        f"Connections: {json.dumps(connection_summaries, ensure_ascii=False)}\n"
        f"Exhaust records present: {sum(1 for r in exhaustion_records if r)}\n\n"
        "Return JSON matching DETECT_SCHEMA.yaml with up to 8 gaps, then include novelty/gap metadata."
    )
    result = llm.complete(
        prompt,
        structured=True,
        schema=schema,
        temperature=0.25,
        max_tokens=4096,
    )
    if not isinstance(result, dict):
        return _fallback_detect(
            cluster_id,
            paper_records,
            connections,
            exhaustion_records,
            schema,
        )
    result["cluster_id"] = cluster_id
    result["scope"] = domain or ("-".join(cross) if cross else "mixed")
    result["paper_ids"] = sorted({str(record.get("id") or (record.get("source") or {}).get("title", "")) for record in paper_records if isinstance(record, dict)})
    result["status"] = result.get("status", "pending_review")
    result["status"] = result.get("status") or "pending_review"
    result.setdefault("novelty", True)
    gaps = [gap for gap in result.get("gaps", []) if isinstance(gap, dict)]
    # Filter low-confidence gaps.
    gaps = [g for g in gaps if _coerce_confidence(g.get("confidence")) > 2]
    result["gaps"] = _rank_gaps(gaps)
    result["metadata"] = {
        "cluster_size": len(paper_records),
        "connection_count": len(connections),
        "detection_prompt_version": "azoth-connect-detect-v1",
        "generated_at": now_iso(),
    }
    result["schema_version"] = 1

    ok, errors, fixed, _ = validate_schema(result, schema, path="/", fix=True)
    if not ok:
        fallback = _fallback_detect(
            cluster_id,
            paper_records,
            connections,
            exhaustion_records,
            schema,
        )
        fallback["_schema_errors"] = errors
        return fallback
    if not fixed.get("gaps"):
        return _fallback_detect(
            cluster_id,
            paper_records,
            connections,
            exhaustion_records,
            schema,
        )
    return fixed


def _rank_gaps(gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for idx, gap in enumerate(gaps):
        gap.setdefault("rank", idx + 1)
        feasibility = _coerce_confidence(gap.get("feasibility"), default=1)
        gap["significance_weight"] = feasibility * 1.0
    gaps.sort(
        key=lambda item: (
            -float(item.get("significance_weight", 0.0)),
            -_coerce_confidence(item.get("feasibility", 1)),
            -_coerce_confidence(item.get("confidence", 1)),
        )
    )
    return gaps[:8]


def _fallback_detect(
    cluster_id: str,
    paper_records: list[dict[str, Any] | None],
    connections: list[dict[str, Any]],
    exhaustion_records: list[dict[str, Any] | None],
    schema: dict[str, Any],
) -> dict[str, Any]:
    paper_ids = [str(record.get("id") or (record.get("source") or {}).get("title", "")) for record in paper_records if record]
    payload = {
        "schema_version": 1,
        "cluster_id": cluster_id,
        "paper_ids": paper_ids,
        "scope": "fallback",
        "novelty": True,
        "summary": f"Fallback synthesis across {len(paper_ids)} papers based on {len(connections)} connections.",
        "status": "pending_review",
        "gaps": [
                {
                    "gap_type": "unexplored_question",
                    "description": "No LLM available; manual review needed.",
                    "novelty": True,
                    "supporting_papers": paper_ids,
                    "supporting_evidence": "Shared claims and methods suggest open cross-paper comparison is needed.",
                    "significance": "Could identify a transferable mechanism between papers.",
                    "feasibility": 2,
                "suggested_approach": "Run focused follow-up synthesis manually.",
                "confidence": 3,
            }
        ],
        "metadata": {
            "cluster_size": len(paper_ids),
            "connection_count": len(connections),
            "generated_at": now_iso(),
            "detection_prompt_version": "fallback",
        },
    }
    ok, errors, fixed, _ = validate_schema(payload, schema, path="/", fix=True)
    if not ok:
        raise ValueError("Fallback detect payload failed schema validation: " + "; ".join(errors))
    return fixed


def _mark_detected(registry: Registry, paper_ids: list[str]) -> None:
    for paper_id in paper_ids:
        try:
            registry.update(paper_id, {"detected": True})
        except Exception:
            continue


def _coerce_confidence(value: Any, default: int = 0) -> int:
    """Convert a user/LLM confidence representation into 1..5 integer scale."""
    text = str(value).strip().lower()
    if not text:
        return default

    label_map = {
        "very_low": 1,
        "low": 2,
        "medium": 3,
        "moderate": 3,
        "high": 4,
        "very_high": 5,
        "veryhigh": 5,
        "very high": 5,
    }
    if text in label_map:
        return label_map[text]

    try:
        parsed = int(float(text))
    except (TypeError, ValueError):
        return default

    return max(1, min(5, parsed))
