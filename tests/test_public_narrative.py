from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_public_narrative import (
    DIRECT_SOURCES,
    SELECTED_METRICS,
    audit_public_narrative,
    metric_rows,
)


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
CASE_STUDY = ROOT / "docs" / "case-studies" / "looped-transformer-prior-art.md"
COMPARISON = (
    ROOT
    / "benchmarks"
    / "operations-decision-support-v1"
    / "results"
    / "locked-comparison.json"
)
CHECK = ROOT / "scripts" / "check_public_narrative.py"


def _comparison() -> dict[str, object]:
    return json.loads(COMPARISON.read_text(encoding="utf-8"))


def _valid_readme(comparison: dict[str, object] | None = None) -> str:
    rows = "\n".join(metric_rows(comparison or _comparison()))
    return f"""# Azoth

Validity and novelty remain human-reviewed.

## Five-minute demo

This 12-paper, 66-pair suite uses a frozen label. Its provider model identity was
not exposed and is not independently verified.

| Metric | Value | Numerator / denominator | 95% interval | Threshold |
|---|---:|---:|---|---|
{rows}

## Architecture
"""


def _valid_case() -> str:
    sources = "\n".join(f"- [{name}]({url})" for name, url in DIRECT_SOURCES.items())
    return f"""# Case

The candidate remained `pending_review` until primary-source review.
{sources}
The human decision was `rejected`. The next step is a proposed controlled
comparison and replication; no experiment was run.
"""


def _run_check(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECK), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_live_public_narrative_matches_locked_results() -> None:
    errors = audit_public_narrative(
        README.read_text(encoding="utf-8"),
        CASE_STUDY.read_text(encoding="utf-8"),
        _comparison(),
    )
    assert errors == []


def test_metric_rows_cover_exact_model_metric_set() -> None:
    rows = metric_rows(_comparison())
    assert len(rows) == len(SELECTED_METRICS) == 13
    assert rows[0] == (
        "| `macro_f1` | 0.5103 | 33 / 66 | 0.3868–0.6212 | not met |"
    )
    assert rows[1] == (
        "| `unsafe_ood_assignment` | undefined | 0 / 0 | "
        "undefined–undefined | undefined |"
    )
    assert rows[-1] == (
        "| `unsupported_derived_items` | undefined | 0 / 0 | "
        "undefined–undefined | undefined |"
    )


def test_metric_drift_is_rejected() -> None:
    comparison = _comparison()
    readme = _valid_readme(comparison).replace("0.5103", "0.9000", 1)
    errors = audit_public_narrative(readme, _valid_case(), comparison)
    assert any("/README/metrics/macro_f1" in error for error in errors)


@pytest.mark.parametrize(
    ("phrase", "address"),
    [
        ("12-paper", "/README/scope/papers"),
        ("66-pair", "/README/scope/pairs"),
        ("provider model identity", "/README/provenance/provider"),
        ("Validity and novelty remain human-reviewed", "/README/authority"),
    ],
)
def test_readme_requires_scope_and_authority_language(
    phrase: str, address: str
) -> None:
    comparison = _comparison()
    readme = _valid_readme(comparison).replace(phrase, "", 1)
    errors = audit_public_narrative(readme, _valid_case(), comparison)
    assert any(address in error for error in errors)


def test_five_minute_demo_must_precede_architecture() -> None:
    comparison = _comparison()
    readme = _valid_readme(comparison).replace(
        "## Five-minute demo", "## Architecture first", 1
    ).replace("## Architecture\n", "## Five-minute demo\n", 1).replace(
        "## Architecture first", "## Architecture", 1
    )
    errors = audit_public_narrative(readme, _valid_case(), comparison)
    assert any("/README/order" in error for error in errors)


@pytest.mark.parametrize("source", sorted(DIRECT_SOURCES))
def test_case_requires_each_direct_primary_source(source: str) -> None:
    comparison = _comparison()
    case = _valid_case().replace(DIRECT_SOURCES[source], "", 1)
    errors = audit_public_narrative(_valid_readme(comparison), case, comparison)
    assert any(f"/case/sources/{source}" in error for error in errors)


@pytest.mark.parametrize(
    ("phrase", "address"),
    [
        ("pending_review", "/case/status/candidate"),
        ("rejected", "/case/status/decision"),
        ("comparison", "/case/reframe/comparison"),
        ("replication", "/case/reframe/replication"),
    ],
)
def test_case_requires_candidate_rejection_and_reframe(
    phrase: str, address: str
) -> None:
    comparison = _comparison()
    case = _valid_case().replace(phrase, "", 1)
    errors = audit_public_narrative(_valid_readme(comparison), case, comparison)
    assert any(address in error for error in errors)


def test_case_rejects_contradictory_state_order() -> None:
    comparison = _comparison()
    case = _valid_case().replace(
        "The candidate remained `pending_review` until primary-source review.\n",
        "The decision was `rejected` before a later `pending_review` state.\n",
    )
    errors = audit_public_narrative(_valid_readme(comparison), case, comparison)
    assert any("/case/status/order" in error for error in errors)


@pytest.mark.parametrize(
    "phrase", ["we discovered", "novel contribution", "experiment confirmed"]
)
def test_case_rejects_unsupported_completion_language(phrase: str) -> None:
    comparison = _comparison()
    errors = audit_public_narrative(
        _valid_readme(comparison), _valid_case() + phrase, comparison
    )
    assert any("/case/unsupported_claim" in error for error in errors)


def test_invalid_comparison_shape_is_field_addressed() -> None:
    errors = audit_public_narrative(_valid_readme(), _valid_case(), {"runs": []})
    assert errors == [
        "/comparison: /runs/model_5_6_sol: missing model metrics"
    ]


def test_diagnostics_are_sorted_and_deterministic() -> None:
    comparison = _comparison()
    first = audit_public_narrative("", "", comparison)
    second = audit_public_narrative("", "", comparison)
    assert first == second == sorted(first)


def test_cli_passes_with_explicit_valid_files(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    case = tmp_path / "case.md"
    readme.write_text(_valid_readme(), encoding="utf-8")
    case.write_text(_valid_case(), encoding="utf-8")
    result = _run_check(
        "--readme",
        str(readme),
        "--case-study",
        str(case),
        "--comparison",
        str(COMPARISON),
    )
    assert result.returncode == 0
    assert result.stdout == "Public narrative audit: PASS\n"
    assert result.stderr == ""


def test_cli_reports_sorted_findings(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    case = tmp_path / "case.md"
    readme.write_text("# incomplete\n", encoding="utf-8")
    case.write_text("# incomplete\n", encoding="utf-8")
    result = _run_check(
        "--readme",
        str(readme),
        "--case-study",
        str(case),
        "--comparison",
        str(COMPARISON),
    )
    assert result.returncode == 1
    assert result.stdout.startswith("Public narrative audit: FAIL\n")
    findings = [line for line in result.stdout.splitlines() if line.startswith("- ")]
    assert findings == sorted(findings)
    assert result.stderr == ""


def test_cli_returns_two_for_unreadable_input(tmp_path: Path) -> None:
    result = _run_check("--readme", str(tmp_path / "missing.md"))
    assert result.returncode == 2
    assert result.stdout.startswith("Public narrative audit: ERROR:")
    assert result.stderr == ""
