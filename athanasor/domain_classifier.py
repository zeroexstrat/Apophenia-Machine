"""Domain classification for SePratio."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Config
from .llm import LLMClient, LLMUnavailableError


DOMAINS = ["physics", "ML", "philosophy", "neuroscience", "mathematics", "unclassified"]


@dataclass
class Classification:
    domain: str
    confidence: float
    reasoning: str


def classify(
    title: str,
    abstract: str | None,
    llm: LLMClient | None,
    config: Config,
) -> Classification:
    title = (title or "").strip()
    abstract = (abstract or "").strip()

    if llm is None:
        return Classification(domain="unclassified", confidence=0.42, reasoning="LLM unavailable.")

    snippet = (title + "\n" + abstract)[:4000]
    prompt = (
        "Classify this paper into exactly one domain: physics, ML, philosophy, "
        "neuroscience, mathematics, or unclassified.\n\n"
        f"Title: {title}\nAbstract: {abstract or '[none]'}\n\n"
        f"Text snippet:\n{snippet}\n\n"
        "Respond with JSON matching:\n"
        '{\"domain\": \"<domain>\", \"confidence\": <0.0-1.0>, \"reasoning\": \"<one sentence>\"}'
    )

    try:
        payload = llm.complete(prompt, structured=True, schema={"type": "object"}, retries=2)
    except Exception:
        payload = None
    if isinstance(payload, dict):
        domain = str(payload.get("domain", "unclassified")).strip()
        if domain not in DOMAINS:
            domain = _heuristic_domain(classification_input=title + " " + abstract)
        try:
            conf = float(payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.5
        conf = max(0.0, min(1.0, conf))
        reasoning = str(payload.get("reasoning", "No reasoning provided."))
        return Classification(domain=domain, confidence=conf, reasoning=reasoning)
    return Classification(
        domain=_heuristic_domain(classification_input=title + " " + abstract),
        confidence=0.5,
        reasoning="LLM did not return structured output.",
    )


def _heuristic_domain(classification_input: str) -> str:
    text = classification_input.lower()
    rules: list[tuple[str, list[str]]] = [
        ("physics", ["quantum", "particle", "field", "gravity", "entropy", "thermo", "condensed"]),
        ("mathematics", ["theorem", "proof", "topology", "probability", "statistical", "algebra"]),
        ("neuroscience", ["neuron", "fMRI", "cognitive", "brain", "behavior", "synapse"]),
        ("philosophy", ["epistemology", "phenomen", "mind", "ethic", "metaphys"]),
        ("ML", ["neural", "transformer", "model", "learning", "network", "embedding"]),
    ]
    for domain, tokens in rules:
        if any(token in text for token in tokens):
            return domain
    return "unclassified"
