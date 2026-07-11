"""Consumers must not depend on repository-root resource files."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from athanasor import cli as cli_module
from athanasor.resources import resource_yaml
from athanasor.scripts import migrate as migrate_module
from athanasor.scripts import validate as validate_module
from athanasor.skills import connect, detect, exhaust, ingest
from tests.fixture_factory import write_library


def test_skill_schema_loaders_ignore_repository_root_path_constants(
    tmp_path: Path, monkeypatch
) -> None:
    missing = tmp_path / "missing.yaml"
    monkeypatch.setattr(ingest, "INGEST_SCHEMA_PATH", missing, raising=False)
    monkeypatch.setattr(exhaust, "EXHAUST_SCHEMA_PATH", missing, raising=False)
    monkeypatch.setattr(connect, "CONNECT_SCHEMA_PATH", missing, raising=False)
    monkeypatch.setattr(connect, "RETRIEVAL_SCHEMA_PATH", missing, raising=False)
    monkeypatch.setattr(detect, "DETECT_SCHEMA_PATH", missing, raising=False)

    assert ingest._load_schema_template() == resource_yaml("SCHEMA.yaml")
    assert exhaust._load_schema() == resource_yaml("EXHAUST_SCHEMA.yaml")
    assert connect._load_schema() == resource_yaml("CONNECT_SCHEMA.yaml")
    assert connect._load_retrieval_schema() == resource_yaml("RETRIEVAL_SCHEMA.yaml")
    assert detect._load_schema() == resource_yaml("DETECT_SCHEMA.yaml")


def test_validator_infers_packaged_schema_for_workspace_artifact(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AZOTH_PROJECT_ROOT", str(tmp_path))
    path = write_library(tmp_path, "synthetic_001")
    monkeypatch.setattr(validate_module, "ROOT", tmp_path / "not-the-workspace", raising=False)
    monkeypatch.setattr(
        validate_module,
        "SCHEMA_PATHS",
        {key: tmp_path / f"missing-{key}.yaml" for key in ("library", "exhaust", "connect", "detect")},
        raising=False,
    )

    ok, errors, count = validate_module.validate_file(path)
    assert ok is True, errors
    assert count == 1


def test_validator_all_targets_use_discovered_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AZOTH_PROJECT_ROOT", str(tmp_path))
    path = write_library(tmp_path, "synthetic_001")
    assert validate_module.iter_targets() == [path]


def test_migrator_schema_inference_uses_explicit_workspace_root(tmp_path: Path) -> None:
    path = tmp_path / "albedo" / "library" / "synthetic_001.yaml"
    assert migrate_module._infer_schema_type(path, root=tmp_path) == "library"


def test_cli_launches_installed_helpers_as_modules(tmp_path: Path, monkeypatch) -> None:
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="validated\n", stderr="")

    monkeypatch.setattr(cli_module.subprocess, "run", fake_run)
    assert cli_module._run_python_module(
        "athanasor.scripts.validate", ["--all"], root=tmp_path
    ) == 0
    command, kwargs = calls[0]
    assert command[1:3] == ["-m", "athanasor.scripts.validate"]
    assert command[3:] == ["--all"]
    assert kwargs["cwd"] == str(tmp_path)
