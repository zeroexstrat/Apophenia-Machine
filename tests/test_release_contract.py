from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_release.py"
EVIDENCE = ROOT / "release" / "v0.2.0.json"
SPEC = importlib.util.spec_from_file_location("check_release", SCRIPT)
assert SPEC and SPEC.loader
release_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_check)


def _evidence() -> dict[str, object]:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def test_live_release_contract_matches_locked_evidence() -> None:
    assert release_check.audit_release(ROOT, EVIDENCE) == []


def test_release_contract_uses_exact_version_and_digest() -> None:
    evidence = _evidence()
    assert evidence["version"] == "0.2.0"
    assert evidence["benchmark"]["locked_comparison_sha256"] == (
        "1593841bda8f7aff72b0128824faa48fd568b76651e39dcbd8b8db6d0126e84c"
    )


def test_metric_mutation_is_rejected(tmp_path: Path) -> None:
    evidence = _evidence()
    evidence["benchmark"]["metrics"]["macro_f1"]["value"] = 0.8
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    errors = release_check.audit_release(ROOT, path)
    assert any("/benchmark/metrics/macro_f1/value" in item for item in errors)


@pytest.mark.parametrize(
    "name",
    ["macro_f1", "workload_reduction", "useful_items"],
)
def test_every_missed_target_is_required(tmp_path: Path, name: str) -> None:
    evidence = _evidence()
    evidence["benchmark"]["missed_targets"].remove(name)
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    assert any(
        "/benchmark/missed_targets" in item
        for item in release_check.audit_release(ROOT, path)
    )


@pytest.mark.parametrize(
    "name",
    ["unsafe_ood_assignment", "unsupported_derived_items"],
)
def test_every_undefined_population_is_required(tmp_path: Path, name: str) -> None:
    evidence = _evidence()
    evidence["benchmark"]["undefined_metrics"].remove(name)
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    assert any(
        "/benchmark/undefined_metrics" in item
        for item in release_check.audit_release(ROOT, path)
    )


def test_cli_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == "Release audit: PASS\n"
    assert result.stderr == ""


def test_release_docs_are_versioned_and_balanced() -> None:
    errors = release_check.audit_release(ROOT, EVIDENCE)
    assert errors == []
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    notes = (ROOT / "docs" / "releases" / "v0.2.0.md").read_text(
        encoding="utf-8"
    )
    assert "actions/workflows/hardening.yml/badge.svg" in readme
    assert "@v0.2.0" in readme
    assert "## [0.2.0] - 2026-07-13" in changelog
    for name in release_check.MISSED + release_check.UNDEFINED:
        assert name in notes
    for phrase in (
        "12-paper",
        "66-pair",
        "human-reviewed",
        "not independently verified",
    ):
        assert phrase in notes
