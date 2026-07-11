"""Rubedo triage skill: build a human review packet for one hypothesis."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..config import Config
from ..skills.common import now_iso, write_yaml
from .rubedo_common import (
    collect_connections,
    collect_exhaustion,
    collect_library,
    evidence_table,
    linked_paths,
    ordered_gaps,
    paper_ids,
    project_root,
    require_hypothesis,
    run_optional_vigil,
)


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a Rubedo human-triage packet.")
    parser.add_argument("cluster_id", help="Hypothesis cluster id.")
    return parser


def run_triage(cluster_id: str, *, config: Config | None = None) -> Path:
    root = project_root(config)
    run_optional_vigil(root, "start", "triage")

    _, hypothesis = require_hypothesis(root, cluster_id)
    ids = paper_ids(hypothesis)
    library = collect_library(root, ids)
    exhaustion = collect_exhaustion(root, ids)
    connections = collect_connections(root, ids)

    payload = {
        "schema_version": 1,
        "artifact_type": "rubedo_triage",
        "cluster_id": cluster_id,
        "status": "pending_review",
        "generated_at": now_iso(),
        "hypothesis_status": hypothesis.get("status", "unknown"),
        "summary": hypothesis.get("summary", ""),
        "paper_ids": ids,
        "paper_count": len(ids),
        "connection_count": len(connections),
        "exhaustion_count": len(exhaustion),
        "candidate_gaps": [_gap_summary(gap) for gap in ordered_gaps(hypothesis)],
        "evidence_table": evidence_table(root, ids, library, exhaustion),
        "connections": [_connection_summary(item) for item in connections],
        "novelty_checklist": {
            "cluster_novelty_claim": bool(hypothesis.get("novelty")),
            "prior_art_search": "not_run",
            "citation_overlap_check": "not_implemented",
            "required_before_promotion": True,
            "notes": "This packet does not perform external literature search; it records what must be checked before human promotion.",
        },
        "decision_options": ["accepted", "rejected", "needs_prior_art"],
        "linked_artifacts": linked_paths(root, cluster_id),
    }

    out_path = root / "rubedo" / "triage" / f"{cluster_id}.yaml"
    write_yaml(out_path, payload)
    run_optional_vigil(root, "verify", "triage")
    return out_path


def _gap_summary(gap: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": gap.get("rank"),
        "gap_type": gap.get("gap_type"),
        "confidence": gap.get("confidence"),
        "feasibility": gap.get("feasibility"),
        "supporting_papers": gap.get("supporting_papers", []),
        "description": gap.get("description", ""),
        "supporting_evidence": gap.get("supporting_evidence", ""),
        "suggested_approach": gap.get("suggested_approach", ""),
        "review_state": "candidate",
    }


def _connection_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "file": item.get("file"),
        "paper_a_id": item.get("paper_a_id"),
        "paper_b_id": item.get("paper_b_id"),
        "connection_type": item.get("connection_type"),
        "confidence": item.get("confidence"),
        "novelty": item.get("novelty"),
        "status": item.get("status"),
        "description": item.get("description"),
        "evidence_a": item.get("evidence_a"),
        "evidence_b": item.get("evidence_b"),
    }
