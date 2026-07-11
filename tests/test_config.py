"""Config loading edge cases: null sections, env overrides, coercions."""

from __future__ import annotations

from pathlib import Path

import pytest

from athanasor.config import load_config


def test_load_config_defaults_when_file_missing(tmp_path: Path) -> None:
    cfg = load_config(path=tmp_path / "does-not-exist.yaml")
    assert cfg.llm["provider"] == "ollama_native"
    assert cfg.exhaustion["depth_multipliers"][3] == 6
    assert "physics" in cfg.domains


def test_load_config_tolerates_null_sections(tmp_path: Path) -> None:
    """A config file with empty sections (`llm:` with nothing after) must not crash."""
    config_path = tmp_path / "azoth.config.yaml"
    config_path.write_text(
        "llm:\nembeddings:\npaths:\ndomains:\nexhaustion:\n",
        encoding="utf-8",
    )
    cfg = load_config(path=config_path)
    assert cfg.llm["provider"] == "ollama_native"
    assert cfg.embeddings["similarity_threshold"] == pytest.approx(0.82)
    assert cfg.domains  # falls back to defaults, not None


def test_load_config_tolerates_scalar_garbage_sections(tmp_path: Path) -> None:
    config_path = tmp_path / "azoth.config.yaml"
    config_path.write_text(
        "llm: 42\ndomains: not-a-list\nexhaustion: []\n",
        encoding="utf-8",
    )
    cfg = load_config(path=config_path)
    assert cfg.llm["provider"] == "ollama_native"
    assert isinstance(cfg.domains, list) and cfg.domains
    assert cfg.exhaustion["batch_size"] == 3


def test_env_overrides_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_MAX_TOKENS", "123")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.9")
    cfg = load_config(path=tmp_path / "missing.yaml")
    assert cfg.llm["provider"] == "openai_compatible"
    assert cfg.llm["model"] == "test-model"
    assert cfg.llm["max_tokens"] == 123
    assert cfg.llm["temperature"] == pytest.approx(0.9)


def test_garbage_numeric_env_values_fall_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MAX_TOKENS", "lots")
    monkeypatch.setenv("LLM_TEMPERATURE", "warm")
    cfg = load_config(path=tmp_path / "missing.yaml")
    assert cfg.llm["max_tokens"] == 4096
    assert cfg.llm["temperature"] == pytest.approx(0.3)


def test_depth_multiplier_garbage_coerced(tmp_path: Path) -> None:
    config_path = tmp_path / "azoth.config.yaml"
    config_path.write_text(
        "exhaustion:\n  depth_multipliers:\n    '1': 'x'\n    '2': 7\n",
        encoding="utf-8",
    )
    cfg = load_config(path=config_path)
    multipliers = cfg.exhaustion["depth_multipliers"]
    assert multipliers[1] == 2  # default restored for garbage value
    assert multipliers[2] == 7  # valid override preserved
    assert set(multipliers) == {1, 2, 3, 4, 5}
