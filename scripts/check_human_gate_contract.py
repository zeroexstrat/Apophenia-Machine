#!/usr/bin/env python3
"""Checks that generated artifacts stay candidates until human triage."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from athanasor.skills.connect import _normalize_connection
from athanasor.skills.detect import _synthesize_cluster


class _FakeDetectLLM:
    def complete(self, *args, **kwargs):
        return {
            "schema_version": 1,
            "cluster_id": "ignored",
            "paper_ids": ["paper_a", "paper_b", "paper_c"],
            "scope": "ML",
            "novelty": True,
            "summary": "Generated candidate hypothesis.",
            "status": "investigate",
            "gaps": [
                {
                    "gap_type": "unexplored_question",
                    "description": "A generated gap that still requires human review.",
                    "novelty": True,
                    "supporting_papers": ["paper_a", "paper_b", "paper_c"],
                    "supporting_evidence": "Generated evidence.",
                    "significance": "Generated significance.",
                    "feasibility": 4,
                    "suggested_approach": "Generated approach.",
                    "confidence": 4,
                }
            ],
        }


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"check failed: {message}")
    print(f"[ok] {message}")


def main() -> int:
    payload = {
        "paper_a_id": "a",
        "paper_b_id": "b",
        "connection_type": "analogous_structure",
        "description": "Generated candidate.",
        "evidence_a": "A",
        "evidence_b": "B",
        "confidence": 4,
        "novelty": "non-obvious",
        "significance": "Review required.",
        "status": "accepted",
    }
    normalized = _normalize_connection(payload, Path("citrinitas/within_domain/ML/a_b.yaml"))
    _assert(normalized["status"] == "pending_review", "generated connection status is forced to pending_review")

    records = [
        {"id": "paper_a", "source": {"title": "Paper A"}},
        {"id": "paper_b", "source": {"title": "Paper B"}},
        {"id": "paper_c", "source": {"title": "Paper C"}},
    ]
    hypothesis = _synthesize_cluster(
        cluster_id="cluster_paper_a_paper_b_3",
        paper_records=records,
        connections=[],
        exhaustion_records=[],
        domain="ML",
        cross=None,
        llm=_FakeDetectLLM(),
        schema={},
    )
    _assert(hypothesis["status"] == "pending_review", "generated hypothesis status is forced to pending_review")

    print("\nAll human gate contract checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
