#!/usr/bin/env python3
"""Machine checks for LLM provider routing."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from athanasor.config import Config, load_config  # noqa: E402
from athanasor.llm import LLMClient  # noqa: E402


def _assert(condition: bool, label: str, failures: list[str]) -> None:
    if condition:
        print(f"[ok] {label}")
    else:
        failures.append(label)
        print(f"[fail] {label}")


class _FakeResponse(io.BytesIO):
    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


def _fake_urlopen_factory(calls: list[dict[str, Any]]):
    def _fake_urlopen(request: Any, timeout: float | None = None) -> _FakeResponse:
        body = json.loads(request.data.decode("utf-8"))
        calls.append(
            {
                "url": request.full_url,
                "headers": dict(request.header_items()),
                "timeout": timeout,
                "body": body,
            }
        )
        payload = {
            "model": body["model"],
            "message": {"role": "assistant", "content": "{\"ok\": true}"},
            "prompt_eval_count": 7,
            "eval_count": 3,
        }
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    return _fake_urlopen


def main() -> int:
    failures: list[str] = []

    cfg = load_config(path=ROOT / ".missing-test-config.yaml")
    _assert(cfg.llm.get("provider") == "ollama_native", "default provider is ollama_native", failures)
    _assert(cfg.llm.get("model") == "nemotron-3-super:cloud", "default model is Nemotron Super cloud", failures)
    _assert(cfg.llm.get("base_url") == "http://localhost:11434", "default Ollama native base URL has no /v1 suffix", failures)
    _assert(cfg.llm.get("think") is False, "default disables Nemotron thinking for machine JSON", failures)

    test_cfg = Config(
        llm={
            "provider": "ollama_native",
            "base_url": "http://localhost:11434/v1",
            "model": "nemotron-3-super:cloud",
            "api_key": "ollama",
            "temperature": 0.2,
            "max_tokens": 128,
            "think": False,
            "timeout": 12,
        },
        embeddings={},
        paths={},
        domains=[],
        exhaustion={},
        project_root=str(ROOT),
    )

    import athanasor.llm as llm_module

    calls: list[dict[str, Any]] = []
    original_urlopen = llm_module.request.urlopen
    llm_module.request.urlopen = _fake_urlopen_factory(calls)
    try:
        client = LLMClient(test_cfg)
        result = client.complete("Return JSON.", structured=True, schema={"type": "object"})
    finally:
        llm_module.request.urlopen = original_urlopen

    _assert(result == {"ok": True}, "ollama_native parses structured JSON responses", failures)
    _assert(len(calls) == 1, "ollama_native performs one HTTP call", failures)
    if calls:
        call = calls[0]
        body = call["body"]
        _assert(call["url"] == "http://localhost:11434/api/chat", "ollama_native uses /api/chat", failures)
        _assert(body.get("model") == "nemotron-3-super:cloud", "ollama_native sends configured model", failures)
        _assert(body.get("think") is False, "ollama_native sends think=false", failures)
        _assert(body.get("format") == "json", "structured ollama_native calls request JSON format", failures)
        _assert(body.get("options", {}).get("num_predict") == 128, "ollama_native maps max_tokens to num_predict", failures)
        _assert(call.get("timeout") == 12, "ollama_native applies configured timeout", failures)

    if failures:
        print("\nFailed checks:")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print("\nAll LLM provider checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
