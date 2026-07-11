"""Rubedo review skill: adversarial gate checks for one hypothesis."""

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
    int_or_default,
    ordered_gaps,
    paper_ids,
    project_root,
    require_hypothesis,
    run_optional_vigil,
)
from .triage import run_triage


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Review a Rubedo hypothesis for promotion readiness.")
    parser.add_argument("cluster_id", help="Hypothesis cluster id.")
    return parser


def run_review(cluster_id: str, *, config: Config | None = None) -> Path:
    root = project_root(config)
    run_optional_vigil(root, "start", "review")

    _, hypothesis = require_hypothesis(root, cluster_id)
    triage_path = run_triage(cluster_id, config=config)
    ids = paper_ids(hypothesis)
    library = collect_library(root, ids)
    exhaustion = collect_exhaustion(root, ids)
    connections = collect_connections(root, ids)

    checks = _run_checks(hypothesis, ids, library, exhaustion, connections)
    blocking = [check["detail"] for check in checks if check["status"] == "fail"]
    warnings = [check["detail"] for check in checks if check["status"] == "warn"]
    recommended = "rejected" if blocking else ("needs_prior_art" if warnings else "pending_review")

    payload = {
        "schema_version": 1,
        "artifact_type": "rubedo_review",
        "cluster_id": cluster_id,
        "status": "pending_review",
        "generated_at": now_iso(),
        "triage_path": str(triage_path.relative_to(root)) if triage_path.is_relative_to(root) else str(triage_path),
        "hypothesis_status": hypothesis.get("status", "unknown"),
        "checks": checks,
        "blocking_issues": blocking,
        "warnings": warnings,
        "recommended_decision": recommended,
        "agent_notes": (
            "Rule-based review only. External novelty and citation search remain required "
            "before accepting any hypothesis."
        ),
    }

    out_path = root / "rubedo" / "reviews" / f"{cluster_id}_review.yaml"
    write_yaml(out_path, payload)
    run_optional_vigil(root, "verify", "review")
    return out_path


def _run_checks(
    hypothesis: dict[str, Any],
    ids: list[str],
    library: dict[str, dict[str, Any]],
    exhaustion: dict[str, dict[str, Any]],
    connections: list[dict[str, Any]],
) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []

    _add_check(
        checks,
        "hypothesis_status",
        "pass" if hypothesis.get("status") == "pending_review" else "warn",
        f"Hypothesis status is {hypothesis.get('status', 'unknown')}.",
    )
    _add_check(
        checks,
        "cluster_size",
        "pass" if len(ids) >= 3 else "fail",
        f"Cluster includes {len(ids)} paper(s); Rubedo clusters should have at least 3.",
    )
    missing_library = [paper_id for paper_id in ids if paper_id not in library]
    _add_check(
        checks,
        "library_records",
        "pass" if not missing_library else "fail",
        "All library records are present." if not missing_library else f"Missing library records: {', '.join(missing_library)}.",
    )
    missing_exhaustion = [paper_id for paper_id in ids if paper_id not in exhaustion]
    _add_check(
        checks,
        "exhaustion_records",
        "pass" if not missing_exhaustion else "warn",
        "All exhaustion records are present." if not missing_exhaustion else f"Missing exhaustion records: {', '.join(missing_exhaustion)}.",
    )
    _add_check(
        checks,
        "connection_support",
        "pass" if connections else "warn",
        f"Found {len(connections)} connection artifact(s) inside this cluster.",
    )

    gaps = ordered_gaps(hypothesis)
    _add_check(
        checks,
        "candidate_gaps",
        "pass" if gaps else "fail",
        f"Found {len(gaps)} candidate gap(s).",
    )
    for gap in gaps:
        rank = int_or_default(gap.get("rank"), 0)
        supporting = {str(item) for item in gap.get("supporting_papers", [])}
        outside = sorted(supporting.difference(ids))
        _add_check(
            checks,
            f"gap_{rank}_supporting_papers",
            "pass" if not outside else "fail",
            (
                f"Gap {rank} supporting papers are inside the cluster."
                if not outside
                else f"Gap {rank} references papers outside the cluster: {', '.join(outside)}."
            ),
        )
        confidence = int_or_default(gap.get("confidence"), 0)
        feasibility = int_or_default(gap.get("feasibility"), 0)
        _add_check(
            checks,
            f"gap_{rank}_scores",
            "pass" if 1 <= confidence <= 5 and 1 <= feasibility <= 5 else "fail",
            f"Gap {rank} confidence={confidence}, feasibility={feasibility}.",
        )
        approach = str(gap.get("suggested_approach", "")).strip()
        _add_check(
            checks,
            f"gap_{rank}_experiment_specificity",
            "pass" if _approach_is_specific(approach) else "warn",
            f"Gap {rank} suggested approach is {'specific enough for a pilot' if _approach_is_specific(approach) else 'too vague for direct execution'}.",
        )

    _add_check(
        checks,
        "prior_art_search",
        "warn",
        "External prior-art search has not been run; do not accept novelty yet.",
    )
    return checks


def _add_check(checks: list[dict[str, str]], name: str, status: str, detail: str) -> None:
    checks.append({"name": name, "status": status, "detail": detail})


def _approach_is_specific(approach: str) -> bool:
    if len(approach) < 80:
        return False
    lowered = approach.lower()
    verbs = ("ablation", "benchmark", "compare", "evaluate", "implement", "measure", "test", "train")
    return any(verb in lowered for verb in verbs)
