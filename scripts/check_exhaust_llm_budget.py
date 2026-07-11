#!/usr/bin/env python3
"""Machine checks for bounded exhaustion LLM calls."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from athanasor.skills.exhaust import _generate_batch  # noqa: E402


def _assert(condition: bool, label: str, failures: list[str]) -> None:
    if condition:
        print(f"[ok] {label}")
    else:
        failures.append(label)
        print(f"[fail] {label}")


class FakeLLM:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def complete(self, prompt: str, **kwargs: Any) -> dict[str, list[dict[str, str]]]:
        self.kwargs = kwargs
        return {
            "derivations": [
                {
                    "statement": "A bounded batch was generated.",
                    "confidence": "likely",
                    "source_claim": "claim_1",
                }
            ],
            "exercises": [],
            "missing_angles": [],
            "open_questions": [],
            "unstated_assumptions": [],
            "experiments": [],
            "necessary_connections": [],
        }


class EmptyLLM:
    def complete(self, prompt: str, **kwargs: Any) -> dict[str, list[dict[str, str]]]:
        return {
            "derivations": [],
            "exercises": [],
            "missing_angles": [],
            "open_questions": [],
            "unstated_assumptions": [],
            "experiments": [],
            "necessary_connections": [],
        }


def main() -> int:
    failures: list[str] = []
    fake = FakeLLM()
    result = _generate_batch("context", fake, batch_size=1, max_tokens=256)

    _assert(fake.kwargs.get("max_tokens") == 256, "exhaust forwards configured LLM max_tokens", failures)
    _assert(fake.kwargs.get("structured") is True, "exhaust requests structured output", failures)
    _assert(len(result.get("derivations", [])) == 1, "exhaust keeps generated derivation", failures)
    _assert(
        _generate_batch("context", EmptyLLM(), batch_size=1, max_tokens=256) == {},
        "exhaust treats all-empty LLM batches as no generated work",
        failures,
    )

    if failures:
        print("\nFailed checks:")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print("\nAll exhaust LLM budget checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
