"""CLI wiring: `awaken --all` must run per-domain slices, not global sweeps."""

from __future__ import annotations

from typing import Any

import pytest
from click.testing import CliRunner

from athanasor import cli as cli_module


@pytest.fixture()
def recorded_exhaust_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_run_exhaust(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        calls.append(kwargs)
        return []

    monkeypatch.setattr(cli_module.exhaust_skill, "run_exhaust", fake_run_exhaust)

    class FakeConfig:
        domains = ["physics", "ML"]

    monkeypatch.setattr(cli_module, "_load_skill_config", lambda no_llm: (FakeConfig(), None))
    return calls


def test_awaken_all_runs_one_domain_scoped_slice_per_domain(
    recorded_exhaust_calls: list[dict[str, Any]],
) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        ["awaken", "--all", "--count", "2", "--no-llm", "--no-auto-checkpoint"],
    )
    assert result.exit_code == 0, result.output
    assert len(recorded_exhaust_calls) == 2
    for call, expected_domain in zip(recorded_exhaust_calls, ["physics", "ML"]):
        assert call["domain"] == expected_domain
        # A per-domain slice must be domain-scoped; all_scope=True would select
        # papers across every domain on each iteration.
        assert call["all_scope"] is False
        assert call["count"] == 2


def test_awaken_single_domain_keeps_domain_scope(
    recorded_exhaust_calls: list[dict[str, Any]],
) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        ["awaken", "physics", "--no-llm", "--no-auto-checkpoint"],
    )
    assert result.exit_code == 0, result.output
    assert len(recorded_exhaust_calls) == 1
    assert recorded_exhaust_calls[0]["domain"] == "physics"
    assert recorded_exhaust_calls[0]["all_scope"] is False
