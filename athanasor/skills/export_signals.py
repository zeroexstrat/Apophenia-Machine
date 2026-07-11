"""Export bounded Azoth candidate signals for Anastomosis staging."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


SOURCE_TYPES = ["connection_candidate", "hypothesis_candidate", "prior_art_seed"]
MAX_SIGNALS = 3


def build_export(project_root: Path, max_signals: int = MAX_SIGNALS) -> dict[str, Any]:
    """Build an azoth-signals v1 payload from a bounded artifact set."""
    if max_signals != MAX_SIGNALS:
        raise ValueError("The first azoth-signals experiment requires exactly 3 signals.")

    root = Path(project_root).expanduser().resolve()
    exported_at = _now_z()
    prior_path = _select_prior_art(root)
    prior = _load_yaml(prior_path)
    cluster_id = str(prior.get("cluster_id", prior_path.stem))
    hypothesis_path = _select_hypothesis(root, cluster_id)
    connection_path = _select_connection(root, cluster_id)

    signals = [
        _connection_signal(root, connection_path, _load_yaml(connection_path), exported_at),
        _hypothesis_signal(root, hypothesis_path, _load_yaml(hypothesis_path), exported_at),
        _prior_art_signal(root, prior_path, prior, exported_at),
    ]

    return {
        "schema_name": "azoth-signals",
        "schema_version": 1,
        "producer": "azoth",
        "producer_project_path": str(root),
        "producer_git_commit": _git_commit(root),
        "producer_dirty_state": _git_dirty_state(root),
        "exported_at": exported_at,
        "export_scope": {
            "mode": "bounded_experiment",
            "max_signals": max_signals,
            "source_types": list(SOURCE_TYPES),
        },
        "signals": signals,
    }


def write_export(project_root: Path, output_path: Path, max_signals: int = MAX_SIGNALS) -> Path:
    """Write an azoth-signals v1 payload to JSON."""
    payload = build_export(project_root, max_signals=max_signals)
    target = Path(output_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def _connection_signal(root: Path, path: Path, payload: dict[str, Any], created_at: str) -> dict[str, Any]:
    paper_a = str(payload.get("paper_a_id", "paper-a"))
    paper_b = str(payload.get("paper_b_id", "paper-b"))
    summary = _clean_text(payload.get("description")) or f"Connection candidate between {paper_a} and {paper_b}."
    return {
        "signal_id": f"azoth:connection_candidate:{path.stem}",
        "signal_type": "connection_candidate",
        "source_project": "azoth",
        "source_artifacts": [_repo_relative(root, path)],
        "summary": _shorten(summary),
        "evidence": _evidence(
            root,
            path,
            [
                ("description", payload.get("description")),
                ("evidence_a", payload.get("evidence_a")),
                ("evidence_b", payload.get("evidence_b")),
            ],
        ),
        "azoth_status": _clean_text(payload.get("status")) or "pending_review",
        "azoth_confidence": _coerce_confidence(payload.get("confidence")),
        "authority_label": "unverified",
        "review_status": "pending_review",
        "recommended_anastomosis_label": "inferred",
        "created_at": created_at,
    }


def _hypothesis_signal(root: Path, path: Path, payload: dict[str, Any], created_at: str) -> dict[str, Any]:
    cluster_id = str(payload.get("cluster_id", path.stem))
    first_gap = _first_dict(payload.get("gaps"))
    summary = _clean_text(payload.get("summary")) or _clean_text(first_gap.get("description")) or cluster_id
    confidence = first_gap.get("confidence", payload.get("confidence"))
    return {
        "signal_id": f"azoth:hypothesis_candidate:{cluster_id}",
        "signal_type": "hypothesis_candidate",
        "source_project": "azoth",
        "source_artifacts": [_repo_relative(root, path)],
        "summary": _shorten(summary),
        "evidence": _evidence(
            root,
            path,
            [
                ("summary", payload.get("summary")),
                ("gaps[0].supporting_evidence", first_gap.get("supporting_evidence")),
                ("gaps[0].description", first_gap.get("description")),
            ],
        ),
        "azoth_status": _clean_text(payload.get("status")) or "pending_review",
        "azoth_confidence": _coerce_confidence(confidence),
        "authority_label": "unverified",
        "review_status": "pending_review",
        "recommended_anastomosis_label": "speculative",
        "created_at": created_at,
    }


def _prior_art_signal(root: Path, path: Path, payload: dict[str, Any], created_at: str) -> dict[str, Any]:
    cluster_id = str(payload.get("cluster_id", path.stem))
    assessment = payload.get("assessment") if isinstance(payload.get("assessment"), dict) else {}
    first_source = _first_dict(payload.get("sources"))
    summary = (
        _clean_text(assessment.get("recommended_reframe"))
        or _clean_text(payload.get("claim_reviewed"))
        or f"Prior-art result for {cluster_id}."
    )
    return {
        "signal_id": f"azoth:prior_art_seed:{cluster_id}",
        "signal_type": "prior_art_seed",
        "source_project": "azoth",
        "source_artifacts": [_repo_relative(root, path)],
        "summary": _shorten(summary),
        "evidence": _evidence(
            root,
            path,
            [
                ("assessment.rationale", assessment.get("rationale")),
                ("assessment.recommended_reframe", assessment.get("recommended_reframe")),
                ("sources[0].finding", first_source.get("finding")),
            ],
        ),
        "azoth_status": _clean_text(payload.get("decision")) or _clean_text(payload.get("status")) or "pending_review",
        "azoth_confidence": _coerce_confidence(payload.get("confidence")),
        "authority_label": "unverified",
        "review_status": "pending_review",
        "recommended_anastomosis_label": "speculative",
        "created_at": created_at,
    }


def _select_prior_art(root: Path) -> Path:
    paths = sorted((root / "rubedo" / "prior_art").glob("*.yaml"))
    if not paths:
        raise FileNotFoundError("No prior-art YAML artifacts found under rubedo/prior_art.")
    return paths[0]


def _select_hypothesis(root: Path, cluster_id: str) -> Path:
    direct = root / "rubedo" / "hypotheses" / f"{cluster_id}.yaml"
    if direct.exists():
        return direct
    paths = sorted((root / "rubedo" / "hypotheses").glob("*.yaml"))
    if not paths:
        raise FileNotFoundError("No hypothesis YAML artifacts found under rubedo/hypotheses.")
    return paths[0]


def _select_connection(root: Path, cluster_id: str) -> Path:
    expected_stem = _connection_stem_from_cluster(cluster_id)
    if expected_stem:
        matches = sorted((root / "citrinitas").glob(f"**/{expected_stem}.yaml"))
        matches = [path for path in matches if "/reports/" not in path.as_posix()]
        if matches:
            return matches[0]

    candidates = [
        path
        for path in sorted((root / "citrinitas").glob("**/*.yaml"))
        if "/reports/" not in path.as_posix()
    ]
    if not candidates:
        raise FileNotFoundError("No connection YAML artifacts found under citrinitas.")
    return max(candidates, key=lambda path: (_coerce_confidence(_load_yaml(path).get("confidence")), str(path)))


def _connection_stem_from_cluster(cluster_id: str) -> str:
    stem = cluster_id.removeprefix("cluster_")
    parts = stem.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return stem


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML mapping in {path}")
    return payload


def _evidence(root: Path, path: Path, fields: list[tuple[str, Any]]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    artifact = _repo_relative(root, path)
    for field, value in fields:
        excerpt = _clean_text(value)
        if not excerpt:
            continue
        entries.append({"artifact": artifact, "field": field, "excerpt": _shorten(excerpt, limit=360)})
    if entries:
        return entries
    return [{"artifact": artifact, "field": "artifact", "excerpt": "Artifact exists for human review."}]


def _repo_relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _first_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return item
    return {}


def _coerce_confidence(value: Any) -> int:
    try:
        return max(1, min(5, int(value)))
    except (TypeError, ValueError):
        return 3


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _shorten(value: str, limit: int = 500) -> str:
    text = _clean_text(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git_commit(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or "unknown"


def _git_dirty_state(root: Path) -> str:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return "dirty" if result.stdout.strip() else "clean"
