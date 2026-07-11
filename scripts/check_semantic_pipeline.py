#!/usr/bin/env python3
"""Semantic checks for ingest/exhaust/checkpoint quality."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from athanasor.cli import _summarize_slice_outputs  # noqa: E402
from athanasor.config import Config  # noqa: E402
from athanasor.registry import Registry  # noqa: E402
from athanasor.skills.exhaust import _process_one  # noqa: E402
from athanasor.skills.ingest import _fallback_extraction  # noqa: E402


def _assert(condition: bool, label: str, failures: list[str]) -> None:
    if condition:
        print(f"[ok] {label}")
    else:
        failures.append(label)
        print(f"[fail] {label}")


class FakeLLM:
    def complete(self, prompt: str, **kwargs: Any) -> dict[str, list[dict[str, Any]]]:
        return {
            "derivations": [
                {
                    "content": "If prompt ordering changes measured accuracy, benchmark results imply a distribution over prompt formats rather than a single task score.",
                    "confidence": "likely",
                    "source": "claim_2",
                }
            ],
            "exercises": [
                {
                    "item": "Run the same few-shot task under five random demonstration orderings and report accuracy variance.",
                    "answer": "The variance estimates prompt sensitivity and should be compared against model-to-model differences.",
                    "difficulty": "standard",
                }
            ],
            "missing_angles": [
                {
                    "item": "The paper does not isolate whether gains come from task inference, memorized templates, or label-space narrowing.",
                    "why": "The reported setup evaluates aggregate accuracy rather than mechanism.",
                    "impact": "A mechanism split would change which architectural interventions are justified.",
                }
            ],
            "open_questions": [
                {
                    "item": "Which prompt perturbations preserve task semantics while changing in-context learning performance?",
                    "can_close": True,
                    "closure": "Run controlled paraphrase, ordering, and label-name perturbation suites.",
                }
            ],
            "unstated_assumptions": [
                {
                    "item": "The examples in the prompt are treated as task evidence rather than noise.",
                    "impacts": "claim_1",
                }
            ],
            "experiments": [
                {
                    "content": "Prompt-order ablation",
                    "method": "Evaluate identical examples under random permutations and measure variance.",
                    "success": "Accuracy remains stable across permutations.",
                    "failure": "Accuracy varies enough to change model ranking.",
                }
            ],
            "necessary_connections": [
                {
                    "title": "Scaling laws for neural language models",
                    "rationale": "The claim that size improves few-shot behavior depends on scaling-law framing.",
                    "consequence": "It separates predictable scale effects from emergent prompt behavior.",
                }
            ],
        }


class FakeStore:
    size = 0

    def add(self, key: str, text: str) -> None:
        return None

    def search(self, text: str, top_k: int = 25) -> list[tuple[str, float]]:
        return []


def _config(root: Path) -> Config:
    return Config(
        llm={"max_tokens": 4096},
        embeddings={"redundancy_threshold": 0.99},
        paths={
            "project_root": str(root),
            "nigredo": "nigredo",
            "albedo": "albedo",
            "citrinitas": "citrinitas",
            "rubedo": "rubedo",
            "athanasor": "athanasor",
        },
        domains=["ML"],
        exhaustion={
            "depth_multipliers": {1: 2, 2: 4, 3: 6, 4: 8, 5: 12},
            "batch_size": 3,
            "llm_max_tokens": 384,
            "redundancy_stop_threshold": 3,
            "speculative_stop_count": 5,
        },
        project_root=str(root),
    )


def _schema() -> dict[str, Any]:
    with open(ROOT / "EXHAUST_SCHEMA.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _check_fallback_extraction(failures: list[str]) -> None:
    parsed = {
        "abstract": None,
        "full_text": """
        Abstract
        We introduce a sparse attention transformer that reduces quadratic attention cost while preserving long-context retrieval accuracy.
        The method uses block-sparse routing and a learned retrieval gate.
        We demonstrate lower memory usage on long-document classification.
        The training objective is L = - sum_i log p(x_i | x_<i).
        """,
    }
    payload = _fallback_extraction(
        parsed=parsed,
        path=Path("rich.pdf"),
        title="Sparse Attention Transformers for Long Documents",
        authors=["A. Researcher"],
        year=2026,
    )

    claims = payload.get("claims", [])
    methods = payload.get("methods", [])
    equations = payload.get("equations", [])
    claim_text = " ".join(str(item.get("statement", "")) for item in claims)
    method_text = " ".join(str(item.get("name", "")) for item in methods)

    _assert(len(claims) >= 2, "fallback ingest extracts multiple concrete claims", failures)
    _assert("Automated ingest found content" not in claim_text, "fallback ingest avoids generic claim when text is rich", failures)
    _assert("sparse attention" in claim_text.lower(), "fallback claims preserve paper concepts", failures)
    _assert("attention" in method_text.lower() or "routing" in method_text.lower(), "fallback ingest extracts methods", failures)
    _assert(len(equations) >= 1, "fallback ingest extracts equation-like text", failures)


def _check_exhaust_aliases(failures: list[str]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="azoth-semantic-") as tmp:
        root = Path(tmp)
        library = root / "albedo" / "library"
        exhaust = root / "albedo" / "exhaust"
        library.mkdir(parents=True)
        exhaust.mkdir(parents=True)
        (root / "albedo").mkdir(exist_ok=True)

        paper_id = "semantic_000000001"
        record = {
            "schema_version": 1,
            "id": paper_id,
            "source": {"title": "Prompt Sensitivity in Few-Shot Learning"},
            "claims": [
                {
                    "statement": "Prompt ordering changes measured few-shot accuracy.",
                    "confidence": "demonstrated",
                    "evidence": "Ablation table.",
                },
                {
                    "statement": "Larger models improve few-shot performance without inference-time gradient updates.",
                    "confidence": "demonstrated",
                    "evidence": "Scaling experiments.",
                },
            ],
            "methods": [
                {
                    "name": "few-shot prompt evaluation",
                    "description": "Evaluate tasks by conditioning on examples in the context window.",
                    "domain": "ML",
                }
            ],
            "techniques": [
                {
                    "name": "transformer self-attention",
                    "description": "Computes contextual token representations.",
                }
            ],
            "equations": [
                {
                    "label": "cross_entropy",
                    "expression": "L = - sum_i log p(x_i | x_<i)",
                    "context": "Autoregressive language modeling objective.",
                }
            ],
            "tags": ["few-shot-learning", "prompting", "transformers"],
        }
        with open(library / f"{paper_id}.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(record, f, sort_keys=False)

        registry = Registry(root / "albedo" / "registry.jsonl")
        registry.add(
            {
                "paper_id": paper_id,
                "domain": "ML",
                "status": "ingested_only",
                "exhausted_at_depth": None,
                "source": {"page_count": 1},
                "paths": {
                    "library": f"albedo/library/{paper_id}.yaml",
                    "exhaust": f"albedo/exhaust/{paper_id}_exhaust.yaml",
                },
            }
        )

        payload = _process_one(
            paper_id=paper_id,
            registry_entry=registry.get(paper_id) or {},
            library_root=library,
            exhaust_root=exhaust,
            depth=3,
            llm=FakeLLM(),
            schema=_schema(),
            store=FakeStore(),
            config=_config(root),
            registry=registry,
        )
        if payload is None:
            payload = {}

        _assert(len(payload.get("derivations", [])) >= 1, "exhaust keeps aliased derivations", failures)
        _assert(len(payload.get("exercises", [])) >= 1, "exhaust keeps aliased exercises", failures)
        _assert(len(payload.get("missing_angles", [])) >= 1, "exhaust keeps aliased missing angles", failures)
        _assert(len(payload.get("open_questions", [])) >= 1, "exhaust keeps aliased open questions", failures)
        _assert(len(payload.get("unstated_assumptions", [])) >= 1, "exhaust keeps aliased assumptions", failures)
        _assert(len(payload.get("experiments", [])) >= 1, "exhaust keeps aliased experiments", failures)
        _assert(len(payload.get("necessary_connections", [])) >= 1, "exhaust keeps aliased connections", failures)

        first_angle = (payload.get("missing_angles") or [{}])[0].get("angle", "")
        _assert("label-space" in first_angle or "task inference" in first_angle, "normalized missing angle has concrete text", failures)
        return payload


def _check_checkpoint_summary(payload: dict[str, Any], failures: list[str]) -> None:
    findings = _summarize_slice_outputs("azoth exhaust", [payload])
    joined = "\n".join(findings)
    _assert("semantic_000000001" in joined, "checkpoint summary includes nested paper id", failures)
    _assert("missing_angles=1" in joined, "checkpoint summary includes bucket counts", failures)
    _assert("Direction:" in joined, "checkpoint summary stores possible next direction", failures)


def main() -> int:
    failures: list[str] = []
    _check_fallback_extraction(failures)
    payload = _check_exhaust_aliases(failures)
    _check_checkpoint_summary(payload, failures)

    if failures:
        print("\nFailed checks:")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print("\nAll semantic pipeline checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
