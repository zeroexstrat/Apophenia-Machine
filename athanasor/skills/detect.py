"""Detect skill: identify gaps from connected paper clusters."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import defaultdict
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..config import Config, load_config
from ..llm import LLMClient
from ..rejections import is_rejected
from ..registry import Registry
from ..schemas import validate as validate_schema
from ..skills.common import ensure_dir, load_yaml_tolerant, now_iso, run_vigil_check, write_yaml


DETECT_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "DETECT_SCHEMA.yaml"


@dataclass(frozen=True)
class _PreparedHypothesis:
    payload: dict[str, Any]
    destination: Path
    idempotent: bool
    suppressed: bool


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect candidate gaps from connection clusters.")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--domain", help="Find intra-domain clusters.")
    scope.add_argument("--cross", nargs=2, metavar=("D1", "D2"), help="Find cross-domain clusters.")
    scope.add_argument("--all", action="store_true", help="Run on all connections.")
    scope.add_argument("--cluster", dest="cluster", help="Force one existing cluster id.")
    return parser


def _run_vigil(root: Path, phase: str) -> tuple[int, str]:
    output = run_vigil_check(root=root, phase=phase, skill="detect")
    return 0, output


def stable_cluster_id(paper_ids: Iterable[str]) -> str:
    ids = sorted(
        {
            str(item).strip()
            for item in paper_ids
            if str(item).strip()
        }
    )
    digest = hashlib.sha256(
        json.dumps(ids, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    return f"cluster_{digest}"


def load_agent_hypotheses(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read hypothesis records JSON {path}: {exc}") from None
    if isinstance(payload, dict):
        if set(payload) != {"hypotheses"} or not isinstance(payload.get("hypotheses"), list):
            raise ValueError('Hypothesis packet object must contain only a "hypotheses" array.')
        payload = payload["hypotheses"]
    if not isinstance(payload, list):
        raise ValueError("Hypothesis records must be a JSON array or an exact hypotheses wrapper.")
    if any(not isinstance(item, dict) for item in payload):
        raise ValueError("Every hypothesis record must be a JSON object.")
    return [deepcopy(item) for item in payload]


def _render_yaml(payload: dict[str, Any]) -> bytes:
    return yaml.safe_dump(payload, sort_keys=False).encode("utf-8")


def _snapshot(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def _restore(path: Path, snapshot: bytes | None) -> None:
    if snapshot is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(snapshot)


def _atomic_write(path: Path, rendered: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _prepare_agent_hypothesis(
    root: Path,
    registry: Registry,
    record: dict[str, Any],
) -> _PreparedHypothesis:
    payload = deepcopy(record)
    payload.pop("file", None)
    raw_ids = payload.get("paper_ids")
    if not isinstance(raw_ids, list):
        raise ValueError("paper_ids must be a list of at least three distinct IDs")
    paper_ids = sorted({str(item).strip() for item in raw_ids if str(item).strip()})
    if len(paper_ids) < 3:
        raise ValueError("hypothesis requires at least three distinct paper IDs")
    expected_cluster_id = stable_cluster_id(paper_ids)
    if str(payload.get("cluster_id") or "").strip() != expected_cluster_id:
        raise ValueError(f"cluster_id must be {expected_cluster_id} for the supplied paper_ids")
    for paper_id in paper_ids:
        entry = registry.get(paper_id)
        if not isinstance(entry, dict):
            raise ValueError(f"registry is missing paper ID: {paper_id}")
        paths = entry.get("paths") if isinstance(entry.get("paths"), dict) else {}
        rel = paths.get("library") or f"albedo/library/{paper_id}.yaml"
        if load_yaml_tolerant(root / rel) is None:
            raise ValueError(f"library record missing or unreadable for {paper_id}: {rel}")

    payload["paper_ids"] = paper_ids
    payload["cluster_id"] = expected_cluster_id
    payload["status"] = "pending_review"
    allowed_ids = set(paper_ids)
    for gap_index, gap in enumerate(payload.get("gaps", []), 1):
        if not isinstance(gap, dict):
            continue
        supporting = {
            str(item).strip()
            for item in gap.get("supporting_papers", [])
            if str(item).strip()
        }
        outside = sorted(supporting.difference(allowed_ids))
        if outside:
            raise ValueError(
                f"gap {gap_index} supporting_papers reference IDs outside cluster: {', '.join(outside)}"
            )

    ok, errors, _, changed = validate_schema(payload, _load_schema(), path="/", fix=False)
    if not ok or errors or changed:
        raise ValueError("hypothesis schema invalid: " + "; ".join(errors))
    destination = root / "rubedo" / "hypotheses" / f"{expected_cluster_id}.yaml"
    ledger_path = root / "athanasor" / "lapis" / "rejections.jsonl"
    suppressed = is_rejected(ledger_path, payload)
    rendered = _render_yaml(payload)
    idempotent = not suppressed and destination.exists() and destination.read_bytes() == rendered
    if not suppressed and destination.exists() and not idempotent:
        raise ValueError(f"hypothesis output collision at {destination}")
    return _PreparedHypothesis(payload, destination, idempotent, suppressed)


def apply_agent_hypotheses(
    records: list[dict[str, Any]],
    *,
    config: Config | None = None,
) -> list[dict[str, Any]]:
    cfg = config or load_config()
    root = Path(cfg.project_root).expanduser().resolve()
    _run_vigil(root, "start")
    registry_path = root / "albedo" / "registry.jsonl"
    if not registry_path.exists():
        raise ValueError(f"registry is missing: {registry_path}")
    registry = Registry(registry_path)

    prepared: list[_PreparedHypothesis] = []
    errors: list[str] = []
    seen: set[str] = set()
    for index, record in enumerate(records, 1):
        try:
            item = _prepare_agent_hypothesis(root, registry, record)
            cluster_id = item.payload["cluster_id"]
            if cluster_id in seen:
                raise ValueError(f"duplicate cluster {cluster_id} in packet")
            seen.add(cluster_id)
            prepared.append(item)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"record {index}: {exc}")
    if errors:
        raise ValueError("Hypothesis packet validation failed: " + "; ".join(errors))

    snapshots: dict[Path, bytes | None] = {registry_path: _snapshot(registry_path)}
    for item in prepared:
        snapshots[item.destination] = _snapshot(item.destination)
    try:
        for item in prepared:
            if not item.suppressed and not item.idempotent:
                _atomic_write(item.destination, _render_yaml(item.payload))
        for item in prepared:
            if item.suppressed or item.idempotent:
                continue
            for paper_id in item.payload["paper_ids"]:
                registry.update(paper_id, {"detected": True})
        _run_vigil(root, "verify")
    except BaseException:
        for path, snapshot in snapshots.items():
            _restore(path, snapshot)
        raise

    outputs: list[dict[str, Any]] = []
    for item in prepared:
        if item.suppressed:
            outputs.append(
                {"cluster_id": item.payload["cluster_id"], "status": "suppressed_rejection"}
            )
            continue
        output = deepcopy(item.payload)
        output["file"] = str(item.destination)
        outputs.append(output)
    return outputs


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

        cluster_id = stable_cluster_id(papers)
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
                if is_rejected(root / "athanasor" / "lapis" / "rejections.jsonl", hypothesis):
                    continue
                out_path = root / "rubedo" / "hypotheses" / f"{cluster_id}.yaml"
                write_yaml(out_path, hypothesis)
                _mark_detected(registry, papers)
                outputs.append(hypothesis)

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
    return load_yaml_tolerant(path)


def _load_library(root: Path, paper_id: str) -> dict[str, Any] | None:
    return load_yaml_tolerant(root / "albedo" / "library" / f"{paper_id}.yaml")


def _load_exhaustion(root: Path, paper_id: str) -> dict[str, Any] | None:
    return load_yaml_tolerant(root / "albedo" / "exhaust" / f"{paper_id}_exhaust.yaml")


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
        return None

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
        return None
    result["cluster_id"] = cluster_id
    result["scope"] = domain or ("-".join(cross) if cross else "mixed")
    result["paper_ids"] = sorted({str(record.get("id") or (record.get("source") or {}).get("title", "")) for record in paper_records if isinstance(record, dict)})
    result["status"] = "pending_review"
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
        return None
    if not fixed.get("gaps"):
        return None
    fixed["status"] = "pending_review"
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
