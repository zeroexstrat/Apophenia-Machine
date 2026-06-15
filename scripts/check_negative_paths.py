#!/usr/bin/env python3
"""Negative-path hardening checks for validation + registry transitions."""

from __future__ import annotations

import tempfile
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from athanasor.registry import Registry
from athanasor.scripts.validate import validate_file


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f)


def _expect_validation_fail(path: Path, schema: Path, *, label: str) -> None:
    ok, errors, _ = validate_file(path, schema_path=schema, fix=False)
    if ok:
        raise SystemExit(f"Expected validation failure in {label}, but it passed.")
    if not errors:
        raise SystemExit(f"Expected validation details in {label}, but none were returned.")


def _run_registry_transition_check(root: Path) -> None:
    registry = Registry(root / "albedo" / "registry.jsonl")
    entry = {
        "paper_id": "test_000000001",
        "filename": "test.pdf",
        "domain": "unclassified",
        "domain_confidence": 0.75,
        "title": "Test paper",
        "authors": ["Test Author"],
        "year": 2024,
        "ingested": "2026-01-01T00:00:00Z",
        "status": "ingested_only",
        "paths": {
            "library": "albedo/library/test_000000001.yaml",
        },
    }
    registry.add(entry)
    # Valid transition: ingested_only -> exhausted
    registry.update("test_000000001", {"status": "exhausted"})

    # Invalid rollback: exhausted -> ingested_only should fail.
    try:
        registry.update("test_000000001", {"status": "ingested_only"})
    except ValueError:
        return
    raise SystemExit("Registry status regression was not rejected.")


def main() -> int:
    with tempfile.TemporaryDirectory() as workdir:
        root = Path(workdir)

        connect_invalid = root / "citrinitas" / "within_domain" / "bad.yaml"
        _write_yaml(
            connect_invalid,
            {
                "pair_scope": "within_domain",
                "paper_a_id": "p1",
                "paper_b_id": "p2",
                "connection_type": "complementary_techniques",
                "description": "Invalid confidence as text.",
                "evidence_a": "a",
                "evidence_b": "b",
                "confidence": "high",
                "novelty": "obvious",
                "significance": "manual review needed",
                "status": "pending_review",
            },
        )
        _expect_validation_fail(
            connect_invalid,
            ROOT / "CONNECT_SCHEMA.yaml",
            label="connect confidence as text",
        )

        detect_invalid = root / "rubedo" / "hypotheses" / "bad.yaml"
        _write_yaml(
            detect_invalid,
            {
                "cluster_id": "cluster_bad",
                "paper_ids": ["p1", "p2", "p3"],
                "novelty": "high",
                "summary": "Should fail because of invalid novelty and gap fields.",
                "status": "pending_review",
                "gaps": [
                    {
                        "gap_type": "unexplored_question",
                        "description": "Missing novel boolean and numeric confidence fields.",
                        "novelty": "maybe",
                        "supporting_papers": ["p1", "p2", "p3"],
                        "supporting_evidence": "N/A",
                        "significance": "N/A",
                        "feasibility": "high",
                        "suggested_approach": "N/A",
                        "confidence": "very high",
                    }
                ],
            },
        )
        _expect_validation_fail(
            detect_invalid,
            ROOT / "DETECT_SCHEMA.yaml",
            label="detect gap confidence format",
        )

        _run_registry_transition_check(root)

    print("Negative-path checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
