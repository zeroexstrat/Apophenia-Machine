"""Connect skill: Citrinitas pair discovery and connection synthesis."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from ..config import Config, load_config
from ..embeddings import EmbeddingStore
from ..llm import LLMClient
from ..registry import Registry
from ..resources import resource_yaml
from ..schemas import validate as validate_schema
from ..skills.common import (
    ensure_dir,
    is_specific_text,
    load_yaml_tolerant,
    now_iso,
    run_vigil_check,
    slugify,
    write_yaml,
)


GENERIC_PAIR_TAGS = {"fallback", "ingested", "automated", "pdf", "paper"}
HIGH_SIGNAL_PAIR_TAGS = {
    "adaptive_computation",
    "knowledge_distillation",
    "latent_dynamics",
    "latent_moe",
    "looped_transformer",
    "mamba_transformer",
    "mixture_of_experts",
    "state_space_models",
    "world_model",
}
STRONG_TAG_OVERLAP_COUNT = 2


@dataclass(frozen=True)
class _PreparedConnection:
    payload: dict[str, Any]
    destination: Path
    a_entry: dict[str, Any]
    b_entry: dict[str, Any]
    idempotent: bool


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Find structural links between papers.")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--within", dest="within", help="Domain for within-domain pass.")
    scope.add_argument("--cross", nargs=2, metavar=("D1", "D2"), help="Domain pair for cross-domain pass.")
    scope.add_argument("--paper", dest="paper_id", help="Single paper id")
    scope.add_argument("--all", action="store_true", help="Run all scopes.")
    parser.add_argument(
        "--reanalyze-depth-upgrades",
        action="store_true",
        help="Re-run previously analyzed pairs when either paper was exhausted at a deeper depth.",
    )
    return parser


def _run_vigil(root: Path, phase: str) -> tuple[int, str]:
    output = run_vigil_check(root=root, phase=phase, skill="connect")
    return 0, output


def load_agent_connections(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read connection records JSON {path}: {exc}") from None
    if isinstance(payload, dict):
        if set(payload) != {"connections"} or not isinstance(payload.get("connections"), list):
            raise ValueError('Connection packet object must contain only a "connections" array.')
        payload = payload["connections"]
    if not isinstance(payload, list):
        raise ValueError("Connection records must be a JSON array or an exact connections wrapper.")
    if any(not isinstance(item, dict) for item in payload):
        raise ValueError("Every connection record must be a JSON object.")
    return [deepcopy(item) for item in payload]


def _connection_destination(
    root: Path,
    payload: dict[str, Any],
    a_entry: dict[str, Any],
) -> Path:
    filename = f"{payload['paper_a_id']}_{payload['paper_b_id']}.yaml"
    if payload["pair_scope"] == "within_domain":
        return root / "citrinitas" / "within_domain" / str(a_entry.get("domain") or "unknown") / filename
    return root / "citrinitas" / "cross_domain" / filename


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


def _prepare_agent_connection(
    root: Path,
    registry: Registry,
    record: dict[str, Any],
) -> _PreparedConnection:
    payload = deepcopy(record)
    payload.pop("file", None)
    raw_a_id = str(payload.get("paper_a_id") or "").strip()
    raw_b_id = str(payload.get("paper_b_id") or "").strip()
    if not raw_a_id or not raw_b_id or raw_a_id == raw_b_id:
        raise ValueError("connection requires two distinct paper IDs")
    a_id, b_id = sorted((raw_a_id, raw_b_id))
    a_entry = registry.get(a_id)
    b_entry = registry.get(b_id)
    if not isinstance(a_entry, dict) or not isinstance(b_entry, dict):
        missing = [
            paper_id
            for paper_id, entry in ((a_id, a_entry), (b_id, b_entry))
            if not isinstance(entry, dict)
        ]
        raise ValueError("registry is missing paper IDs: " + ", ".join(missing))
    for paper_id, entry in ((a_id, a_entry), (b_id, b_entry)):
        paths = entry.get("paths") if isinstance(entry.get("paths"), dict) else {}
        rel = paths.get("library") or f"albedo/library/{paper_id}.yaml"
        if load_yaml_tolerant(root / rel) is None:
            raise ValueError(f"library record missing or unreadable for {paper_id}: {rel}")

    scope = str(payload.get("pair_scope") or "").strip()
    if scope not in {"within_domain", "cross_domain"}:
        raise ValueError("pair_scope must be within_domain or cross_domain")
    same_domain = str(a_entry.get("domain")) == str(b_entry.get("domain"))
    if scope == "within_domain" and not same_domain:
        raise ValueError("within_domain record references different registry domains")
    if scope == "cross_domain" and same_domain:
        raise ValueError("cross_domain record references the same registry domain")

    payload["paper_a_id"] = a_id
    payload["paper_b_id"] = b_id
    payload["pair_domains"] = {
        "paper_a_domain": str(a_entry.get("domain") or "unknown"),
        "paper_b_domain": str(b_entry.get("domain") or "unknown"),
    }
    payload["status"] = "pending_review"
    raw_confidence = _coerce_confidence(
        payload.get("confidence_raw", payload.get("confidence")),
        fallback=0,
    )
    if not 1 <= raw_confidence <= 5:
        raise ValueError("confidence_raw must resolve to an integer from 1 through 5")
    payload["confidence_raw"] = raw_confidence
    payload["confidence"] = max(1, raw_confidence - (1 if scope == "cross_domain" else 0))
    payload["score"] = _score_connection(payload, novelty_weight=True)
    for field in ("evidence_a", "evidence_b"):
        if not is_specific_text(payload.get(field)):
            raise ValueError(f"{field} must contain specific non-placeholder evidence")

    ok, errors, _, changed = validate_schema(payload, _load_schema(), path="/", fix=False)
    if not ok or errors or changed:
        raise ValueError("connection schema invalid: " + "; ".join(errors))
    destination = _connection_destination(root, payload, a_entry)
    rendered = _render_yaml(payload)
    idempotent = destination.exists() and destination.read_bytes() == rendered
    if destination.exists() and not idempotent:
        raise ValueError(f"connection output collision at {destination}")
    return _PreparedConnection(payload, destination, a_entry, b_entry, idempotent)


def apply_agent_connections(
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

    prepared: list[_PreparedConnection] = []
    errors: list[str] = []
    seen: set[str] = set()
    for index, record in enumerate(records, 1):
        try:
            item = _prepare_agent_connection(root, registry, record)
            pair = _pair_key(item.payload["paper_a_id"], item.payload["paper_b_id"])
            if pair in seen:
                raise ValueError(f"duplicate pair {pair} in packet")
            seen.add(pair)
            prepared.append(item)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"record {index}: {exc}")
    if errors:
        raise ValueError("Connection packet validation failed: " + "; ".join(errors))

    analyzed_path = root / "albedo" / "connections_analyzed.jsonl"
    snapshots: dict[Path, bytes | None] = {
        registry_path: _snapshot(registry_path),
        analyzed_path: _snapshot(analyzed_path),
    }
    for item in prepared:
        snapshots[item.destination] = _snapshot(item.destination)

    try:
        for item in prepared:
            if not item.idempotent:
                _atomic_write(item.destination, _render_yaml(item.payload))
        for item in prepared:
            if item.idempotent:
                continue
            _mark_connected(registry, item.a_entry, item.b_entry)
            _append_analyzed(
                analyzed_path,
                item.payload["paper_a_id"],
                item.payload["paper_b_id"],
                paper_depths=_paper_depths(item.a_entry, item.b_entry),
                reanalysis_reason="agent_import",
            )
        _run_vigil(root, "verify")
    except BaseException:
        for path, snapshot in snapshots.items():
            _restore(path, snapshot)
        raise

    outputs: list[dict[str, Any]] = []
    for item in prepared:
        output = deepcopy(item.payload)
        output["file"] = str(item.destination)
        outputs.append(output)
    return outputs


def connect(
    *,
    config: Config | None = None,
    llm: LLMClient | None = None,
    within: str | None = None,
    cross: tuple[str, str] | None = None,
    paper_id: str | None = None,
    all_scope: bool = False,
    reanalyze_depth_upgrades: bool = False,
) -> list[dict[str, Any]]:
    cfg = config or load_config()
    root = Path(cfg.project_root).expanduser().resolve()
    _run_vigil(root, "start")

    registry = Registry(root / "albedo" / "registry.jsonl")
    store = EmbeddingStore(root / cfg.embeddings["store_path"], model_name=cfg.embeddings.get("model", "all-MiniLM-L6-v2"))
    schema = _load_schema()
    persistence_threshold = 3
    report_stats: dict[str, Any] = Counter(
        candidate_pairs=0,
        analyzed_pairs=0,
        pairs_with_no_connection=0,
        below_confidence=0,
        speculative_filtered=0,
        validation_failed=0,
        skipped_similarity=0,
        skipped_missing_records=0,
        retrieval_candidates=0,
    )

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
    connection_types: Counter[str] = Counter()
    library_records: dict[str, dict[str, Any]] = {}

    for a_id, b_id, pair_scope, pair_domain in pairs:
        a_id, b_id = sorted([str(a_id), str(b_id)])
        key = _pair_key(a_id, b_id)

        a_entry = registry.get(a_id)
        b_entry = registry.get(b_id)
        if not isinstance(a_entry, dict) or not isinstance(b_entry, dict):
            if llm is not None:
                analyzed[key] = _append_analyzed(
                    root / "albedo" / "connections_analyzed.jsonl",
                    a_id,
                    b_id,
                    paper_depths={},
                    reanalysis_reason="missing_registry_entry",
                )
            continue

        existing_event = analyzed.get(key) if llm is not None else None
        if existing_event is not None and _should_skip_analyzed_pair(
            existing_event,
            a_entry,
            b_entry,
            reanalyze_depth_upgrades=reanalyze_depth_upgrades,
        ):
            continue
        reanalysis_reason = "depth_upgrade" if existing_event is not None else "initial"

        sim = _pair_similarity(a_id, b_id, store)
        if not _should_analyze_pair(
            a_entry,
            b_entry,
            similarity=sim,
            similarity_threshold=cfg.embeddings.get("similarity_threshold", 0.82),
        ):
            report_stats["skipped_similarity"] += 1
            if llm is not None and existing_event is not None:
                analyzed[key] = _append_analyzed(
                    root / "albedo" / "connections_analyzed.jsonl",
                    a_id,
                    b_id,
                    paper_depths=_paper_depths(a_entry, b_entry),
                    reanalysis_reason=f"{reanalysis_reason}_skipped_similarity",
                )
            continue

        report_stats["candidate_pairs"] += 1
        if llm is None:
            retrieval = build_retrieval_candidate(
                a_entry,
                b_entry,
                pair_scope=pair_scope,
                similarity=sim if store.size else None,
            )
            _write_retrieval_candidate(root, retrieval)
            output.append(retrieval)
            report_stats["retrieval_candidates"] += 1
            continue

        record_a = library_records.get(a_id)
        if record_a is None:
            record_a = _load_library_record(root, a_entry.get("paths", {}).get("library"), a_id) or {}
            if record_a:
                library_records[a_id] = record_a
        record_b = library_records.get(b_id)
        if record_b is None:
            record_b = _load_library_record(root, b_entry.get("paths", {}).get("library"), b_id) or {}
            if record_b:
                library_records[b_id] = record_b
        if not record_a or not record_b:
            report_stats["skipped_missing_records"] += 1
            analyzed[key] = _append_analyzed(
                root / "albedo" / "connections_analyzed.jsonl",
                a_id,
                b_id,
                paper_depths=_paper_depths(a_entry, b_entry),
                reanalysis_reason="missing_library_record",
            )
            continue

        exhaust_a = _load_exhaustion_record(root, a_entry, a_id)
        exhaust_b = _load_exhaustion_record(root, b_entry, b_id)
        candidate = _analyze_pair(
            a_id,
            b_id,
            record_a,
            record_b,
            pair_scope,
            llm,
            schema,
            exhaust_a=exhaust_a,
            exhaust_b=exhaust_b,
        )
        if not candidate:
            report_stats["pairs_with_no_connection"] += 1
            analyzed[key] = _append_analyzed(
                root / "albedo" / "connections_analyzed.jsonl",
                a_id,
                b_id,
                paper_depths=_paper_depths(a_entry, b_entry),
                reanalysis_reason=reanalysis_reason,
            )
            continue

        confidence_raw = _coerce_confidence(candidate.get("confidence"), fallback=3)
        report_stats["analyzed_pairs"] += 1
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
            report_stats["validation_failed"] += 1
            analyzed[key] = _append_analyzed(
                root / "albedo" / "connections_analyzed.jsonl",
                a_id,
                b_id,
                paper_depths=_paper_depths(a_entry, b_entry),
                reanalysis_reason=reanalysis_reason,
            )
            continue
        candidate = fixed
        candidate["status"] = "pending_review"

        if candidate.get("novelty") == "speculative" and candidate["confidence"] < 4:
            report_stats["speculative_filtered"] += 1
            analyzed[key] = _append_analyzed(
                root / "albedo" / "connections_analyzed.jsonl",
                a_id,
                b_id,
                paper_depths=_paper_depths(a_entry, b_entry),
                reanalysis_reason=reanalysis_reason,
            )
            continue

        if candidate["confidence"] < persistence_threshold:
            report_stats["below_confidence"] += 1
            analyzed[key] = _append_analyzed(
                root / "albedo" / "connections_analyzed.jsonl",
                a_id,
                b_id,
                paper_depths=_paper_depths(a_entry, b_entry),
                reanalysis_reason=reanalysis_reason,
            )
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
        if connection_type := record.get("connection_type"):
            if isinstance(connection_type, str):
                connection_types[connection_type] += 1

        _mark_connected(registry, a_entry, b_entry)
        analyzed[key] = _append_analyzed(
            root / "albedo" / "connections_analyzed.jsonl",
            a_id,
            b_id,
            paper_depths=_paper_depths(a_entry, b_entry),
            reanalysis_reason=reanalysis_reason,
        )

    scope = _scope_label(within=within, cross=cross, paper_id=paper_id, all_scope=all_scope)
    if llm is None:
        _write_retrieval_report(
            root / "citrinitas" / "reports",
            output=output,
            pairs=pairs,
            pair_stats=report_stats,
            scope=scope,
        )
    else:
        _write_connection_report(
            root / "citrinitas" / "reports",
            output=output,
            pairs=pairs,
            pair_stats=report_stats,
            output_by_type=connection_types,
            library_records=library_records,
            scope=scope,
        )
    _run_vigil(root, "verify")
    return output

def _load_schema() -> dict[str, Any]:
    payload = resource_yaml("CONNECT_SCHEMA.yaml")
    return payload if isinstance(payload, dict) else {}


def _load_retrieval_schema() -> dict[str, Any]:
    payload = resource_yaml("RETRIEVAL_SCHEMA.yaml")
    return payload if isinstance(payload, dict) else {}


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


def _load_analyzed(path: Path) -> dict[str, dict[str, Any]]:
    analyzed: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return analyzed
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            try:
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    key = payload.get("pair")
                    if isinstance(key, str):
                        analyzed[key] = payload
            except json.JSONDecodeError:
                continue
    return analyzed


def _append_analyzed(
    path: Path,
    a_id: str,
    b_id: str,
    *,
    paper_depths: dict[str, int] | None = None,
    reanalysis_reason: str = "initial",
) -> dict[str, Any]:
    ensure_dir(path.parent)
    payload = {
        "pair": _pair_key(a_id, b_id),
        "analyzed_at": now_iso(),
        "paper_depths": paper_depths or {},
        "reanalysis_reason": reanalysis_reason,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")
    return payload


def _depth_for_entry(entry: dict[str, Any]) -> int:
    try:
        return int(entry.get("exhausted_at_depth") or 0)
    except (TypeError, ValueError):
        return 0


def _paper_depths(a_entry: dict[str, Any], b_entry: dict[str, Any]) -> dict[str, int]:
    depths: dict[str, int] = {}
    for entry in (a_entry, b_entry):
        paper_id = entry.get("paper_id")
        if isinstance(paper_id, str) and paper_id:
            depths[paper_id] = _depth_for_entry(entry)
    return depths


def _should_skip_analyzed_pair(
    event: dict[str, Any],
    a_entry: dict[str, Any],
    b_entry: dict[str, Any],
    *,
    reanalyze_depth_upgrades: bool,
) -> bool:
    if not reanalyze_depth_upgrades:
        return True

    recorded_depths = event.get("paper_depths")
    if not isinstance(recorded_depths, dict):
        recorded_depths = {}

    for entry in (a_entry, b_entry):
        paper_id = entry.get("paper_id")
        if not isinstance(paper_id, str) or not paper_id:
            continue
        current_depth = _depth_for_entry(entry)
        try:
            recorded_depth = int(recorded_depths.get(paper_id) or 0)
        except (TypeError, ValueError):
            recorded_depth = 0
        if current_depth > recorded_depth:
            return False
    return True


def _scope_label(
    *,
    within: str | None = None,
    cross: tuple[str, str] | None = None,
    paper_id: str | None = None,
    all_scope: bool = False,
) -> str:
    if within:
        return f"within::{within}"
    if cross:
        return f"cross::{cross[0]}::{cross[1]}"
    if paper_id:
        return f"paper::{paper_id}"
    if all_scope:
        return "all"
    return "unknown"


def _normalize_text(raw: Any) -> str:
    return str(raw or "").strip().lower()


def _paper_title(record: dict[str, Any] | None) -> str:
    if not record:
        return ""
    return _normalize_text((record.get("source") or {}).get("title"))


def _connection_targets(record: dict[str, Any] | None) -> set[str]:
    if not record:
        return set()
    targets: set[str] = set()
    for item in record.get("connections_explicit", []) or []:
        if not isinstance(item, dict):
            continue
        target = item.get("target_paper")
        if not target:
            continue
        targets.add(_normalize_text(target))
    return targets


def _is_connection_visible_from_extraction(
    record_a: dict[str, Any],
    record_b: dict[str, Any],
    a_id: str,
    b_id: str,
) -> bool:
    title_a = _paper_title(record_a)
    title_b = _paper_title(record_b)
    targets_a = _connection_targets(record_a)
    targets_b = _connection_targets(record_b)
    if title_b and title_b in targets_a:
        return True
    if title_a and title_a in targets_b:
        return True
    if b_id and b_id in targets_a:
        return True
    if a_id and a_id in targets_b:
        return True
    return False


def _write_connection_report(
    report_dir: Path,
    *,
    output: list[dict[str, Any]],
    pairs: list[tuple[str, str, str, str]],
    pair_stats: dict[str, Any],
    output_by_type: Counter[str],
    library_records: dict[str, dict[str, Any]],
    scope: str,
) -> Path:
    ensure_dir(report_dir)
    path = report_dir / f"connect_report_{slugify(scope)}_{now_iso().replace(':', '-').replace('+', 'p')}.yaml"

    confidence_counts: Counter[int] = Counter()
    for item in output:
        confidence = _coerce_confidence(item.get("confidence"), fallback=0)
        if confidence >= 1:
            confidence_counts[confidence] += 1

    top_by_score = sorted(
        output,
        key=lambda item: float(item.get("score", 0.0)),
        reverse=True,
    )[:5]
    top_payload = [
        {
            "paper_a_id": item.get("paper_a_id"),
            "paper_b_id": item.get("paper_b_id"),
            "score": item.get("score"),
            "confidence": _coerce_confidence(item.get("confidence"), fallback=0),
            "connection_type": item.get("connection_type"),
            "novelty": item.get("novelty"),
            "description": item.get("description"),
        }
        for item in top_by_score
    ]

    extraction_visible = 0
    for item in output:
        if not isinstance(item.get("paper_a_id"), str) or not isinstance(item.get("paper_b_id"), str):
            continue
        a_id = item.get("paper_a_id", "")
        b_id = item.get("paper_b_id", "")
        if _is_connection_visible_from_extraction(
            library_records.get(a_id, {}),
            library_records.get(b_id, {}),
            a_id,
            b_id,
        ):
            extraction_visible += 1

    payload: dict[str, Any] = {
        "scope": scope,
        "generated_at": now_iso(),
        "pairs": {
            "total_pairs": len(pairs),
            "candidate_pairs": pair_stats["candidate_pairs"],
            "analyzed_pairs": pair_stats["analyzed_pairs"],
            "pairs_with_no_connection": pair_stats["pairs_with_no_connection"],
            "skipped_similarity": pair_stats["skipped_similarity"],
            "skipped_missing_records": pair_stats["skipped_missing_records"],
            "validation_failed": pair_stats["validation_failed"],
            "speculative_filtered": pair_stats["speculative_filtered"],
            "below_confidence_threshold": pair_stats["below_confidence"],
        },
        "connections": {
            "total_found": len(output),
            "by_confidence": {str(k): v for k, v in sorted(confidence_counts.items())},
            "by_type": dict(sorted(output_by_type.items())),
        },
        "connections_from_exhaustion": {
            "count": max(0, len(output) - extraction_visible),
            "example_pairs": [
                {
                    "paper_a_id": item.get("paper_a_id"),
                    "paper_b_id": item.get("paper_b_id"),
                }
                for item in top_by_score[:3]
            ],
        },
        "top_5_connections": top_payload,
    }

    write_yaml(path, payload)
    return path


def build_retrieval_candidate(
    a_entry: dict[str, Any],
    b_entry: dict[str, Any],
    *,
    pair_scope: str,
    similarity: float | None,
) -> dict[str, Any]:
    entries = {
        str(a_entry.get("paper_id") or ""): a_entry,
        str(b_entry.get("paper_id") or ""): b_entry,
    }
    paper_a_id, paper_b_id = sorted(entries)
    if not paper_a_id or not paper_b_id or paper_a_id == paper_b_id:
        raise ValueError("Retrieval candidates require two distinct paper IDs.")
    shared_tags = sorted(_shared_tags(entries[paper_a_id], entries[paper_b_id]))
    if not shared_tags:
        raise ValueError("Retrieval candidates require at least one shared non-generic tag.")
    reasons = ["shared_non_generic_tags:" + ",".join(shared_tags)]
    if similarity is not None:
        reasons.append(f"embedding_similarity:{float(similarity):.6f}")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "artifact_type": "retrieval_candidate",
        "pair_id": _pair_key(paper_a_id, paper_b_id),
        "paper_a_id": paper_a_id,
        "paper_b_id": paper_b_id,
        "pair_scope": pair_scope,
        "pair_domains": {
            "paper_a_domain": str(entries[paper_a_id].get("domain") or "unknown"),
            "paper_b_domain": str(entries[paper_b_id].get("domain") or "unknown"),
        },
        "shared_tags": shared_tags,
        "similarity": similarity,
        "selection_reasons": reasons,
        "status": "pending_assessment",
        "metadata": {
            "method": "deterministic_retrieval",
            "generated_at": now_iso(),
        },
    }
    ok, errors, _, changed = validate_schema(
        payload,
        _load_retrieval_schema(),
        path="/",
        fix=False,
    )
    if not ok or errors or changed:
        raise ValueError("Retrieval candidate failed schema validation: " + "; ".join(errors))
    return payload


def _write_retrieval_candidate(root: Path, payload: dict[str, Any]) -> Path:
    path = (
        root
        / "citrinitas"
        / "retrieval_candidates"
        / f"{payload['paper_a_id']}_{payload['paper_b_id']}.yaml"
    )
    write_yaml(path, payload)
    return path


def _write_retrieval_report(
    report_dir: Path,
    *,
    output: list[dict[str, Any]],
    pairs: list[tuple[str, str, str, str]],
    pair_stats: dict[str, Any],
    scope: str,
) -> Path:
    ensure_dir(report_dir)
    path = report_dir / f"retrieval_report_{slugify(scope)}_{now_iso().replace(':', '-').replace('+', 'p')}.yaml"
    payload = {
        "artifact_type": "retrieval_report",
        "scope": scope,
        "generated_at": now_iso(),
        "method": "deterministic_retrieval",
        "total_pairs": len(pairs),
        "retrieval_candidates": len(output),
        "skipped_similarity": pair_stats["skipped_similarity"],
        "candidate_pairs": [item["pair_id"] for item in output],
        "interpretation": (
            "Pairs are queued for substantive assessment; this report contains no connection, "
            "novelty, evidence, or confidence claims."
        ),
    }
    write_yaml(path, payload)
    return path


def _has_shared_tags(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return bool(_shared_tags(a, b))


def _shared_tags(a: dict[str, Any], b: dict[str, Any]) -> set[str]:
    a_tags = _meaningful_tags(a)
    b_tags = _meaningful_tags(b)
    return a_tags.intersection(b_tags)


def _meaningful_tags(entry: dict[str, Any]) -> set[str]:
    tags: set[str] = set()
    for raw in entry.get("tags", []) or []:
        if not isinstance(raw, str):
            continue
        tag = raw.strip().lower()
        if not tag or tag in GENERIC_PAIR_TAGS:
            continue
        tags.add(tag)
    return tags


def _should_analyze_pair(
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    similarity: float,
    similarity_threshold: float,
) -> bool:
    if similarity >= similarity_threshold:
        return True
    shared = _shared_tags(a, b)
    return bool(shared.intersection(HIGH_SIGNAL_PAIR_TAGS)) or len(shared) >= STRONG_TAG_OVERLAP_COUNT


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
        payload = load_yaml_tolerant(root / rel_path)
        if payload is not None:
            return payload
    return load_yaml_tolerant(root / "albedo" / "library" / f"{paper_id}.yaml")


def _load_exhaustion_record(root: Path, entry: dict[str, Any], paper_id: str) -> dict[str, Any]:
    rel_path = None
    paths = entry.get("paths")
    if isinstance(paths, dict):
        rel_path = paths.get("exhaust")

    candidates: list[Path] = []
    if isinstance(rel_path, str) and rel_path:
        candidates.append(root / rel_path)
    candidates.append(root / "albedo" / "exhaust" / f"{paper_id}_exhaust.yaml")

    for candidate in candidates:
        payload = load_yaml_tolerant(candidate)
        if payload is not None:
            return payload
    return {}


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


EXHAUST_PROMPT_BUCKETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("derivations", ("statement", "follows_from", "confidence")),
    ("exercises", ("problem", "solution", "difficulty")),
    ("missing_angles", ("angle", "where_it_lands", "why_missed")),
    ("open_questions", ("question", "how_to_close", "closable")),
    ("unstated_assumptions", ("assumption", "impacts_claim")),
    ("experiments", ("hypothesis", "design", "predicted_true", "predicted_false")),
    ("necessary_connections", ("work", "why_necessary")),
)


def _paper_prompt_block(paper_id: str, record: dict[str, Any], exhaust: dict[str, Any]) -> str:
    title = record.get("source", {}).get("title", paper_id)
    claims = [item.get("statement") for item in record.get("claims", [])[:5] if isinstance(item, dict)]
    methods = [item.get("name") for item in record.get("methods", [])[:5] if isinstance(item, dict)]
    techniques = [item.get("name") for item in record.get("techniques", [])[:5] if isinstance(item, dict)]
    equations = [item.get("latex") or item.get("expression") for item in record.get("equations", [])[:3] if isinstance(item, dict)]
    exhaust_lines = _exhaust_summary_lines(exhaust)

    lines = [
        f"Paper: {title}",
        f"Paper ID: {paper_id}",
        f"Claims: {claims}",
        f"Methods: {methods}",
        f"Techniques: {techniques}",
    ]
    if equations:
        lines.append(f"Equations: {equations}")
    if exhaust_lines:
        lines.append("Exhaustion outputs:")
        lines.extend(f"- {line}" for line in exhaust_lines)
    else:
        lines.append("Exhaustion outputs: none found")
    return "\n".join(lines)


def _exhaust_summary_lines(exhaust: dict[str, Any], *, max_items_per_bucket: int = 3) -> list[str]:
    if not isinstance(exhaust, dict) or not exhaust:
        return []

    normalized = dict(exhaust)
    nested = exhaust.get("exhaustion")
    if isinstance(nested, dict):
        for key, value in nested.items():
            normalized.setdefault(key, value)

    lines: list[str] = []
    for bucket, keys in EXHAUST_PROMPT_BUCKETS:
        values = normalized.get(bucket)
        if not isinstance(values, list) or not values:
            continue
        for item in values[:max_items_per_bucket]:
            summary = _exhaust_item_summary(item, keys)
            if summary:
                lines.append(f"{bucket}: {summary}")
    return lines


def _exhaust_item_summary(item: Any, keys: tuple[str, ...]) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return ""

    parts: list[str] = []
    for key in keys:
        value = item.get(key)
        if value is None or value == "":
            continue
        parts.append(str(value).strip())
    return " | ".join(part for part in parts if part)


def _build_pair_prompt(
    a_id: str,
    b_id: str,
    record_a: dict[str, Any],
    record_b: dict[str, Any],
    exhaust_a: dict[str, Any] | None = None,
    exhaust_b: dict[str, Any] | None = None,
) -> str:
    return (
        "Paper A\n"
        "-------\n"
        f"{_paper_prompt_block(a_id, record_a, exhaust_a or {})}\n\n"
        "Paper B\n"
        "-------\n"
        f"{_paper_prompt_block(b_id, record_b, exhaust_b or {})}\n"
    )


def _analyze_pair(
    a_id: str,
    b_id: str,
    record_a: dict[str, Any],
    record_b: dict[str, Any],
    pair_scope: str,
    llm: LLMClient | None,
    schema: dict[str, Any],
    *,
    exhaust_a: dict[str, Any] | None = None,
    exhaust_b: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if llm is None:
        raise ValueError("Substantive pair analysis requires an LLM or connect --from-file.")

    prompt = _build_pair_prompt(a_id, b_id, record_a, record_b, exhaust_a, exhaust_b)
    response = llm.complete(
        (
            "Analyze whether these two papers share a substantive structural connection.\n\n"
            + prompt
            + "\nUse claims, methods, equations, and exhaustion outputs as evidence. "
            + "Prioritize connections that depend on derivations, missing angles, open questions, "
            + "unstated assumptions, experiments, or necessary connections. "
            + "If no connection exists return {}."
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
    payload["status"] = "pending_review"
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
