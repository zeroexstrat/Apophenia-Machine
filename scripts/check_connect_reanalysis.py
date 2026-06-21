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
        "source": {"title": "Looped World Models"},
        "claims": [{"statement": "Looped world models reuse computation for stable rollouts."}],
        "methods": [{"name": "spectral retention"}],
        "techniques": [{"name": "looped transformer"}],
    }
    record_b = {
        "source": {"title": "Power of Looped Transformers"},
        "claims": [{"statement": "Looped transformers improve reasoning via repeated layers."}],
        "methods": [{"name": "looped model analysis"}],
        "techniques": [{"name": "weight sharing"}],
    }
    exhaust_a = {
        "missing_angles": [
            {
                "angle": "Distribution-shift behavior of adaptive looped rollouts remains untested.",
            }
        ],
        "open_questions": [
            {
                "question": "Does early exit preserve latent dynamics under long-horizon rollouts?",
            }
        ],
    }
    exhaust_b = {
        "derivations": [
            {
                "statement": "A k-layer block looped L times has effective depth kL with k-layer parameter count.",
            }
        ],
        "necessary_connections": [
            {
                "work": "adaptive computation literature",
                "why_necessary": "It frames loop count as test-time compute allocation.",
            }
        ],
    }
    prompt = _build_pair_prompt(
        "loopedworldmodels_903887879",
        "powerofloopedtransformers_159603065",
        record_a,
        record_b,
        exhaust_a,
        exhaust_b,
    )
    _assert("Distribution-shift behavior" in prompt, "pair prompt includes missing angles from exhaust A")
    _assert("effective depth kL" in prompt, "pair prompt includes derivations from exhaust B")
    _assert("adaptive computation literature" in prompt, "pair prompt includes necessary connections from exhaust B")

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
