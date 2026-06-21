"""Rubedo promote skill: record a human triage decision for a hypothesis."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..config import Config
from ..registry import Registry
from ..skills.common import now_iso, write_yaml
from .rubedo_common import paper_ids, project_root, require_hypothesis, run_optional_vigil


VALID_DECISIONS = {"accepted", "rejected", "needs_prior_art"}


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record a human Rubedo decision.")
    parser.add_argument("cluster_id", help="Hypothesis cluster id.")
    parser.add_argument("--decision", choices=sorted(VALID_DECISIONS), required=True)
    parser.add_argument("--reviewer", required=True, help="Human reviewer name or handle.")
    parser.add_argument("--note", required=True, help="Decision rationale.")
    return parser


def run_promote(
    cluster_id: str,
    *,
    decision: str,
    reviewer: str,
    note: str,
    config: Config | None = None,
) -> Path:
    if decision not in VALID_DECISIONS:
        raise ValueError(f"Invalid decision: {decision}")
    if not reviewer.strip():
        raise ValueError("reviewer is required")
    if not note.strip():
        raise ValueError("note is required")

    root = project_root(config)
    run_optional_vigil(root, "start", "promote")

    path, hypothesis = require_hypothesis(root, cluster_id)
    status_after = _status_for_decision(decision)
    timestamp = now_iso()
    hypothesis["status"] = status_after
    hypothesis["triage"] = {
        "decision": decision,
        "status_after": status_after,
        "reviewer": reviewer.strip(),
        "note": note.strip(),
        "reviewed_at": timestamp,
        "command": "azoth promote",
    }
    write_yaml(path, hypothesis)
    _mark_registry_triaged(root, paper_ids(hypothesis), decision, timestamp)
    run_optional_vigil(root, "verify", "promote")
    return path


def _status_for_decision(decision: str) -> str:
    if decision == "needs_prior_art":
        return "investigate"
    return decision


def _mark_registry_triaged(root: Path, ids: list[str], decision: str, timestamp: str) -> None:
    registry_path = root / "albedo" / "registry.jsonl"
    if not registry_path.exists():
        return
    registry = Registry(registry_path)
    for paper_id in ids:
        try:
            registry.update(
                paper_id,
                {
                    "triaged": True,
                    "last_triage": {
                        "decision": decision,
                        "reviewed_at": timestamp,
                    },
                },
            )
        except KeyError:
            continue
