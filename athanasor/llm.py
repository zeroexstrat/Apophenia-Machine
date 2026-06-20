"""LLM client abstraction for model-agnostic generation."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, request

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


class _OllamaNativeClient:
    pass


class LLMClient:
    """Thin wrapper around configured LLM providers."""

    def __init__(self, config: Config):
        self.config = config
        self.provider = _normalize_provider(config.llm.get("provider", "openai_compatible"))
        self.model = config.llm.get("model", "")
        self.base_url = config.llm.get("base_url", "")
        self.api_key = config.llm.get("api_key", "")
        self.temperature = float(config.llm.get("temperature", 0.3))
        self.max_tokens = int(config.llm.get("max_tokens", 2048))
        self.think = bool(config.llm.get("think", False))
        self.timeout = float(config.llm.get("timeout", 300))
        self.client = self._init_client()
        self.call_logs: list[LLMCallLog] = []

    def _init_client(self):
        if self.provider == "ollama_native":
            return _OllamaNativeClient()
        if self.provider not in {"openai", "openai_compatible"}:
            return None
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

        if self.provider == "ollama_native":
            return self._complete_ollama_native(
                messages=messages,
                payload=payload,
                temp=temp,
                max_tokens=max_tokens,
                structured=structured,
                schema=schema,
                retries=retries,
                retry_parse_fail=retry_parse_fail,
            )

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

    def _complete_ollama_native(
        self,
        *,
        messages: list[dict[str, str]],
        payload: str,
        temp: float,
        max_tokens: int,
        structured: bool,
        schema: dict[str, Any] | str | None,
        retries: int,
        retry_parse_fail: bool,
    ) -> str | dict[str, Any]:
        last_exc: Exception | None = None
        current_messages = messages

        for attempt in range(1, retries + 1):
            try:
                response = self._ollama_native_chat(
                    messages=current_messages,
                    temperature=temp,
                    max_tokens=max_tokens,
                    structured=structured,
                )
                content = str(response.get("message", {}).get("content") or "").strip()
                prompt_tokens = response.get("prompt_eval_count")
                completion_tokens = response.get("eval_count")
                total_tokens = None
                if isinstance(prompt_tokens, int) and isinstance(completion_tokens, int):
                    total_tokens = prompt_tokens + completion_tokens

                self.call_logs.append(
                    LLMCallLog(
                        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        model=self.model,
                        prompt_length=len(payload),
                        response_length=len(content),
                        temperature=temp,
                        usage={
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                            "total_tokens": total_tokens,
                        },
                    )
                )

                if structured:
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError as exc:
                        last_exc = exc
                        if not retry_parse_fail or attempt >= retries:
                            return _attempt_parse_structured_text(content, schema)
                        current_messages = [
                            {
                                "role": "system",
                                "content": "You previously returned malformed JSON. Return only strict JSON now.",
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

    def _ollama_native_chat(
        self,
        *,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        structured: bool,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": self.think,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if structured:
            body["format"] = "json"

        req = request.Request(
            _ollama_chat_url(self.base_url),
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMUnavailableError(f"Ollama native call failed with HTTP {exc.code}: {detail}") from exc
        return json.loads(raw)

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


def _normalize_provider(value: Any) -> str:
    provider = str(value or "openai_compatible").strip().lower().replace("-", "_")
    if provider in {"ollama", "ollama_native"}:
        return "ollama_native"
    if provider in {"openai", "openai_compatible", "openai_compat"}:
        return "openai_compatible"
    return provider


def _ollama_chat_url(base_url: str) -> str:
    base = (base_url or "http://localhost:11434").rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    if base.endswith("/api"):
        base = base[:-4]
    return f"{base}/api/chat"
