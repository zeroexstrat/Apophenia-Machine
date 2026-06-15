"""Configuration loading for Azoth.

Defaults are kept in ``azoth.config.yaml`` at the project root.
Environment variables can override:
- ``LLM_BASE_URL``
- ``LLM_MODEL``
- ``LLM_API_KEY``
- ``AZOTH_PROJECT_ROOT``
"""

from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _project_root() -> Path:
    override = os.environ.get("AZOTH_PROJECT_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return PROJECT_ROOT.resolve()


@dataclass(frozen=True)
class Config:
    llm: dict[str, Any]
    embeddings: dict[str, Any]
    paths: dict[str, str]
    domains: list[str]
    exhaustion: dict[str, Any]
    project_root: str

    @property
    def resolved_paths(self) -> dict[str, Path]:
        root = Path(self.project_root).expanduser().resolve()
        return {
            key: root / value
            for key, value in self.paths.items()
            if isinstance(value, str)
        }


def _default_config() -> dict[str, Any]:
    return {
        "llm": {
            "base_url": "http://localhost:11434/v1",
            "model": "llama3.1:70b",
            "api_key": "ollama",
            "temperature": 0.3,
            "max_tokens": 4096,
        },
        "embeddings": {
            "model": "all-MiniLM-L6-v2",
            "store_path": "athanasor/embeddings.store",
            "similarity_threshold": 0.82,
            "redundancy_threshold": 0.85,
        },
        "paths": {
            "project_root": str(_project_root()),
            "nigredo": "nigredo",
            "albedo": "albedo",
            "citrinitas": "citrinitas",
            "rubedo": "rubedo",
            "athanasor": "athanasor",
        },
        "domains": [
            "physics",
            "ML",
            "philosophy",
            "neuroscience",
            "mathematics",
            "unclassified",
        ],
        "exhaustion": {
            "depth_multipliers": {"1": 2, "2": 4, "3": 6, "4": 8, "5": 12},
            "batch_size": 3,
            "redundancy_stop_threshold": 3,
            "speculative_stop_count": 5,
        },
    }


def _coerce_depth_multipliers(value: Any) -> dict[int, int]:
    if not isinstance(value, dict):
        return {1: 2, 2: 4, 3: 6, 4: 8, 5: 12}
    fixed: dict[int, int] = {}
    for raw_key, raw_value in value.items():
        try:
            key = int(raw_key)
            fixed[key] = int(raw_value)
        except (TypeError, ValueError):
            continue
    for key in [1, 2, 3, 4, 5]:
        fixed.setdefault(key, _default_config()["exhaustion"]["depth_multipliers"][str(key)])
    return fixed


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_config(path: Path | None = None) -> Config:
    merged: dict[str, Any] = _default_config()
    config_path = path or (Path(_project_root()) / "azoth.config.yaml")

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        if not isinstance(loaded, dict):
            loaded = {}
        merged = _deep_update(merged, loaded)

    merged["paths"]["project_root"] = str(_project_root())

    # Environment variable overrides.
    merged["llm"]["base_url"] = os.getenv("LLM_BASE_URL", merged["llm"]["base_url"])
    merged["llm"]["model"] = os.getenv("LLM_MODEL", merged["llm"]["model"])
    merged["llm"]["api_key"] = os.getenv("LLM_API_KEY", merged["llm"]["api_key"])

    merged["llm"]["temperature"] = _coerce_float(merged["llm"].get("temperature"), _default_config()["llm"]["temperature"])
    merged["llm"]["max_tokens"] = _coerce_int(merged["llm"].get("max_tokens"), _default_config()["llm"]["max_tokens"])
    merged["embeddings"]["similarity_threshold"] = _coerce_float(
        merged["embeddings"].get("similarity_threshold"),
        _default_config()["embeddings"]["similarity_threshold"],
    )
    merged["embeddings"]["redundancy_threshold"] = _coerce_float(
        merged["embeddings"].get("redundancy_threshold"),
        _default_config()["embeddings"]["redundancy_threshold"],
    )
    merged["exhaustion"]["depth_multipliers"] = _coerce_depth_multipliers(
        merged["exhaustion"].get("depth_multipliers")
    )

    merged["exhaustion"]["batch_size"] = _coerce_int(
        merged["exhaustion"].get("batch_size"),
        _default_config()["exhaustion"]["batch_size"],
    )
    merged["exhaustion"]["redundancy_stop_threshold"] = _coerce_int(
        merged["exhaustion"].get("redundancy_stop_threshold"),
        _default_config()["exhaustion"]["redundancy_stop_threshold"],
    )
    merged["exhaustion"]["speculative_stop_count"] = _coerce_int(
        merged["exhaustion"].get("speculative_stop_count"),
        _default_config()["exhaustion"]["speculative_stop_count"],
    )

    return Config(
        llm=merged["llm"],
        embeddings=merged["embeddings"],
        paths=merged["paths"],
        domains=[str(item) for item in merged.get("domains", [])],
        exhaustion=merged["exhaustion"],
        project_root=str(_project_root()),
    )


def _deep_update(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_update(merged[key], value)
        else:
            merged[key] = value
    return merged


def save_config(config: Config, path: Path | None = None) -> None:
    output = {
        "llm": config.llm,
        "embeddings": config.embeddings,
        "paths": config.paths,
        "domains": config.domains,
        "exhaustion": config.exhaustion,
    }
    target = path or (Path(_project_root()) / "azoth.config.yaml")
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        yaml.safe_dump(output, f, sort_keys=False)
