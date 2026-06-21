#!/usr/bin/env python3
"""Focused checks for the productized Rubedo review path."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from athanasor.config import Config
from athanasor.skills.experiment import run_experiment
from athanasor.skills.promote import run_promote
from athanasor.skills.review import run_review
from athanasor.skills.triage import run_triage


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"check failed: {message}")
    print(f"[ok] {message}")


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False)


def _read_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        payload = yaml.safe_load(f)
    if not isinstance(payload, dict):
        raise SystemExit(f"check failed: expected YAML object at {path}")
    return payload


def _config(root: Path) -> Config:
    return Config(
        project_root=root,
        paths={
            "project_root": str(root),
            "nigredo": "nigredo",
            "albedo": "albedo",
            "citrinitas": "citrinitas",
            "rubedo": "rubedo",
            "athanasor": "athanasor",
        },
        llm={},
        embeddings={"store_path": "athanasor/embeddings.store"},
        domains=["ML"],
        exhaustion={},
    )


def _build_fixture(root: Path) -> str:
    cluster_id = "cluster_alpha_beta_gamma_3"
    paper_ids = ["alpha", "beta", "gamma"]
    for paper_id in paper_ids:
        _write_yaml(
            root / "albedo" / "library" / f"{paper_id}.yaml",
            {
                "id": paper_id,
                "source": {"title": f"{paper_id.title()} Paper"},
                "classification": {"primary_domain": "ML", "tags": ["looped_systems", "stability"]},
                "claims": [
                    {
                        "claim": f"{paper_id} claim about stable iteration.",
                        "confidence": "demonstrated",
                    }
                ],
                "methods": [{"name": f"{paper_id} method", "description": "A fixture method."}],
            },
        )
        _write_yaml(
            root / "albedo" / "exhaust" / f"{paper_id}_exhaust.yaml",
            {
                "paper_id": paper_id,
                "depth": 3,
                "derivations": [{"statement": "Derived fixture result."}],
                "missing_angles": [{"angle": "Missing fixture angle."}],
                "experiments": [{"hypothesis": "Fixture experiment."}],
            },
        )

    _write_yaml(
        root / "citrinitas" / "within_domain" / "ML" / "alpha_beta.yaml",
        {
            "schema_version": 1,
            "pair_scope": "within_domain",
            "paper_a_id": "alpha",
            "paper_b_id": "beta",
            "connection_type": "analogous_structure",
            "description": "Both papers study stable looped updates.",
            "evidence_a": "alpha uses stable recurrence.",
            "evidence_b": "beta uses looped updates.",
            "confidence": 4,
            "confidence_raw": 4,
            "novelty": "non-obvious",
            "significance": "The relation can support transfer of constraints.",
            "status": "pending_review",
        },
    )
    _write_yaml(
        root / "rubedo" / "hypotheses" / f"{cluster_id}.yaml",
        {
            "schema_version": 1,
            "cluster_id": cluster_id,
            "paper_ids": paper_ids,
            "scope": "ML",
            "novelty": True,
            "summary": "A fixture cluster about stable looped systems.",
            "status": "pending_review",
            "gaps": [
                {
                    "rank": 1,
                    "gap_type": "missing_experiment",
                    "description": "No controlled comparison tests spectral and looped constraints together.",
                    "novelty": True,
                    "supporting_papers": ["alpha", "beta"],
                    "supporting_evidence": "alpha and beta each expose part of the method but no shared experiment.",
                    "significance": "The experiment would clarify whether the stability mechanism transfers.",
                    "feasibility": 4,
                    "suggested_approach": "Implement a controlled ablation, train baseline and constrained variants, and evaluate stability, task score, and compute cost.",
                    "confidence": 4,
                }
            ],
            "metadata": {"cluster_size": 3, "connection_count": 1},
        },
    )
    return cluster_id


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="azoth-rubedo-review-") as tmp:
        root = Path(tmp)
        cluster_id = _build_fixture(root)
        cfg = _config(root)

        triage_path = run_triage(cluster_id, config=cfg)
        _assert(triage_path.exists(), "triage artifact created")
        triage = _read_yaml(triage_path)
        _assert(triage["artifact_type"] == "rubedo_triage", "triage artifact typed")
        _assert(len(triage["evidence_table"]) == 3, "triage includes paper evidence table")
        _assert(len(triage["connections"]) == 1, "triage includes linked connection evidence")
        _assert(triage["novelty_checklist"]["prior_art_search"] == "not_run", "triage does not fake prior-art search")

        review_path = run_review(cluster_id, config=cfg)
        _assert(review_path.exists(), "review artifact created")
        review = _read_yaml(review_path)
        _assert(review["artifact_type"] == "rubedo_review", "review artifact typed")
        _assert(review["recommended_decision"] in {"pending_review", "needs_prior_art", "rejected"}, "review emits machine decision")
        _assert(any(item["name"] == "prior_art_search" for item in review["checks"]), "review includes prior-art check")

        experiment_path = run_experiment(cluster_id, config=cfg)
        _assert(experiment_path.exists(), "experiment artifact created")
        experiment = _read_yaml(experiment_path)
        _assert(experiment["artifact_type"] == "rubedo_experiment", "experiment artifact typed")
        _assert(experiment["status"] == "pending_review", "experiment remains candidate output")
        _assert("baseline" in experiment and "intervention" in experiment, "experiment has baseline and intervention")

        promoted_path = run_promote(
            cluster_id,
            decision="needs_prior_art",
            reviewer="regression",
            note="Fixture requires external novelty search.",
            config=cfg,
        )
        promoted = _read_yaml(promoted_path)
        _assert(promoted["status"] == "investigate", "needs_prior_art maps to schema-compatible investigate")
        _assert(promoted["triage"]["decision"] == "needs_prior_art", "promotion records human decision")

    print("\nRubedo review path checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
