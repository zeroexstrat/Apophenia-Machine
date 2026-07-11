"""Workspace discovery and initialization contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from athanasor import cli as cli_module
from athanasor.config import load_config
from athanasor.workspace import (
    RUNTIME_DIRECTORIES,
    WorkspaceConflictError,
    discover_workspace,
    initialize_workspace,
)


def test_discover_workspace_prefers_environment_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    explicit = tmp_path / "explicit"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setenv("AZOTH_PROJECT_ROOT", str(explicit))
    assert discover_workspace() == explicit.resolve()


def test_discover_workspace_uses_nearest_ancestor_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    nested = root / "notes" / "drafts"
    nested.mkdir(parents=True)
    (root / "azoth.config.yaml").write_text("domains: [ML]\n", encoding="utf-8")
    monkeypatch.delenv("AZOTH_PROJECT_ROOT", raising=False)
    monkeypatch.chdir(nested)
    assert discover_workspace() == root.resolve()


def test_discover_workspace_falls_back_to_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AZOTH_PROJECT_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    assert discover_workspace() == tmp_path.resolve()


def test_initialize_workspace_creates_exact_scaffold_and_seed_files(tmp_path: Path) -> None:
    target = tmp_path / "research"
    result = initialize_workspace(target)

    assert result == target.resolve()
    for relative in RUNTIME_DIRECTORIES:
        assert (target / relative).is_dir(), relative

    config = yaml.safe_load((target / "azoth.config.yaml").read_text(encoding="utf-8"))
    assert config["paths"]["project_root"] == str(target.resolve())
    assert (target / "albedo" / "registry.jsonl").read_text(encoding="utf-8") == ""

    state = json.loads((target / "athanasor" / "lapis" / "state.json").read_text())
    assert state["project"] == "Azoth / Apophenia Machine"
    assert state["processing"]["registry_total"] == 0
    assert set(state["gates"].values()) == {"unchecked"}

    cfg = load_config(path=target / "azoth.config.yaml")
    assert cfg.project_root == str(target.resolve())
    assert cfg.paths["project_root"] == str(target.resolve())


def test_initialize_workspace_is_idempotent_without_overwriting_files(tmp_path: Path) -> None:
    target = initialize_workspace(tmp_path / "research")
    config_path = target / "azoth.config.yaml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    payload["llm"]["model"] = "local-test-model"
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    missing = target / "rubedo" / "drafts"
    missing.rmdir()

    assert initialize_workspace(target) == target
    assert yaml.safe_load(config_path.read_text())["llm"]["model"] == "local-test-model"
    assert missing.is_dir()


def test_initialize_workspace_rejects_non_azoth_nonempty_target(tmp_path: Path) -> None:
    target = tmp_path / "occupied"
    target.mkdir()
    sentinel = target / "keep.txt"
    sentinel.write_text("keep\n", encoding="utf-8")

    with pytest.raises(WorkspaceConflictError, match="non-empty"):
        initialize_workspace(target)

    assert sentinel.read_text(encoding="utf-8") == "keep\n"
    assert sorted(path.name for path in target.iterdir()) == ["keep.txt"]


@pytest.mark.parametrize(
    ("collision", "expected"),
    [
        ("azoth.config.yaml", "configuration"),
        ("albedo/registry.jsonl", "registry"),
        ("athanasor/lapis/state.json", "state"),
    ],
)
def test_initialize_workspace_rejects_path_type_collisions(
    tmp_path: Path, collision: str, expected: str
) -> None:
    target = tmp_path / "workspace"
    target.mkdir()
    config = target / "azoth.config.yaml"
    config.write_text("domains: [ML]\npaths: {}\n", encoding="utf-8")
    path = target / collision
    if collision == "azoth.config.yaml":
        path.unlink()
    path.mkdir(parents=True)

    with pytest.raises(WorkspaceConflictError, match=expected):
        initialize_workspace(target)


def test_initialize_workspace_rejects_invalid_existing_config(tmp_path: Path) -> None:
    target = tmp_path / "workspace"
    target.mkdir()
    (target / "azoth.config.yaml").write_text("llm: [\n", encoding="utf-8")

    with pytest.raises(WorkspaceConflictError, match="Invalid"):
        initialize_workspace(target)


def test_cli_init_reports_absolute_workspace_path(tmp_path: Path) -> None:
    target = tmp_path / "cli-workspace"
    result = CliRunner().invoke(cli_module.main, ["init", str(target)])
    assert result.exit_code == 0, result.output
    assert str(target.resolve()) in result.output
    assert (target / "azoth.config.yaml").is_file()


def test_cli_init_surfaces_conflict_without_traceback(tmp_path: Path) -> None:
    target = tmp_path / "occupied"
    target.mkdir()
    (target / "keep.txt").write_text("keep", encoding="utf-8")
    result = CliRunner().invoke(cli_module.main, ["init", str(target)])
    assert result.exit_code != 0
    assert "non-empty" in result.output
    assert "Traceback" not in result.output
