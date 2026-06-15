"""LLM client abstraction for model-agnostic generation."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

from .config import Config

try:
    import openai
except Exception:  # pragma: no cover
    openai = None  # type: ignore


@dataclass
class LLMCallLog:
    timestamp: str
    model: str
    prompt_length: int
    response_length: int
    temperature: float
    usage: dict[str, Any] | None = None


class LLMUnavailableError(RuntimeError):
    pass


class LLMClient:
    """Thin wrapper around an OpenAI-compatible client."""

    def __init__(self, config: Config):
        self.config = config
        self.model = config.llm.get("model", "")
        self.base_url = config.llm.get("base_url", "")
        self.api_key = config.llm.get("api_key", "")
        self.temperature = float(config.llm.get("temperature", 0.3))
        self.max_tokens = int(config.llm.get("max_tokens", 2048))
        self.client = self._init_client()
        self.call_logs: list[LLMCallLog] = []

    def _init_client(self):
        if openai is None:
            return None
        if not self.base_url:
            return openai.OpenAI(api_key=self.api_key)  # type: ignore[attr-defined]
        return openai.OpenAI(  # type: ignore[attr-defined]
            base_url=self.base_url,
            api_key=self.api_key,
        )

    def is_available(self) -> bool:
        return self.client is not None

    def _truncate_middle(self, text: str, max_len: int = 24000) -> str:
        """Truncate from the middle to preserve prompt framing and task instruction."""
        if len(text) <= max_len:
            return text
        keep = max_len // 2 - 100
        if keep <= 0:
            return text[-max_len:]
        prefix = text[:keep]
        suffix = text[-(max_len - keep - 13) :]
        return f"{prefix}\n...[truncated]...\n{suffix}"

    def _json_payload(self, schema: dict[str, Any] | str | None, prompt: str, structured: bool) -> str:
        if not structured:
            return prompt
        if isinstance(schema, str):
            schema_hint = schema.strip()
        elif isinstance(schema, dict):
            schema_hint = json.dumps(schema, indent=2)
        else:
            schema_hint = "{}"
        return (
            f"{prompt}\n\nRespond ONLY with valid JSON matching this schema:\n"
            f"{schema_hint}"
        )

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        structured: bool = False,
        schema: dict[str, Any] | str | None = None,
        retries: int = 3,
        retry_parse_fail: bool = False,
    ) -> str | dict[str, Any]:
        if self.client is None:
            raise LLMUnavailableError("No LLM backend configured.")

        if structured:
            prompt = self._json_payload(schema, prompt, structured=True)

        temp = float(self.temperature if temperature is None else temperature)
        max_tokens = int(self.max_tokens if max_tokens is None else max_tokens)
        payload = self._truncate_middle(prompt)

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": payload})

        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                response = self.client.chat.completions.create(  # type: ignore[attr-defined]
                    model=self.model,
                    messages=messages,
                    temperature=temp,
                    max_tokens=max_tokens,
                )
                content = (response.choices[0].message.content or "").strip()
                usage = getattr(response, "usage", None)
                usage_payload = None
                if usage is not None:
                    usage_payload = {
                        "prompt_tokens": getattr(usage, "prompt_tokens", None),
                        "completion_tokens": getattr(usage, "completion_tokens", None),
                        "total_tokens": getattr(usage, "total_tokens", None),
                    }
                self.call_logs.append(
                    LLMCallLog(
                        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        model=self.model,
                        prompt_length=len(payload),
                        response_length=len(content),
                        temperature=temp,
                        usage=usage_payload,
                    )
                )

                if structured:
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError as exc:
                        last_exc = exc
                        if not retry_parse_fail or attempt >= retries:
                            return _attempt_parse_structured_text(content, schema)
                        # Retry with an explicit parser hint.
                        messages = [
                            {
                                "role": "system",
                                "content": "You previously returned malformed JSON. "
                                "Return only strict JSON now.",
                            },
                            {"role": "user", "content": payload},
                        ]
                        continue

                return content
            except Exception as exc:  # pragma: no cover
                last_exc = exc
                if attempt >= retries:
                    break
                delay = 0.5 * (2 ** (attempt - 1))
                time.sleep(delay)

        if isinstance(last_exc, Exception):
            raise LLMUnavailableError(f"LLM call failed: {last_exc}")
        raise LLMUnavailableError("LLM call failed without response.")

    def complete_with_fallback(
        self,
        prompt: str,
        *,
        fallback: str,
        **kwargs: Any,
    ) -> str:
        try:
            return self.complete(prompt, **kwargs)  # type: ignore[return-value]
        except LLMUnavailableError:
            return fallback


def _attempt_parse_structured_text(text: str, schema: dict[str, Any] | str | None) -> dict[str, Any]:
    """Try to salvage JSON from a potentially fenced/extra-text response."""
    if not text:
        return {}
    lowered = text.strip()

    # Extract fenced JSON.
    if "```" in lowered:
        for part in lowered.split("```"):
            stripped = part.strip()
            if not stripped:
                continue
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()
            if not stripped.startswith("{") and not stripped.startswith("["):
                continue
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                continue

    # Fallback to substring search.
    start = lowered.find("{")
    end = lowered.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(lowered[start : end + 1])
        except json.JSONDecodeError:
            pass

    if isinstance(schema, dict):
        return {key: None for key in schema.keys() if isinstance(key, str)}
    return {}

