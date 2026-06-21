#!/usr/bin/env python3
"""Checks that generated artifacts stay candidates until human triage."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from athanasor.skills.connect import _normalize_connection


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

    print("\nAll human gate contract checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
