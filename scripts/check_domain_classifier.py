#!/usr/bin/env python3
"""Focused checks for Separatio domain classification."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from athanasor.config import Config
from athanasor.domain_classifier import classify


def _config() -> Config:
    return Config(
        llm={},
        paths={"project_root": str(ROOT)},
        domains=["physics", "ML", "philosophy", "neuroscience", "mathematics", "unclassified"],
        embeddings={},
        exhaustion={},
        project_root=str(ROOT),
    )


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"check failed: {message}")
    print(f"[ok] {message}")


def main() -> int:
    title_only = classify(
        title="Looped World Models",
        abstract=None,
        llm=None,
        config=_config(),
        filename="Looped World Models.pdf",
        context_text=None,
    )
    _assert(title_only.domain == "ML", "world-model title alone classifies as ML")

    result = classify(
        title="Looped World Models",
        abstract=(
            "LoopWM uses looped transformers, adaptive computation, and latent "
            "dynamics for long-horizon world model rollouts in reinforcement learning."
        ),
        llm=None,
        config=_config(),
        filename="Looped World Models.pdf",
        context_text="world model architectures stable rollouts parameter efficiency",
    )

    _assert(result.domain == "ML", "world-model papers classify as ML without LLM")
    _assert(result.confidence >= 0.65, "world-model ML classification is high enough to override weak LLM output")

    print("\nAll domain classifier checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
