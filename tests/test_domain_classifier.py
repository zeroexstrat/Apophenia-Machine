"""Domain classifier coverage, including the biology domain and open vocabulary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from athanasor.config import Config, load_config
from athanasor.domain_classifier import DOMAINS, classify


def _config(domains: list[str] | None = None) -> Config:
    return Config(
        llm={},
        paths={"project_root": "."},
        domains=domains if domains is not None else list(DOMAINS),
        embeddings={},
        exhaustion={},
        project_root=".",
    )


def test_biology_is_a_known_domain() -> None:
    assert "biology" in DOMAINS


def test_default_config_includes_biology(tmp_path: Path) -> None:
    cfg = load_config(path=tmp_path / "missing.yaml")
    assert "biology" in cfg.domains


def test_levin_basal_cognition_classifies_as_biology_without_llm() -> None:
    result = classify(
        title="Bioelectric signaling and morphogenesis in planarian regeneration",
        abstract=(
            "We study how bioelectric gradients across cell membranes guide anatomical "
            "pattern formation during regeneration, framing basal cognition in "
            "non-neural tissue as collective cellular decision making."
        ),
        llm=None,
        config=_config(),
        filename="levin_bioelectricity.pdf",
        context_text="morphogenesis regeneration bioelectric gene regulatory network",
    )
    assert result.domain == "biology"
    assert result.confidence >= 0.6
    assert result.proposed is False


def test_classifier_prompt_lists_configured_domains() -> None:
    """The LLM prompt must be driven by config.domains, not a hard-coded list."""
    captured: dict[str, str] = {}

    class PromptCapturingLLM:
        def complete(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
            captured["prompt"] = prompt
            return {"domain": "biology", "confidence": 0.9, "reasoning": "cells"}

    result = classify(
        title="A paper about cells",
        abstract="cells and organisms",
        llm=PromptCapturingLLM(),
        config=_config(["physics", "ML", "biology", "unclassified"]),
    )
    assert "biology" in captured["prompt"]
    assert result.domain == "biology"


def test_llm_can_propose_new_domain_marked_proposed() -> None:
    class ProposingLLM:
        def complete(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
            return {
                "domain": "chemistry",
                "confidence": 0.92,
                "reasoning": "reaction kinetics",
                "proposed": True,
            }

    result = classify(
        title="Reaction kinetics of catalytic surfaces",
        abstract="We measure turnover frequencies on catalytic surfaces.",
        llm=ProposingLLM(),
        config=_config(["physics", "ML", "biology", "unclassified"]),
    )
    assert result.domain == "chemistry"
    assert result.proposed is True


def test_low_confidence_proposed_domain_is_not_forced() -> None:
    """A weakly-proposed unknown domain should not override a real heuristic signal."""
    class WeakProposingLLM:
        def complete(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
            return {
                "domain": "astrology",
                "confidence": 0.2,
                "reasoning": "unsure",
                "proposed": True,
            }

    result = classify(
        title="Transformer attention for neural machine translation",
        abstract="We train a deep neural network with attention.",
        llm=WeakProposingLLM(),
        config=_config(["physics", "ML", "biology", "unclassified"]),
    )
    assert result.domain != "astrology"


def test_known_world_model_still_classifies_as_ml() -> None:
    """Regression: biology additions must not disturb the ML world-model heuristic."""
    result = classify(
        title="Looped World Models",
        abstract=None,
        llm=None,
        config=_config(),
        filename="Looped World Models.pdf",
        context_text=None,
    )
    assert result.domain == "ML"
