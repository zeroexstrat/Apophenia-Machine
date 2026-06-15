"""Domain classification for SePratio."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Config
from .llm import LLMClient


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
    *,
    filename: str | None = None,
    context_text: str | None = None,
) -> Classification:
    del config
    title = (title or "").strip()
    abstract = (abstract or "").strip()
    filename = (filename or "").strip()
    context_text = (context_text or "").strip()

    classification_input = _build_classification_input(
        title=title,
        abstract=abstract,
        filename=filename,
        context_text=context_text,
    )
    heuristic_domain, heuristic_conf, heuristic_reasoning = _heuristic_domain(classification_input)

    if llm is None:
        return Classification(
            domain=heuristic_domain,
            confidence=heuristic_conf,
            reasoning=heuristic_reasoning,
        )

    snippet = classification_input[:5000]
    prompt = (
        "Classify this paper into exactly one domain: physics, ML, philosophy, "
        "neuroscience, mathematics, or unclassified.\n\n"
        f"Title: {title or '[none]'}\n"
        f"Filename: {filename or '[none]'}\n"
        f"Abstract: {abstract or '[none]'}\n\n"
        "Text snippet:\n"
        f"{snippet}\n\n"
        "Respond with JSON matching:\n"
        '{"domain": "<domain>", "confidence": <0.0-1.0>, "reasoning": "<one sentence>"}'
    )

    try:
        payload = llm.complete(prompt, structured=True, schema={"type": "object"}, retries=2)
    except Exception:
        payload = None

    if isinstance(payload, dict):
        domain = str(payload.get("domain", "unclassified")).strip()
        if domain not in DOMAINS:
            return Classification(
                domain=heuristic_domain,
                confidence=heuristic_conf,
                reasoning="LLM returned an invalid domain; heuristic fallback used.",
            )

        try:
            conf = float(payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.5
        conf = max(0.0, min(1.0, conf))
        reasoning = str(payload.get("reasoning", "No reasoning provided."))

        llm_choice = Classification(domain=domain, confidence=conf, reasoning=reasoning)
        return _merge_llm_and_heuristic(llm_choice, heuristic_domain, heuristic_conf, heuristic_reasoning)

    return Classification(
        domain=heuristic_domain,
        confidence=heuristic_conf,
        reasoning=f"LLM did not return structured output. {heuristic_reasoning}",
    )


def _merge_llm_and_heuristic(
    llm_choice: Classification,
    heuristic_domain: str,
    heuristic_confidence: float,
    heuristic_reasoning: str,
) -> Classification:
    # Prefer the LLM when it is confident or the heuristic is weak.
    if llm_choice.domain == "unclassified" and heuristic_domain != "unclassified" and heuristic_confidence >= 0.55:
        return Classification(
            domain=heuristic_domain,
            confidence=max(heuristic_confidence, llm_choice.confidence),
            reasoning=f"{heuristic_reasoning} Heuristic override: {llm_choice.reasoning}",
        )

    if llm_choice.confidence >= 0.75 or heuristic_domain == "unclassified":
        return llm_choice

    if heuristic_domain != "unclassified" and (
        llm_choice.domain == "unclassified"
        or heuristic_confidence >= 0.65
        or (heuristic_confidence > llm_choice.confidence + 0.15)
    ):
        return Classification(
            domain=heuristic_domain,
            confidence=max(heuristic_confidence, llm_choice.confidence),
            reasoning=f"{heuristic_reasoning} Heuristic override: {llm_choice.reasoning}",
        )

    return llm_choice


def _build_classification_input(
    *,
    title: str,
    abstract: str,
    filename: str,
    context_text: str,
) -> str:
    parts: list[str] = [part for part in (filename, title, abstract, context_text) if part.strip()]
    return "\n".join(parts)


def _heuristic_domain(classification_input: str) -> tuple[str, float, str]:
    text = _normalize_text(classification_input)
    if not text:
        return "unclassified", 0.15, "No classification signal present."

    scored = _score_by_domain(text)
    if not scored:
        return "unclassified", 0.15, "No domain patterns matched extracted text."

    sorted_scores = sorted(
        (
            (domain, score, cues)
            for domain, (score, cues) in scored.items()
        ),
        key=lambda item: item[1],
        reverse=True,
    )

    top_domain, top_score, top_cues = sorted_scores[0]
    second_score = sorted_scores[1][1] if len(sorted_scores) > 1 else 0.0

    if top_score < 0.60:
        return (
            "unclassified",
            round(max(0.15, 0.25 + top_score * 0.20), 3),
            f"Weak evidence for {top_domain}; score={top_score:.2f}.",
        )

    margin = top_score - second_score
    confidence = min(
        0.98,
        0.45 + min(top_score / 2.4, 1.0) * 0.45 + min(margin, 1.2) * 0.12,
    )
    reasoning = (
        f"Heuristic matched {top_domain} with scored cues ({top_score:.2f}). "
        f"Top cue terms: {top_cues}"
    )
    return top_domain, round(confidence, 3), reasoning


def _score_by_domain(text: str) -> dict[str, tuple[float, str]]:
    normalized = f" {text} "
    scores: dict[str, float] = {domain: 0.0 for domain in DOMAINS}
    cue_hits: dict[str, list[str]] = {domain: [] for domain in DOMAINS}

    rules = {
        "physics": [
            ("entanglement", 0.95),
            ("quantum", 0.95),
            ("qecc", 0.95),
            ("tqft", 0.85),
            ("hep th", 0.6),
            ("particle", 0.55),
            ("gravity", 0.5),
            ("entropy", 0.45),
            ("thermodynamic", 0.45),
            ("epr", 0.55),
            ("field theory", 0.65),
            ("department of physics", 0.75),
            ("free energy principle", 0.25),
            ("locc", 0.5),
            ("communication protocol", 0.35),
            ("quantization", 0.4),
            ("scattering", 0.3),
        ],
        "ML": [
            ("neural network", 0.95),
            ("neural", 0.85),
            ("transformer", 0.9),
            ("machine learning", 0.9),
            ("deep learning", 0.85),
            ("embedding", 0.65),
            ("reinforcement", 0.75),
            ("dataset", 0.5),
            ("training", 0.45),
            ("inference", 0.45),
            ("optimization", 0.45),
            ("model", 0.2),
        ],
        "mathematics": [
            ("nash equilibria", 1.0),
            ("undecidability", 0.95),
            ("theorem", 0.6),
            ("topology", 0.65),
            ("proof", 0.6),
            ("algebra", 0.45),
            ("manifold", 0.65),
            ("probability", 0.45),
            ("statistics", 0.4),
            ("department of mathematics", 0.95),
            ("equilibrium", 0.25),
            ("graph", 0.25),
            ("lemma", 0.45),
            ("corollary", 0.45),
            ("stochastic", 0.35),
        ],
        "neuroscience": [
            ("neuron", 0.9),
            ("synapse", 0.75),
            ("brain", 0.65),
            ("cortex", 0.6),
            ("cognitive", 0.45),
            ("fmri", 0.85),
            ("eeg", 0.8),
            ("behavior", 0.35),
            ("perception", 0.35),
            ("attention", 0.35),
            ("department of neuroscience", 0.9),
            ("free energy principle", 0.45),
            ("predictive coding", 0.6),
            ("active inference", 0.5),
        ],
        "philosophy": [
            ("phenomen", 0.9),
            ("epistemology", 0.85),
            ("metaphysics", 0.75),
            ("consciousness", 0.8),
            ("mind", 0.45),
            ("ethics", 0.6),
            ("ontology", 0.7),
            ("qualia", 0.9),
            ("intentional", 0.6),
            ("phenomenology", 0.9),
        ],
    }

    for domain, clues in rules.items():
        for clue, weight in clues:
            token = _normalize_text(clue)
            if f" {token} " in normalized:
                scores[domain] += weight
                cue_hits[domain].append(clue)

    return {
        domain: (scores[domain], ", ".join(cue_hits[domain][:4]))
        for domain in DOMAINS
        if scores[domain] > 0
    }


def _normalize_text(value: str) -> str:
    lowered = value.lower()
    lowered = lowered.replace("œ", "oe").replace("ﬁ", "fi")
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()
