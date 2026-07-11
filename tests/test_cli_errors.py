"""CLI error surfaces: clean messages for expected failures."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from athanasor import cli as cli_module


@pytest.fixture()
def tmp_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("AZOTH_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AZOTH_SKIP_VIGIL", "1")
    return tmp_path


def test_triage_missing_cluster_reports_cleanly(tmp_project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli_module.main, ["triage", "ghost_cluster", "--no-auto-checkpoint"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()
    assert "unexpectedly" not in result.output.lower()


def test_config_set_rejects_list_index_paths(tmp_project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli_module.main, ["config", "--set", "domains.0", "biology"])
    assert result.exit_code != 0
    assert "domains" in result.output
    # The config file must not have been corrupted by the failed set.
    config_file = tmp_project / "azoth.config.yaml"
    if config_file.exists():
        import yaml

        payload = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert isinstance(payload.get("domains"), list)


def test_config_set_rejects_scalar_over_list(tmp_project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli_module.main, ["config", "--set", "domains", "biology"])
    assert result.exit_code != 0
    assert "list" in result.output.lower()


def test_config_set_accepts_json_list_for_domains(tmp_project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        ["config", "--set", "domains", '["ML", "biology", "unclassified"]'],
    )
    assert result.exit_code == 0, result.output
    import yaml

    payload = yaml.safe_load((tmp_project / "azoth.config.yaml").read_text(encoding="utf-8"))
    assert payload["domains"] == ["ML", "biology", "unclassified"]


def test_validate_all_prints_validator_summary(tmp_project: Path) -> None:
    """`azoth validate --all` must surface the validator's report, not swallow it."""
    runner = CliRunner()
    result = runner.invoke(cli_module.main, ["validate", "--all"])
    assert result.exit_code == 0, result.output
    assert result.output.strip(), "validator output was swallowed"
