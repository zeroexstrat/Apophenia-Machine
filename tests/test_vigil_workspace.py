"""Installed Vigil must gate the active runtime workspace."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from athanasor.skills import common, rubedo_common
from athanasor.vigil import verify
from athanasor.workspace import initialize_workspace


def test_non_git_workspace_has_no_git_drift(tmp_path: Path) -> None:
    root = initialize_workspace(tmp_path / "workspace")
    passed, detail = verify.check_git_drift(root)
    assert passed is True
    assert "not a Git repository" in detail


def test_vigil_module_writes_report_and_close_state_in_workspace(tmp_path: Path) -> None:
    root = initialize_workspace(tmp_path / "workspace")
    env = os.environ.copy()
    env["AZOTH_PROJECT_ROOT"] = str(root)
    result = subprocess.run(
        [sys.executable, "-m", "athanasor.vigil.verify", "close"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Vigil close: PASS" in result.stdout
    reports = list((root / "athanasor" / "vigil" / "reports").glob("vigil_close_*.json"))
    assert len(reports) == 1
    state = (root / "athanasor" / "lapis" / "state.json").read_text(encoding="utf-8")
    assert '"git_drift": "pass"' in state


def test_skill_vigil_launches_installed_module(tmp_path: Path, monkeypatch) -> None:
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="Vigil start: PASS", stderr="")

    monkeypatch.delenv("AZOTH_SKIP_VIGIL", raising=False)
    monkeypatch.setattr(common.subprocess, "run", fake_run)
    output = common.run_vigil_check(tmp_path, "start", "ingest")
    command, kwargs = calls[0]
    assert command == [sys.executable, "-m", "athanasor.vigil.verify", "start"]
    assert kwargs["cwd"] == str(tmp_path)
    assert kwargs["env"]["AZOTH_PROJECT_ROOT"] == str(tmp_path.resolve())
    assert output == "Vigil start: PASS"


def test_explicit_skip_remains_the_only_normal_vigil_bypass(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AZOTH_SKIP_VIGIL", "1")
    monkeypatch.setattr(
        common.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not launch")),
    )
    assert "skipped" in common.run_vigil_check(tmp_path, "start", "ingest").lower()


def test_rubedo_optional_vigil_does_not_require_workspace_source_file(
    tmp_path: Path, monkeypatch
) -> None:
    calls = []
    monkeypatch.setattr(
        rubedo_common,
        "run_vigil_check",
        lambda **kwargs: calls.append(kwargs) or "PASS",
    )
    rubedo_common.run_optional_vigil(tmp_path, "verify", "review")
    assert calls == [{"root": tmp_path, "phase": "verify", "skill": "review"}]
