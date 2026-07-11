#!/usr/bin/env python3
"""Focused checks for Citrinitas exhaust-aware reanalysis."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from athanasor.skills.connect import (
    _append_analyzed,
    _build_pair_prompt,
    _load_analyzed,
    _should_skip_analyzed_pair,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"check failed: {message}")
    print(f"[ok] {message}")


def main() -> int:
    record_a = {
        "source": {"title": "Adaptive Queue Scheduling"},
        "claims": [{"statement": "Bounded queues reuse capacity while limiting scheduling delay."}],
        "methods": [{"name": "queue stability analysis"}],
        "techniques": [{"name": "adaptive capacity allocation"}],
    }
    record_b = {
        "source": {"title": "Threshold Routing for Resource Allocation"},
        "claims": [{"statement": "Threshold routing reduces overload through staged allocation."}],
        "methods": [{"name": "threshold policy analysis"}],
        "techniques": [{"name": "staged routing"}],
    }
    exhaust_a = {
        "missing_angles": [
            {
                "angle": "Demand-shift behavior of adaptive queue allocation remains untested.",
            }
        ],
        "open_questions": [
            {
                "question": "Does early release preserve service levels under sustained demand?",
            }
        ],
    }
    exhaust_b = {
        "derivations": [
            {
                "statement": "A staged policy with k queues and L review windows performs kL allocation checks.",
            }
        ],
        "necessary_connections": [
            {
                "work": "adaptive resource-allocation literature",
                "why_necessary": "It frames review frequency as an operating-capacity decision.",
            }
        ],
    }
    prompt = _build_pair_prompt(
        "synthetic_001",
        "synthetic_002",
        record_a,
        record_b,
        exhaust_a,
        exhaust_b,
    )
    _assert("Demand-shift behavior" in prompt, "pair prompt includes missing angles from exhaust A")
    _assert("kL allocation checks" in prompt, "pair prompt includes derivations from exhaust B")
    _assert("adaptive resource-allocation literature" in prompt, "pair prompt includes necessary connections from exhaust B")

    analyzed_path = Path("/tmp/azoth-connect-reanalysis.jsonl")
    analyzed_path.unlink(missing_ok=True)
    _append_analyzed(
        analyzed_path,
        "paper_a",
        "paper_b",
        paper_depths={"paper_a": 1, "paper_b": 1},
        reanalysis_reason="initial",
    )
    analyzed = _load_analyzed(analyzed_path)
    event = analyzed["paper_a::paper_b"]
    _assert(event["paper_depths"] == {"paper_a": 1, "paper_b": 1}, "analyzed events retain per-paper depths")
    _assert(
        _should_skip_analyzed_pair(
            event,
            {"paper_id": "paper_a", "exhausted_at_depth": 1},
            {"paper_id": "paper_b", "exhausted_at_depth": 1},
            reanalyze_depth_upgrades=True,
        ),
        "same-depth analyzed pair is skipped during depth-aware reanalysis",
    )
    _assert(
        not _should_skip_analyzed_pair(
            event,
            {"paper_id": "paper_a", "exhausted_at_depth": 3},
            {"paper_id": "paper_b", "exhausted_at_depth": 1},
            reanalyze_depth_upgrades=True,
        ),
        "depth-upgraded analyzed pair is eligible for reanalysis",
    )
    _assert(
        _should_skip_analyzed_pair(
            event,
            {"paper_id": "paper_a", "exhausted_at_depth": 3},
            {"paper_id": "paper_b", "exhausted_at_depth": 1},
            reanalyze_depth_upgrades=False,
        ),
        "analyzed pair is skipped without explicit reanalysis flag",
    )

    raw = [json.loads(line) for line in analyzed_path.read_text().splitlines()]
    _assert(raw[0]["reanalysis_reason"] == "initial", "analyzed event stores reanalysis reason")

    print("\nAll connect reanalysis checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
