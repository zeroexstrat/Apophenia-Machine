"""Unit contracts for the installed-wheel smoke harness."""

from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_wheel_install.py"
SPEC = importlib.util.spec_from_file_location("check_wheel_install", SCRIPT)
assert SPEC and SPEC.loader
wheel_smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wheel_smoke)


def _write_wheel(path: Path, names: list[str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, "resource\n")


def test_required_wheel_resources_cover_every_packaged_contract() -> None:
    assert set(wheel_smoke.REQUIRED_WHEEL_RESOURCES) == {
        "athanasor/resources/SCHEMA.yaml",
        "athanasor/resources/EXHAUST_SCHEMA.yaml",
        "athanasor/resources/RETRIEVAL_SCHEMA.yaml",
        "athanasor/resources/CONNECT_SCHEMA.yaml",
        "athanasor/resources/DETECT_SCHEMA.yaml",
        "athanasor/resources/azoth.config.yaml",
        "athanasor/resources/vigil/gates.yaml",
    }


def test_inspect_wheel_accepts_complete_resource_set(tmp_path: Path) -> None:
    wheel = tmp_path / "azoth.whl"
    _write_wheel(wheel, list(wheel_smoke.REQUIRED_WHEEL_RESOURCES))
    assert wheel_smoke.inspect_wheel(wheel) == []


def test_inspect_wheel_reports_missing_resources(tmp_path: Path) -> None:
    wheel = tmp_path / "azoth.whl"
    _write_wheel(wheel, ["athanasor/resources/SCHEMA.yaml"])
    missing = wheel_smoke.inspect_wheel(wheel)
    assert "athanasor/resources/vigil/gates.yaml" in missing
    assert "athanasor/resources/SCHEMA.yaml" not in missing


def test_resolve_wheel_rejects_zero_or_multiple_matches(tmp_path: Path) -> None:
    with pytest.raises(wheel_smoke.SmokeFailure, match="exactly one"):
        wheel_smoke.resolve_wheel(str(tmp_path / "*.whl"))
    _write_wheel(tmp_path / "one.whl", [])
    _write_wheel(tmp_path / "two.whl", [])
    with pytest.raises(wheel_smoke.SmokeFailure, match="exactly one"):
        wheel_smoke.resolve_wheel(str(tmp_path / "*.whl"))
