#!/usr/bin/env python3
"""Focused checks for Citrinitas pair pruning."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from athanasor.skills.connect import _has_shared_tags, _shared_tags, _should_analyze_pair


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"check failed: {message}")
    print(f"[ok] {message}")


def main() -> int:
    strong_a = {
        "paper_id": "a",
        "tags": ["fallback", "mixture_of_experts", "latent_moe", "speculative_decoding"],
    }
    strong_b = {
        "paper_id": "b",
        "tags": ["ingested", "latent_moe", "mixture_of_experts", "multi_token_prediction"],
    }
    generic_a = {"paper_id": "c", "tags": ["ingested", "fallback"]}
    generic_b = {"paper_id": "d", "tags": ["fallback", "ingested"]}
    weak_a = {"paper_id": "e", "tags": ["inference_throughput", "long_context"]}
    weak_b = {"paper_id": "f", "tags": ["inference_throughput", "fp8_training"]}
    world_model_a = {"paper_id": "g", "tags": ["world_model", "sparse_computation"]}
    world_model_b = {"paper_id": "h", "tags": ["world_model", "adaptive_computation"]}

    _assert(_shared_tags(strong_a, strong_b) == {"latent_moe", "mixture_of_experts"}, "shared tags ignore generic fallback tags")
    _assert(_has_shared_tags(strong_a, strong_b), "meaningful tag overlap creates a candidate pair")
    _assert(not _has_shared_tags(generic_a, generic_b), "generic-only tag overlap is pruned")
    _assert(
        _should_analyze_pair(strong_a, strong_b, similarity=0.0, similarity_threshold=0.82),
        "strong tag overlap bypasses low embedding similarity",
    )
    _assert(
        not _should_analyze_pair(weak_a, weak_b, similarity=0.0, similarity_threshold=0.82),
        "single weak shared tag still needs embedding similarity",
    )
    _assert(
        _should_analyze_pair(world_model_a, world_model_b, similarity=0.0, similarity_threshold=0.82),
        "single high-signal shared tag bypasses low embedding similarity",
    )
    _assert(
        _should_analyze_pair(weak_a, weak_b, similarity=0.91, similarity_threshold=0.82),
        "high embedding similarity still permits weak shared tags",
    )

    print("\nAll connection pruning checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
