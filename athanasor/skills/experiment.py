"""Rubedo experiment skill: convert a candidate gap into a pilot spec."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from ..config import Config
from ..skills.common import now_iso, write_yaml
from .rubedo_common import paper_ids, project_root, require_hypothesis, run_optional_vigil, select_gap


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate an experiment spec from a Rubedo gap.")
    parser.add_argument("cluster_id", help="Hypothesis cluster id.")
    parser.add_argument("--gap-rank", type=int, default=1, help="Ranked gap to convert.")
    return parser


def run_experiment(cluster_id: str, *, gap_rank: int = 1, config: Config | None = None) -> Path:
    root = project_root(config)
    run_optional_vigil(root, "start", "experiment")

    _, hypothesis = require_hypothesis(root, cluster_id)
    gap = select_gap(hypothesis, gap_rank)
    approach = str(gap.get("suggested_approach", "")).strip()
    description = str(gap.get("description", "")).strip()
    benchmarks = _extract_parenthetical_examples(approach)

    payload = {
        "schema_version": 1,
        "artifact_type": "rubedo_experiment",
        "cluster_id": cluster_id,
        "gap_rank": gap_rank,
        "status": "pending_review",
        "generated_at": now_iso(),
        "paper_ids": paper_ids(hypothesis),
        "gap_type": gap.get("gap_type"),
        "hypothesis": description,
        "rationale": gap.get("significance", ""),
        "baseline": _baseline_for(gap),
        "intervention": approach or "Define a concrete intervention before execution.",
        "variables": {
            "independent": ["constraint_or_method_variant", "loop_depth_or_iteration_budget"],
            "dependent": ["task_performance", "training_stability", "compute_cost"],
            "controls": ["model_size", "dataset", "training_tokens_or_steps", "optimizer", "random_seed"],
        },
        "datasets_or_benchmarks": benchmarks or ["pilot_benchmark_to_select"],
        "metrics": [
            "primary_task_metric",
            "loss_curve_stability",
            "gradient_norm_or_update_norm",
            "wall_clock_or_token_cost",
        ],
        "protocol_steps": [
            "Implement the baseline exactly as described in the strongest supporting paper.",
            "Implement the intervention while changing only the target mechanism.",
            "Run at least three seeds on a small benchmark slice before scaling.",
            "Compare final performance, instability events, and compute-normalized performance.",
            "Record whether the result supports, weakens, or falsifies the proposed connection.",
        ],
        "compute_budget": {
            "scale": "pilot",
            "notes": "Start with the smallest benchmark slice that can expose instability or transfer failure.",
        },
        "stop_criteria": [
            "Stop if the intervention cannot reproduce baseline quality within the pilot budget.",
            "Stop if instability is not measurable with the selected benchmark.",
            "Promote to a larger run only after the pilot improves either stability or compute-normalized performance.",
        ],
        "expected_if_true": "The intervention improves stability or compute-normalized performance as loop depth or iteration budget increases.",
        "expected_if_false": "The intervention adds constraint overhead without improving stability, performance, or scaling behavior.",
        "failure_modes": [
            "The gap is already solved by prior art not represented in the current cluster.",
            "The proposed mechanisms are only superficially analogous.",
            "The benchmark is too small to expose the claimed stability difference.",
        ],
        "source_gap": gap,
    }

    out_path = root / "rubedo" / "experiments" / f"{cluster_id}_gap{gap_rank}_experiment.yaml"
    write_yaml(out_path, payload)
    run_optional_vigil(root, "verify", "experiment")
    return out_path


def _baseline_for(gap: dict[str, Any]) -> str:
    supporting = ", ".join(str(item) for item in gap.get("supporting_papers", []))
    if supporting:
        return f"Reproduce the most direct baseline from: {supporting}."
    return "Reproduce the most direct baseline from the supporting papers."


def _extract_parenthetical_examples(text: str) -> list[str]:
    matches = re.findall(r"\((?:e\.g\.,|e\.g\.|for example)\s*([^)]*)\)", text, flags=re.IGNORECASE)
    out: list[str] = []
    for match in matches:
        for item in re.split(r",|/|;", match):
            cleaned = item.strip()
            if cleaned:
                out.append(cleaned)
    return out[:8]
