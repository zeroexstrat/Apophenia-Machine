"""Shared helpers for Rubedo review-path skills."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ..config import Config, load_config
from ..skills.common import run_vigil_check


def project_root(config: Config | None = None) -> Path:
    cfg = config or load_config()
    return Path(cfg.project_root).expanduser().resolve()


def run_optional_vigil(root: Path, phase: str, skill: str) -> None:
    verify_path = root / "athanasor" / "vigil" / "verify.py"
    if not verify_path.exists():
        return
    run_vigil_check(root=root, phase=phase, skill=skill)


def load_yaml(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        payload = yaml.safe_load(f)
    return payload if isinstance(payload, dict) else None


def hypothesis_path(root: Path, cluster_id: str) -> Path:
    return root / "rubedo" / "hypotheses" / f"{cluster_id}.yaml"


def require_hypothesis(root: Path, cluster_id: str) -> tuple[Path, dict[str, Any]]:
    path = hypothesis_path(root, cluster_id)
    payload = load_yaml(path)
    if payload is None:
        raise FileNotFoundError(f"Hypothesis not found: {path}")
    return path, payload


def paper_ids(hypothesis: dict[str, Any]) -> list[str]:
    return [
        str(item).strip()
        for item in hypothesis.get("paper_ids", [])
        if str(item).strip()
    ]


def ordered_gaps(hypothesis: dict[str, Any]) -> list[dict[str, Any]]:
    gaps = [gap for gap in hypothesis.get("gaps", []) if isinstance(gap, dict)]
    return sorted(gaps, key=lambda gap: int_or_default(gap.get("rank"), 999))


def select_gap(hypothesis: dict[str, Any], gap_rank: int = 1) -> dict[str, Any]:
    gaps = ordered_gaps(hypothesis)
    for gap in gaps:
        if int_or_default(gap.get("rank"), 0) == gap_rank:
            return gap
    if gaps and gap_rank == 1:
        return gaps[0]
    raise ValueError(f"No gap with rank {gap_rank}.")


def int_or_default(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def relpath(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def collect_library(root: Path, ids: list[str]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for paper_id in ids:
        path = root / "albedo" / "library" / f"{paper_id}.yaml"
        payload = load_yaml(path)
        if payload is not None:
            records[paper_id] = payload
    return records


def collect_exhaustion(root: Path, ids: list[str]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for paper_id in ids:
        path = root / "albedo" / "exhaust" / f"{paper_id}_exhaust.yaml"
        payload = load_yaml(path)
        if payload is not None:
            records[paper_id] = payload
    return records


def collect_connections(root: Path, ids: list[str]) -> list[dict[str, Any]]:
    wanted = set(ids)
    records: list[dict[str, Any]] = []
    for base in (root / "citrinitas" / "within_domain", root / "citrinitas" / "cross_domain"):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.yaml")):
            payload = load_yaml(path)
            if payload is None:
                continue
            a_id = str(payload.get("paper_a_id") or "").strip()
            b_id = str(payload.get("paper_b_id") or "").strip()
            if a_id in wanted and b_id in wanted:
                item = dict(payload)
                item["file"] = relpath(root, path)
                records.append(item)
    return records


def evidence_table(
    root: Path,
    ids: list[str],
    library: dict[str, dict[str, Any]],
    exhaustion: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for paper_id in ids:
        record = library.get(paper_id, {})
        source = record.get("source") if isinstance(record.get("source"), dict) else {}
        classification = record.get("classification") if isinstance(record.get("classification"), dict) else {}
        exhaust = exhaustion.get(paper_id, {})
        rows.append(
            {
                "paper_id": paper_id,
                "title": source.get("title") or record.get("title") or paper_id,
                "domain": classification.get("primary_domain") or record.get("domain") or "unknown",
                "tags": classification.get("tags") or record.get("tags") or [],
                "library_path": relpath(root, root / "albedo" / "library" / f"{paper_id}.yaml"),
                "exhaust_path": relpath(root, root / "albedo" / "exhaust" / f"{paper_id}_exhaust.yaml"),
                "claims": summarize_bucket(record.get("claims"), ("claim", "statement")),
                "methods": summarize_bucket(record.get("methods"), ("name", "description")),
                "exhaustion_counts": {
                    "derivations": bucket_count(exhaust, "derivations"),
                    "missing_angles": bucket_count(exhaust, "missing_angles"),
                    "open_questions": bucket_count(exhaust, "open_questions"),
                    "experiments": bucket_count(exhaust, "experiments"),
                    "necessary_connections": bucket_count(exhaust, "necessary_connections"),
                },
            }
        )
    return rows


def summarize_bucket(value: Any, keys: tuple[str, ...], limit: int = 3) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, dict):
            text = " - ".join(
                str(item.get(key, "")).strip()
                for key in keys
                if str(item.get(key, "")).strip()
            )
        else:
            text = str(item).strip()
        if text:
            out.append(text[:300])
        if len(out) >= limit:
            break
    return out


def bucket_count(payload: dict[str, Any], name: str) -> int:
    value = payload.get(name)
    return len(value) if isinstance(value, list) else 0


def linked_paths(root: Path, cluster_id: str) -> dict[str, str]:
    return {
        "hypothesis": relpath(root, hypothesis_path(root, cluster_id)),
        "triage": relpath(root, root / "rubedo" / "triage" / f"{cluster_id}.yaml"),
        "review": relpath(root, root / "rubedo" / "reviews" / f"{cluster_id}_review.yaml"),
        "experiment": relpath(root, root / "rubedo" / "experiments" / f"{cluster_id}_gap1_experiment.yaml"),
    }
