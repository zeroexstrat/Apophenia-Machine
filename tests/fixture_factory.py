"""Small synthetic artifact builders for isolated pipeline tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def write_yaml(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def registry_entry(
    paper_id: str,
    *,
    status: str = "exhausted",
    depth: int | None = 3,
    domain: str = "operations_research",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "paper_id": paper_id,
        "filename": f"{paper_id}.txt",
        "domain": domain,
        "domain_confidence": 1.0,
        "title": f"Synthetic study {paper_id}",
        "authors": ["Synthetic Author"],
        "year": 2026,
        "ingested": "2026-01-01T00:00:00Z",
        "exhausted_at_depth": depth,
        "connected": False,
        "detected": False,
        "drafted": False,
        "triaged": False,
        "status": status,
        "paths": {
            "library": f"albedo/library/{paper_id}.yaml",
            "exhaust": f"albedo/exhaust/{paper_id}_exhaust.yaml",
            "pdf": f"sources/{paper_id}.txt",
        },
        "processing_notes": [],
        "tags": list(tags or ["bounded_queue", "resource_allocation"]),
    }


def write_registry(root: Path, entries: list[dict[str, Any]]) -> Path:
    path = root / "albedo" / "registry.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in entries),
        encoding="utf-8",
    )
    return path


def write_library(
    root: Path,
    paper_id: str,
    *,
    explicit_targets: list[str] | None = None,
    domain: str = "operations_research",
) -> Path:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "id": paper_id,
        "source": {
            "title": f"Synthetic study {paper_id}",
            "authors": ["Synthetic Author"],
            "year": 2026,
            "path": f"sources/{paper_id}.txt",
        },
        "claims": [
            {
                "statement": "A bounded queue reduces worst-case scheduling delay.",
                "confidence": "demonstrated",
                "evidence": "Synthetic result table 1, row 2.",
            }
        ],
        "classification": {
            "primary_domain": domain,
            "secondary_domains": [],
            "tags": ["bounded_queue", "resource_allocation"],
        },
    }
    if explicit_targets:
        payload["connections_explicit"] = [
            {
                "target_paper": target,
                "relationship": "cites_as_background",
                "strength": 5,
            }
            for target in explicit_targets
        ]
    return write_yaml(root / "albedo" / "library" / f"{paper_id}.yaml", payload)


def write_exhaust(
    root: Path,
    paper_id: str,
    *,
    depth: int = 3,
    derivations: list[dict[str, Any]] | None = None,
    domain: str = "operations_research",
) -> Path:
    payload = {
        "exhaustion": {
            "paper_id": paper_id,
            "paper_title": f"Synthetic study {paper_id}",
            "domain": domain,
            "paper_type": "paper",
            "exhaustion_depth": depth,
            "schema_version": 2,
        },
        "derivations": list(
            derivations
            or [
                {
                    "statement": "The bounded queue also caps queued work in progress.",
                    "follows_from": "claim_1",
                    "source_claim": "claim_1",
                    "confidence": "derived",
                }
            ]
        ),
    }
    return write_yaml(root / "albedo" / "exhaust" / f"{paper_id}_exhaust.yaml", payload)


def write_connection(
    root: Path,
    a_id: str,
    b_id: str,
    **overrides: Any,
) -> Path:
    a_id, b_id = sorted((a_id, b_id))
    payload: dict[str, Any] = {
        "schema_version": 1,
        "pair_scope": "within_domain",
        "paper_a_id": a_id,
        "paper_b_id": b_id,
        "pair_domains": {
            "paper_a_domain": "operations_research",
            "paper_b_domain": "operations_research",
        },
        "connection_type": "complementary_techniques",
        "description": "The scheduling policy combines a bounded queue with staged allocation.",
        "evidence_a": "Synthetic claim 1 specifies the bounded queue invariant.",
        "evidence_b": "Synthetic claim 1 specifies the staged allocation rule.",
        "confidence": 4,
        "confidence_raw": 4,
        "novelty": "non-obvious",
        "significance": "The combined policy exposes a measurable delay-capacity tradeoff.",
        "status": "pending_review",
        "tags": ["bounded_queue", "resource_allocation"],
    }
    payload.update(overrides)
    if payload["pair_scope"] == "within_domain":
        path = root / "citrinitas" / "within_domain" / "operations_research" / f"{a_id}_{b_id}.yaml"
    else:
        path = root / "citrinitas" / "cross_domain" / f"{a_id}_{b_id}.yaml"
    return write_yaml(path, payload)


def write_hypothesis(
    root: Path,
    cluster_id: str,
    paper_ids: list[str],
    **overrides: Any,
) -> Path:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "cluster_id": cluster_id,
        "paper_ids": sorted(paper_ids),
        "scope": "operations_research",
        "novelty": False,
        "summary": "Synthetic queue policies leave one allocation question unresolved.",
        "status": "pending_review",
        "gaps": [
            {
                "gap_type": "missing_experiment",
                "description": "The synthetic records do not compare delay under demand shifts.",
                "novelty": False,
                "supporting_papers": sorted(paper_ids),
                "supporting_evidence": "Synthetic claims describe policies but no demand-shift comparison.",
                "significance": "The comparison would bound an operational failure mode.",
                "feasibility": 5,
                "suggested_approach": "Simulate both policies under a fixed three-regime demand trace.",
                "confidence": 4,
                "rank": 1,
                "references": ["Synthetic claim 1"],
            }
        ],
    }
    payload.update(overrides)
    return write_yaml(root / "rubedo" / "hypotheses" / f"{cluster_id}.yaml", payload)
