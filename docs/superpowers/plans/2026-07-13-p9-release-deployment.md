# P9 Release and Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the verified P8 tree as the GitHub-only `v0.2.0` release and align the hosted repository and `0xstrategies.com` portfolio with one audited, evidence-backed public narrative.

**Architecture:** P9 is a staged two-repository release train. The Apophenia Machine repository first creates a versioned evidence contract, verifies wheel and sdist artifacts across Python 3.10-3.12, publishes the exact accepted SHA and immutable GitHub release, and only then supplies the canonical release URL and evidence projection used by the portfolio. The portfolio keeps its current bundled homepage/resume runtime, uses a deterministic template transformer, adds one plain static technical case study, and deploys through its existing Cloudflare Pages `main` branch.

**Tech Stack:** Python 3.10-3.12, pytest, Click, uv, setuptools, YAML/JSON, GitHub Actions, GitHub CLI, static HTML/CSS, Python `unittest`, ReportLab PDF generation, Poppler rendering, Cloudflare Pages.

## Global Constraints

- Distribution is GitHub-only; do not publish to PyPI.
- `pyproject.toml` is the only package-version authority and must resolve to `0.2.0`.
- Do not mutate benchmark inputs, gold labels, prompts, metrics, thresholds, raw runs, or P5-P7 frozen outputs.
- Every public benchmark claim must be derived from `benchmarks/operations-decision-support-v1/results/locked-comparison.json` with SHA-256 `1593841bda8f7aff72b0128824faa48fd568b76651e39dcbd8b8db6d0126e84c`.
- Preserve the 12-paper / 66-pair suite scope, human validity and novelty authority, external-validity limit, and unverified provider-model-identity limit.
- Publish all three missed targets (`macro_f1`, `workload_reduction`, `useful_items`) and both undefined populations (`unsafe_ood_assignment`, `unsupported_derived_items`).
- Support and verify Python 3.10, 3.11, and 3.12.
- Never move or reuse tag `v0.2.0` after it is pushed.
- Keep the portfolio operations-first; preserve `writing/azoth.html` as the reflective essay.
- Add at most one benchmark-evidence bullet to the resume and keep the HTML, Markdown source, and PDF consistent.
- Do not publish gold labels, rationales, pair-level failures, raw runs, private paths, provider secrets, employee IDs, or internal email addresses.
- Run `python3 athanasor/vigil/verify.py start` before substantive repository work, `verify` after implementation, and `close` on the final committed tree.

## Working directories

- Set `APOPHENIA_REPO=$(git rev-parse --show-toplevel)` from the current durable
  Apophenia Machine feature checkout.
- Set `PORTFOLIO_REPO` to the operator-provided clone of private repository
  `zeroexstrat/0xstrategies`; never commit its machine-local absolute path.
- Apophenia branch: `codex/p9-release-deployment`
- Portfolio branch to create during Task 4: `codex/p9-apophenia-case-study`

---

### Task 1: Versioned release evidence and fail-closed audit

**Files:**
- Create: `release/v0.2.0.json`
- Create: `scripts/check_release.py`
- Create: `tests/test_release_contract.py`
- Modify: `pyproject.toml:7`
- Regenerate for local verification only: ignored, untracked `uv.lock`
- Modify: `skills/azoth/scripts/preflight.py:29`
- Modify: `skills/azoth/reference/workflow.md:15`
- Modify: `skills/azoth/reference/troubleshooting.md:53`
- Modify: `tests/test_audit_and_release.py:66-77`

**Interfaces:**
- Consumes: `locked-comparison.json`, `pyproject.toml`, and the existing P8 narrative contract.
- Produces: `load_release_evidence(path: Path) -> dict[str, Any]`, `audit_release(root: Path, evidence_path: Path) -> list[str]`, and a CLI that prints exactly `Release audit: PASS` on success.

- [ ] **Step 1: Write failing release-contract tests**

Add `tests/test_release_contract.py` with tests that import `scripts/check_release.py`, require the exact version and digest, mutate one metric, remove each miss/undefined name, and exercise CLI diagnostics:

```python
from __future__ import annotations

import copy
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
    assert any("/benchmark/missed_targets" in item for item in release_check.audit_release(ROOT, path))


@pytest.mark.parametrize(
    "name",
    ["unsafe_ood_assignment", "unsupported_derived_items"],
)
def test_every_undefined_population_is_required(tmp_path: Path, name: str) -> None:
    evidence = _evidence()
    evidence["benchmark"]["undefined_metrics"].remove(name)
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    assert any("/benchmark/undefined_metrics" in item for item in release_check.audit_release(ROOT, path))


def test_cli_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=ROOT, text=True, capture_output=True
    )
    assert result.returncode == 0
    assert result.stdout == "Release audit: PASS\n"
    assert result.stderr == ""
```

- [ ] **Step 2: Run the focused tests and observe RED**

Run:

```bash
uv run --python 3.12 pytest tests/test_release_contract.py -q
```

Expected: collection fails because `scripts/check_release.py` does not exist.

- [ ] **Step 3: Add the release evidence document**

Create `release/v0.2.0.json` with the full public contract. Use the exact eight portfolio-facing metrics below and copy their raw numeric values, numerator, denominator, interval, and threshold result from the locked comparison:

```json
{
  "schema_version": 1,
  "artifact_type": "azoth_release_evidence",
  "version": "0.2.0",
  "python": ["3.10", "3.11", "3.12"],
  "benchmark": {
    "benchmark_id": "operations-decision-support-v1",
    "locked_comparison_sha256": "1593841bda8f7aff72b0128824faa48fd568b76651e39dcbd8b8db6d0126e84c",
    "papers": 12,
    "pairs": 66,
    "runs": 7,
    "metric_records": 91,
    "metrics": {
      "macro_f1": {"value": 0.5102638352638353, "numerator": 33, "denominator": 66, "lower": 0.3867630666808299, "upper": 0.6212488324286953, "threshold_met": false},
      "unsafe_ood_assignment": {"value": null, "numerator": 0, "denominator": 0, "lower": null, "upper": null, "threshold_met": null},
      "claim_precision": {"value": 0.9393939393939394, "numerator": 62, "denominator": 66, "lower": 0.8542709132143579, "upper": 0.9761813851676816, "threshold_met": true},
      "reference_recall": {"value": 1.0, "numerator": 27, "denominator": 27, "lower": 0.8754449702581328, "upper": 0.9999999999999998, "threshold_met": true},
      "candidate_recall": {"value": 1.0, "numerator": 27, "denominator": 27, "lower": 0.8754449702581328, "upper": 0.9999999999999998, "threshold_met": true},
      "workload_reduction": {"value": 0.42424242424242425, "numerator": 28, "denominator": 66, "lower": 0.30303030303030304, "upper": 0.5303030303030303, "threshold_met": false},
      "useful_items": {"value": 0.5151515151515151, "numerator": 34, "denominator": 66, "lower": 0.39710591285717234, "upper": 0.6315303732939324, "threshold_met": false},
      "unsupported_derived_items": {"value": null, "numerator": 0, "denominator": 0, "lower": null, "upper": null, "threshold_met": null}
    },
    "missed_targets": ["macro_f1", "workload_reduction", "useful_items"],
    "undefined_metrics": ["unsafe_ood_assignment", "unsupported_derived_items"]
  },
  "limitations": {
    "suite": "One frozen 12-paper, 66-pair operations-decision-support suite; no external-validity claim.",
    "authority": "Validity and novelty remain human-reviewed.",
    "provider": "5.6 Sol is the frozen backend label; provider model identity was not exposed and is not independently verified."
  },
  "urls": {
    "repository": "https://github.com/zeroexstrat/Apophenia-Machine",
    "release": "https://github.com/zeroexstrat/Apophenia-Machine/releases/tag/v0.2.0",
    "case_study": "https://0xstrategies.com/case-studies/apophenia-machine.html"
  }
}
```

- [ ] **Step 4: Implement the release auditor**

Create `scripts/check_release.py`. Reuse the model-run selection logic from `scripts/check_public_narrative.py`; compare JSON values without rounding:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = ROOT / "release" / "v0.2.0.json"
COMPARISON = ROOT / "benchmarks" / "operations-decision-support-v1" / "results" / "locked-comparison.json"
MISSED = ["macro_f1", "workload_reduction", "useful_items"]
UNDEFINED = ["unsafe_ood_assignment", "unsupported_derived_items"]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _version(root: Path) -> str:
    match = re.search(r'^version\s*=\s*"([^"]+)"', (root / "pyproject.toml").read_text(), re.M)
    if not match:
        raise ValueError("pyproject version missing")
    return match.group(1)


def _model_metrics(comparison: dict[str, Any]) -> dict[str, dict[str, Any]]:
    run = next(row for row in comparison["runs"] if row["run_id"] == "model_5_6_sol")
    return {row["name"]: row for row in run["metrics"]}


def load_release_evidence(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def audit_release(root: Path = ROOT, evidence_path: Path = DEFAULT_EVIDENCE) -> list[str]:
    errors: list[str] = []
    evidence = load_release_evidence(evidence_path)
    comparison_path = root / COMPARISON.relative_to(ROOT)
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    expected = _model_metrics(comparison)
    if evidence.get("version") != _version(root):
        errors.append("/version: evidence and pyproject differ")
    digest = evidence.get("benchmark", {}).get("locked_comparison_sha256")
    if digest != _sha256(comparison_path):
        errors.append("/benchmark/locked_comparison_sha256: mismatch")
    for name, public in evidence.get("benchmark", {}).get("metrics", {}).items():
        locked = expected.get(name)
        if locked is None:
            errors.append(f"/benchmark/metrics/{name}: unknown metric")
            continue
        fields = {
            "value": locked["value"], "numerator": locked["numerator"],
            "denominator": locked["denominator"],
            "lower": locked["uncertainty_result"]["lower"],
            "upper": locked["uncertainty_result"]["upper"],
            "threshold_met": locked["threshold_met"],
        }
        for field, value in fields.items():
            if public.get(field) != value:
                errors.append(f"/benchmark/metrics/{name}/{field}: mismatch")
    if evidence.get("benchmark", {}).get("missed_targets") != MISSED:
        errors.append("/benchmark/missed_targets: exact ordered set required")
    if evidence.get("benchmark", {}).get("undefined_metrics") != UNDEFINED:
        errors.append("/benchmark/undefined_metrics: exact ordered set required")
    limits = " ".join(evidence.get("limitations", {}).values()).lower()
    for phrase in ("external-validity", "human-reviewed", "not independently verified"):
        if phrase not in limits:
            errors.append(f"/limitations/{phrase}: missing")
    return sorted(errors)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    args = parser.parse_args()
    errors = audit_release(ROOT, args.evidence)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("Release audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Bump the single version source and pins**

Change `pyproject.toml` to `version = "0.2.0"`, run `uv lock` to refresh the intentionally ignored local lock, and replace the three `@v0.1.3` install pins with `@v0.2.0`. Do not force-add `uv.lock`. Do not rewrite historical `PROJECT_ROADMAP.md` or lineage-test references to old `v0.1.3` state.

```bash
uv lock
rg -n "@v0\.1\.3|version = \"0\.1\.3\"" pyproject.toml uv.lock skills
```

Expected: no matches.

- [ ] **Step 6: Run GREEN tests and existing version audit**

```bash
uv run --python 3.12 pytest tests/test_release_contract.py tests/test_audit_and_release.py -q
python3 scripts/check_release.py
```

Expected: all tests pass and `Release audit: PASS`.

- [ ] **Step 7: Commit Task 1**

```bash
git add pyproject.toml release/v0.2.0.json scripts/check_release.py tests/test_release_contract.py tests/test_audit_and_release.py skills/azoth
git commit -m "feat: bind v0.2.0 release evidence"
```

---

### Task 2: Wheel and sdist acceptance on Python 3.10-3.12

**Files:**
- Modify: `scripts/check_wheel_install.py`
- Modify: `tests/test_wheel_install.py`
- Modify: `.github/workflows/hardening.yml`

**Interfaces:**
- Consumes: a quoted wheel glob, a quoted sdist glob, expected version, and repeated Python versions.
- Produces: `resolve_artifact(pattern: str) -> Path`, `inspect_sdist(path: Path) -> list[str]`, and one complete smoke run per artifact/interpreter pair.

- [ ] **Step 1: Add failing artifact tests**

Extend `tests/test_wheel_install.py` with tarball fixtures, version expectations, and parser coverage:

```python
import io
import tarfile


def _write_sdist(path: Path, names: list[str]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name in names:
            payload = b"resource\n"
            info = tarfile.TarInfo(f"azoth-0.2.0/{name}")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))


def test_inspect_sdist_accepts_complete_resource_set(tmp_path: Path) -> None:
    sdist = tmp_path / "azoth-0.2.0.tar.gz"
    _write_sdist(sdist, list(wheel_smoke.REQUIRED_WHEEL_RESOURCES))
    assert wheel_smoke.inspect_sdist(sdist) == []


def test_inspect_sdist_reports_missing_resources(tmp_path: Path) -> None:
    sdist = tmp_path / "azoth-0.2.0.tar.gz"
    _write_sdist(sdist, ["athanasor/resources/SCHEMA.yaml"])
    assert "athanasor/resources/vigil/gates.yaml" in wheel_smoke.inspect_sdist(sdist)


def test_parser_requires_expected_version_and_accepts_both_artifacts() -> None:
    args = wheel_smoke.build_parser().parse_args([
        "--wheel", "dist/*.whl", "--sdist", "dist/*.tar.gz",
        "--expected-version", "0.2.0", "--python", "3.12",
    ])
    assert args.expected_version == "0.2.0"
    assert args.sdist == "dist/*.tar.gz"
```

- [ ] **Step 2: Run RED**

```bash
uv run --python 3.12 pytest tests/test_wheel_install.py -q
```

Expected: failures for missing `inspect_sdist`, `--sdist`, and `--expected-version`.

- [ ] **Step 3: Generalize the installed-artifact smoke harness**

In `scripts/check_wheel_install.py`, import `importlib.metadata` only inside the installed-environment probe, add `tarfile`, and make the install target generic:

```python
import tarfile


def resolve_artifact(pattern: str) -> Path:
    matches = sorted(Path(path).resolve() for path in glob.glob(pattern))
    if len(matches) != 1:
        raise SmokeFailure(f"Expected exactly one artifact for {pattern!r}; found {len(matches)}")
    return matches[0]


def inspect_sdist(sdist: Path) -> list[str]:
    with tarfile.open(sdist, "r:gz") as archive:
        names = {name.split("/", 1)[1] for name in archive.getnames() if "/" in name}
    return [name for name in REQUIRED_WHEEL_RESOURCES if name not in names]
```

Rename `run_version(wheel, python_version, ...)` to `run_version(artifact, python_version, *, expected_version, keep_temp=False)`. Install `artifact`, then add this probe after import isolation:

```python
version_probe = _run(
    [str(python), "-c", "import importlib.metadata; print(importlib.metadata.version('azoth'))"],
    cwd=outside,
    env=env,
)
if version_probe.stdout.strip() != expected_version:
    raise SmokeFailure(
        f"Python {python_version} installed version {version_probe.stdout.strip()!r}, expected {expected_version!r}"
    )
```

Update the parser and `main`:

```python
parser.add_argument("--wheel", required=True)
parser.add_argument("--sdist", required=True)
parser.add_argument("--expected-version", required=True)

wheel = resolve_artifact(args.wheel)
sdist = resolve_artifact(args.sdist)
missing = inspect_wheel(wheel) + inspect_sdist(sdist)
if missing:
    raise SmokeFailure("Release artifact is missing resources: " + ", ".join(sorted(set(missing))))
retained = []
for artifact in (wheel, sdist):
    for version in args.versions:
        path = run_version(
            artifact, version, expected_version=args.expected_version, keep_temp=args.keep_temp
        )
        if path is not None:
            retained.append(path)
print(f"Installed-artifact smoke passed for {2 * len(args.versions)} artifact/interpreter pair(s).")
```

- [ ] **Step 4: Update hosted CI to build and verify both artifacts**

Replace the wheel-only workflow step with:

```yaml
      - name: Verify release artifacts outside checkout
        run: |
          rm -rf dist
          uv build --wheel --sdist --out-dir dist
          python3 scripts/check_wheel_install.py \
            --wheel 'dist/azoth-*.whl' \
            --sdist 'dist/azoth-*.tar.gz' \
            --expected-version 0.2.0 \
            --python '${{ matrix.python-version }}'
```

Add `python3 scripts/check_release.py` immediately after the public narrative audit or benchmark protocol step.

- [ ] **Step 5: Run GREEN unit tests**

```bash
uv run --python 3.12 pytest tests/test_wheel_install.py tests/test_release_contract.py -q
```

Expected: all focused tests pass.

- [ ] **Step 6: Build and run the six-pair artifact smoke**

```bash
rm -rf dist
uv build --wheel --sdist --out-dir dist
uv run --python 3.12 python scripts/check_wheel_install.py \
  --wheel 'dist/azoth-*.whl' \
  --sdist 'dist/azoth-*.tar.gz' \
  --expected-version 0.2.0 \
  --python 3.10 --python 3.11 --python 3.12
```

Expected: six PASS lines and final `Installed-artifact smoke passed for 6 artifact/interpreter pair(s).`

- [ ] **Step 7: Commit Task 2**

```bash
git add scripts/check_wheel_install.py tests/test_wheel_install.py .github/workflows/hardening.yml
git commit -m "test: verify v0.2.0 wheel and sdist"
```

---

### Task 3: Release-facing README, changelog, and notes

**Files:**
- Create: `CHANGELOG.md`
- Create: `docs/releases/v0.2.0.md`
- Modify: `README.md`
- Modify: `scripts/check_release.py`
- Modify: `tests/test_release_contract.py`

**Interfaces:**
- Consumes: release evidence and P8 public narrative.
- Produces: auditable README badge/install links, changelog, and exact GitHub release-note body.

- [ ] **Step 1: Add failing documentation tests**

```python
def test_release_docs_are_versioned_and_balanced() -> None:
    errors = release_check.audit_release(ROOT, EVIDENCE)
    assert errors == []
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    notes = (ROOT / "docs" / "releases" / "v0.2.0.md").read_text(encoding="utf-8")
    assert "actions/workflows/hardening.yml/badge.svg" in readme
    assert "@v0.2.0" in readme
    assert "## [0.2.0] - 2026-07-13" in changelog
    for name in release_check.MISSED + release_check.UNDEFINED:
        assert name in notes
    for phrase in ("12-paper", "66-pair", "human-reviewed", "not independently verified"):
        assert phrase in notes
```

- [ ] **Step 2: Run RED**

```bash
uv run --python 3.12 pytest tests/test_release_contract.py::test_release_docs_are_versioned_and_balanced -q
```

Expected: failure because `CHANGELOG.md` and release notes do not exist.

- [ ] **Step 3: Add README badge and pinned installation**

Place this badge below the title and add the pinned install beside the source install instructions:

```markdown
[![hardening](https://github.com/zeroexstrat/Apophenia-Machine/actions/workflows/hardening.yml/badge.svg?branch=main)](https://github.com/zeroexstrat/Apophenia-Machine/actions/workflows/hardening.yml)

Stable Git release:

```bash
pip install 'git+https://github.com/zeroexstrat/Apophenia-Machine@v0.2.0'
```
```

Do not change the exact P8 benchmark table or limitations.

- [ ] **Step 4: Write changelog and release notes**

`CHANGELOG.md` must include version `0.2.0`, Python 3.10-3.12, clean public baseline, installed workspace, frozen benchmark, locked results, rejection/reframe case, and all limits. `docs/releases/v0.2.0.md` must contain:

```markdown
# Azoth v0.2.0

Azoth is a local, human-gated research-operations pipeline for turning technical documents into schema-validated evidence records, ranked candidate connections, and auditable review decisions.

The wheel and source distribution were installed and exercised outside the checkout on Python 3.10, 3.11, and 3.12.

## Measured evaluation

The locked evaluation covers one frozen 12-paper, 66-pair operations-decision-support suite. It met claim precision, reference recall, candidate recall, ranking, evidence-support, supported-item, and redundancy targets. It missed `macro_f1`, `workload_reduction`, and `useful_items`. `unsafe_ood_assignment` and `unsupported_derived_items` are undefined because their eligible denominators were zero.

Validity and novelty remain human-reviewed. The suite does not establish external validity. `5.6 Sol` is the frozen backend label; provider model identity was not exposed and is not independently verified.

## Prior-art rejection

The looped-transformer candidate remained `pending_review`, was rejected after direct review of Parcae, STARS, and CART, and was reframed as a proposed comparison/replication rather than presented as a discovery.

## Verify downloads

```bash
shasum -a 256 -c SHA256SUMS.txt
```
```

- [ ] **Step 5: Extend the release audit to read all three documents**

Append these checks inside `audit_release` before `return sorted(errors)`:

```python
readme = (root / "README.md").read_text(encoding="utf-8")
changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
notes = (root / "docs" / "releases" / "v0.2.0.md").read_text(encoding="utf-8")
if "actions/workflows/hardening.yml/badge.svg?branch=main" not in readme:
    errors.append("/README/badge: missing main hardening badge")
if "@v0.2.0" not in readme:
    errors.append("/README/install: missing v0.2.0 pin")
if "## [0.2.0] - 2026-07-13" not in changelog:
    errors.append("/CHANGELOG/version: missing 0.2.0 heading")
if any(name not in notes for name in MISSED):
    errors.append("/release_notes/missed_targets: exact names required")
if any(name not in notes for name in UNDEFINED):
    errors.append("/release_notes/undefined_metrics: exact names required")
for phrase in ("12-paper", "66-pair", "human-reviewed", "external validity", "not independently verified"):
    if phrase.lower() not in notes.lower():
        errors.append(f"/release_notes/limitations/{phrase}: missing")
```

- [ ] **Step 6: Run GREEN documentation and narrative audits**

```bash
uv run --python 3.12 pytest tests/test_release_contract.py tests/test_public_narrative.py -q
python3 scripts/check_release.py
python3 scripts/check_public_narrative.py
```

Expected: all tests and both audits pass.

- [ ] **Step 7: Commit Task 3**

```bash
git add README.md CHANGELOG.md docs/releases/v0.2.0.md scripts/check_release.py tests/test_release_contract.py
git commit -m "docs: prepare v0.2.0 release narrative"
```

---

### Task 4: Portfolio evidence manifest, bundle transformer, and audit

**Files (portfolio repository):**
- Create: `assets/data/apophenia-v0.2.0.json`
- Create: `scripts/update_bundle_copy.py`
- Create: `scripts/check_apophenia_portfolio.py`
- Create: `tests/test_apophenia_portfolio.py`

**Interfaces:**
- Consumes: the accepted `release/v0.2.0.json` and bundled JSON templates inside `index.html` and `resume.html`.
- Produces: `extract_template(path: Path) -> str`, `replace_template(path: Path, replacements: dict[str, str]) -> None`, `audit_portfolio(root: Path) -> list[str]`, and CLI PASS/FAIL output.

- [ ] **Step 1: Create and switch to the portfolio feature branch**

```bash
cd "$PORTFOLIO_REPO"
git switch -c codex/p9-apophenia-case-study
git status --short --branch
```

Expected: clean feature branch based on `019b7aa`.

- [ ] **Step 2: Add failing transformer and audit tests**

Use stdlib `unittest` so the static-site repo needs no package installation:

```python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_apophenia_portfolio import audit_portfolio
from scripts.update_bundle_copy import extract_template, replace_template

ROOT = Path(__file__).resolve().parents[1]


class BundleTransformerTests(unittest.TestCase):
    def test_exact_single_replacement_round_trips_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "page.html"
            path.write_text('<script type="__bundler/template">"old text"</script>')
            replace_template(path, {"old text": "new text"})
            self.assertEqual(extract_template(path), "new text")

    def test_missing_or_duplicate_source_refuses_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "page.html"
            path.write_text('<script type="__bundler/template">"old old"</script>')
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "exactly once"):
                replace_template(path, {"old": "new"})
            self.assertEqual(path.read_bytes(), before)


class PortfolioAuditUnitTests(unittest.TestCase):
    def test_missing_evidence_is_field_addressed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(audit_portfolio(Path(directory)), ["/evidence: missing"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run RED**

```bash
python3 -m unittest tests/test_apophenia_portfolio.py -v
```

Expected: import failure because both scripts are missing.

- [ ] **Step 4: Implement the fail-closed bundled-template transformer**

```python
#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

PATTERN = re.compile(r'(<script type="__bundler/template">)(.*?)(</script>)', re.S)


def extract_template(path: Path) -> str:
    match = PATTERN.search(path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"{path}: bundled template missing")
    return json.loads(match.group(2))


def replace_template(path: Path, replacements: dict[str, str]) -> None:
    raw = path.read_text(encoding="utf-8")
    match = PATTERN.search(raw)
    if not match:
        raise ValueError(f"{path}: bundled template missing")
    template = json.loads(match.group(2))
    for old, new in replacements.items():
        count = template.count(old)
        if count != 1:
            raise ValueError(f"{path}: expected source exactly once, found {count}: {old[:80]!r}")
        template = template.replace(old, new)
    encoded = json.dumps(template, ensure_ascii=False)
    updated = raw[:match.start(2)] + encoded + raw[match.end(2):]
    path.write_text(updated, encoding="utf-8")
```

- [ ] **Step 5: Copy the public evidence projection and implement the portfolio audit**

Copy the eight-metric release evidence projection to `assets/data/apophenia-v0.2.0.json`. Create `scripts/check_apophenia_portfolio.py` with the complete tracked-HTML, claim, link, and privacy audit below:

```python
#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

from scripts.update_bundle_copy import extract_template

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PAGES = (
    "index.html", "resume.html", "writing/azoth.html",
    "case-studies/apophenia-machine.html",
)
OLD_PILOT = "57 papers across ML, physics, philosophy, mathematics, and neuroscience; 5 candidates"
REQUIRED_LIMITS = ("12-paper", "66-pair", "human-reviewed", "external validity", "not independently verified")
RESUME_BULLET = "On one frozen 12-paper, 66-pair suite"


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name in {"href", "src"} and value:
                self.links.append(value)


def _tracked_html(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "*.html"],
        check=True, capture_output=True,
    )
    return [root / item.decode() for item in result.stdout.split(b"\0") if item]


def _visible_source(path: Path, root: Path) -> str:
    relative = path.relative_to(root).as_posix()
    if relative in {"index.html", "resume.html"}:
        return extract_template(path)
    return path.read_text(encoding="utf-8")


def _link_errors(root: Path, path: Path, html: str) -> list[str]:
    parser = LinkParser()
    parser.feed(html)
    errors: list[str] = []
    for link in parser.links:
        parsed = urlparse(link)
        if parsed.scheme in {"mailto", "tel", "data", "blob"} or link.startswith("#"):
            continue
        if parsed.scheme:
            if parsed.scheme != "https":
                errors.append(f"/{path.relative_to(root)}/link: external URL must use HTTPS: {link}")
            continue
        relative = unquote(parsed.path)
        if not relative:
            continue
        target = (path.parent / relative).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            errors.append(f"/{path.relative_to(root)}/link: escapes root: {link}")
            continue
        if target.is_dir():
            target = target / "index.html"
        if not target.exists():
            errors.append(f"/{path.relative_to(root)}/link: missing target: {link}")
    return errors


def audit_portfolio(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    evidence_path = root / "assets" / "data" / "apophenia-v0.2.0.json"
    if not evidence_path.is_file():
        return ["/evidence: missing"]
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if evidence.get("version") != "0.2.0":
        errors.append("/evidence/version: expected 0.2.0")
    if evidence.get("benchmark", {}).get("papers") != 12:
        errors.append("/evidence/benchmark/papers: expected 12")
    if evidence.get("benchmark", {}).get("pairs") != 66:
        errors.append("/evidence/benchmark/pairs: expected 66")

    text_by_path: dict[str, str] = {}
    for relative in REQUIRED_PAGES:
        path = root / relative
        if not path.is_file():
            errors.append(f"/{relative}: missing")
            continue
        text_by_path[relative] = _visible_source(path, root)
    joined = "\n".join(text_by_path.values())
    if OLD_PILOT in joined:
        errors.append("/claims/pilot_inventory: prohibited")
    for phrase in REQUIRED_LIMITS:
        if phrase.lower() not in joined.lower():
            errors.append(f"/claims/limitations/{phrase}: missing")
    resume = text_by_path.get("resume.html", "")
    if resume.count(RESUME_BULLET) != 1:
        errors.append("/resume/benchmark_bullet: exactly one required")
    for forbidden in ("/Users/", "__bundler_err", "[bundle]", "benchmarks/operations-decision-support-v1/private"):
        if forbidden in joined:
            errors.append(f"/privacy/{forbidden}: prohibited")
    if re.search(r"\b(?:employee|slic)\s*[:#-]?\s*\d{4,}\b", joined, re.I):
        errors.append("/privacy/employee_identifier: prohibited")
    if re.search(r"[A-Z0-9._%+-]+@(?:ups|corp|internal)\.[A-Z]{2,}", joined, re.I):
        errors.append("/privacy/internal_email: prohibited")
    for path in _tracked_html(root):
        errors.extend(_link_errors(root, path, _visible_source(path, root)))
    return sorted(errors)


def main() -> int:
    errors = audit_portfolio(ROOT)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("Portfolio Apophenia audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Run the audit-foundation tests GREEN**

```bash
python3 -m unittest tests/test_apophenia_portfolio.py -v
```

Expected: transformer round-trip/refusal tests and the missing-evidence diagnostic test pass. The live-site acceptance test is deliberately added in Task 5 before public content changes.

- [ ] **Step 7: Commit the audit foundation**

```bash
git add assets/data/apophenia-v0.2.0.json scripts tests
git commit -m "test: bind portfolio to v0.2.0 evidence"
```

---

### Task 5: Technical case study, homepage, resume, and PDF

**Files (portfolio repository):**
- Create: `case-studies/apophenia-machine.html`
- Create: `assets/rafael-de-almeida-operations-ai-systems-resume-v5.md`
- Create: `assets/rafael-de-almeida-operations-ai-systems-resume-v5.pdf`
- Modify: `index.html` bundled template
- Modify: `resume.html` bundled template
- Modify: `writing/azoth.html`
- Modify: `assets/portfolio.css`
- Modify: `README.md`
- Modify: `scripts/check_apophenia_portfolio.py`
- Modify: `tests/test_apophenia_portfolio.py`

**Interfaces:**
- Consumes: portfolio evidence manifest and live GitHub release URL.
- Produces: one technical case-study route and mutually consistent homepage, resume, PDF, and reflective-essay navigation.

- [ ] **Step 1: Add exact live-copy assertions before editing pages**

Extend the live tests:

```python
def test_live_portfolio_passes_claim_and_link_audit(self) -> None:
    self.assertEqual(audit_portfolio(ROOT), [])


def test_case_study_contains_balanced_locked_results(self) -> None:
    case = (ROOT / "case-studies/apophenia-machine.html").read_text()
    for phrase in (
        "0.9394", "1.0000", "0.5103", "0.4242", "0.5152",
        "undefined", "pending_review", "rejected", "Parcae", "STARS", "CART",
    ):
        self.assertIn(phrase, case)


def test_homepage_links_three_distinct_azoth_surfaces(self) -> None:
    home = extract_template(ROOT / "index.html")
    self.assertIn("case-studies/apophenia-machine.html", home)
    self.assertIn("https://github.com/zeroexstrat/Apophenia-Machine", home)
    self.assertIn("writing/azoth.html", home)


def test_resume_sources_use_one_balanced_benchmark_bullet(self) -> None:
    html = extract_template(ROOT / "resume.html")
    markdown = (ROOT / "assets/rafael-de-almeida-operations-ai-systems-resume-v5.md").read_text()
    bullet = (
        "On one frozen 12-paper, 66-pair suite, recovered all 27 human-labeled relevant pairs "
        "while publishing the missed macro-F1, workload-reduction, and usefulness targets."
    )
    self.assertIn(bullet, html)
    self.assertIn(bullet, markdown)
    self.assertEqual(html.count(bullet), 1)
```

- [ ] **Step 2: Run RED copy tests**

```bash
python3 -m unittest tests/test_apophenia_portfolio.py -v
```

Expected: failures for missing case study, links, v5 source, and benchmark bullet.

- [ ] **Step 3: Build the technical case study**

Create a semantic standalone HTML document that links `../assets/portfolio.css`. Use these fixed sections and claims:

```html
<main class="case-study-page">
  <header class="case-study-hero">
    <p class="eyebrow">Research operations · Python · human review gates</p>
    <h1>Apophenia Machine</h1>
    <p class="lede">A local pipeline that turns technical documents into reviewable evidence records and candidate connections without allowing generated prose to become authority.</p>
  </header>
  <section>
    <h2>The operating problem</h2>
    <p>Technical reading produces claims, notes, possible connections, and dead ends across files and sessions. Without durable evidence labels and explicit review states, a plausible model response can be mistaken for a finding and a useful rejection can disappear.</p>
  </section>
  <section>
    <h2>The system</h2>
    <p>Azoth separates ingestion, exhaustion, candidate generation, gap detection, and human decisions. YAML schemas validate artifacts, deterministic fallbacks keep the CLI usable without a model, Vigil gates reject invalid state, and <code>azoth init</code> creates a writable workspace from an installed wheel rather than relying on the source checkout.</p>
  </section>
  <section>
    <h2>The locked evaluation</h2>
    <p>The evaluation froze 12 exact papers and all 66 pairs before scoring. Rafael supplied the final human labels. Generation was sealed before gold access and results were published without retuning after misses.</p>
    <table class="metric-grid">
      <thead><tr><th>Metric</th><th>Value</th><th>Count</th><th>Result</th></tr></thead>
      <tbody>
        <tr><td>Claim precision</td><td>0.9394</td><td>62 / 66</td><td>met</td></tr>
        <tr><td>Reference recall</td><td>1.0000</td><td>27 / 27</td><td>met</td></tr>
        <tr><td>Candidate recall</td><td>1.0000</td><td>27 / 27</td><td>met</td></tr>
        <tr><td>Macro-F1</td><td>0.5103</td><td>33 / 66</td><td>not met</td></tr>
        <tr><td>Workload reduction</td><td>0.4242</td><td>28 / 66</td><td>not met</td></tr>
        <tr><td>Useful items</td><td>0.5152</td><td>34 / 66</td><td>not met</td></tr>
      </tbody>
    </table>
  </section>
  <section>
    <h2>What missed</h2>
    <p>Macro-F1, workload reduction, and usefulness missed their preregistered targets. Unsafe out-of-domain assignment and unsupported-derived-item rates are undefined, not zero, because neither metric had an eligible case.</p>
  </section>
  <section>
    <h2>A rejection, not a discovery</h2>
    <p>A looped-transformer candidate remained <code>pending_review</code> until primary-source review found direct overlap with Parcae, STARS, and CART. The human decision was <code>rejected</code>. The preserved next step is a proposed controlled comparison and replication, not a resurrected novelty claim.</p>
  </section>
  <section>
    <h2>Engineering judgment</h2>
    <p>The public repository was rebuilt with a clean lineage, private pilot material stayed outside public Git, claims are bound to executable audits, and both wheel and source distribution are exercised outside the checkout on Python 3.10, 3.11, and 3.12.</p>
  </section>
  <section class="limit-panel">
    <h2>Limits</h2>
    <p>This is one 12-paper, 66-pair suite and does not establish external validity. Validity and novelty remain human-reviewed. <code>5.6 Sol</code> is the frozen backend label; provider model identity was not exposed and is not independently verified.</p>
  </section>
</main>
```

Add direct links in the header/footer to the GitHub release, repository README, locked public report, P8 prior-art case, and reflective essay. Append these scoped styles without changing existing global colors or typography:

```css
.case-study-page {
  width: min(100% - 32px, 980px);
  margin: 0 auto;
  padding: 64px 0 88px;
}
.case-study-hero {
  padding-bottom: 36px;
  border-bottom: 1px solid var(--rule);
}
.case-study-page section {
  padding: 36px 0;
  border-bottom: 1px solid var(--rule);
}
.case-study-page section h2 {
  margin-bottom: 14px;
  font-family: var(--serif);
  font-size: clamp(1.8rem, 4vw, 3rem);
}
.case-study-page section p {
  max-width: 760px;
  color: var(--ink-2);
  font-size: 1.02rem;
  line-height: 1.7;
}
.metric-grid {
  width: 100%;
  margin-top: 22px;
  border-collapse: collapse;
  background: var(--surface);
}
.metric-grid th,
.metric-grid td {
  padding: 12px;
  border: 1px solid var(--rule);
  text-align: left;
}
.metric-grid th {
  color: var(--accent-dark);
  font-family: var(--mono);
  font-size: .72rem;
  letter-spacing: .08em;
  text-transform: uppercase;
}
.decision-timeline {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  background: var(--rule);
  border: 1px solid var(--rule);
}
.decision-timeline > * { padding: 16px; background: var(--surface); }
.limit-panel { padding: 28px !important; background: var(--surface-2); }
@media (max-width: 680px) {
  .metric-grid { font-size: .82rem; }
  .metric-grid th, .metric-grid td { padding: 8px; }
  .decision-timeline { grid-template-columns: 1fr; }
}
```

- [ ] **Step 4: Transform the homepage and resume bundles**

Use `replace_template` with the exact existing source fragments. Replace the homepage paragraph with:

```html
A local research-operations pipeline with schema-validated records, deterministic workflows, and human review gates. On one frozen 12-paper, 66-pair suite it recovered all 27 human-labeled relevant pairs, while macro-F1 (0.5103), workload reduction (0.4242), and usefulness (0.5152) missed their preregistered targets. A looped-transformer candidate was rejected after Parcae, STARS, and CART contradicted its novelty premise. <a href="case-studies/apophenia-machine.html" style="font-style:italic">Technical case study.</a> <a href="https://github.com/zeroexstrat/Apophenia-Machine" style="font-style:italic">GitHub.</a> <a href="writing/azoth.html" style="font-style:italic">Reflective essay.</a>
```

Replace the single resume pilot-count `<li>` with:

```html
<li>On one frozen 12-paper, 66-pair suite, recovered all 27 human-labeled relevant pairs while publishing the missed macro-F1, workload-reduction, and usefulness targets.</li>
```

Update the PDF link from `v4.pdf` to `v5.pdf`. The transformer must refuse if any expected old fragment is absent or duplicated.

Apply the replacements with this one-shot, reviewable invocation:

```bash
python3 - <<'PY'
from pathlib import Path
from scripts.update_bundle_copy import replace_template

OLD_HOME = "A pipeline that ingests papers, exhausts them five layers deep, connects across fields, and drafts hypotheses that sit in triage until a named reviewer promotes them — nothing is auto-accepted. First cycle: 57 papers across ML, physics, philosophy, mathematics, and neuroscience; 5 candidates; one rejected after prior-art review found Parcae, STARS, and CART already there — which means the machine finds real things. The sources went back to nigredo for the next turn of the loop. <a href=\"https://github.com/zeroexstrat/Apophenia-Machine\" style=\"font-style:italic\">Public repo.</a>"
NEW_HOME = "A local research-operations pipeline with schema-validated records, deterministic workflows, and human review gates. On one frozen 12-paper, 66-pair suite it recovered all 27 human-labeled relevant pairs, while macro-F1 (0.5103), workload reduction (0.4242), and usefulness (0.5152) missed their preregistered targets. A looped-transformer candidate was rejected after Parcae, STARS, and CART contradicted its novelty premise. <a href=\"case-studies/apophenia-machine.html\" style=\"font-style:italic\">Technical case study.</a> <a href=\"https://github.com/zeroexstrat/Apophenia-Machine\" style=\"font-style:italic\">GitHub.</a> <a href=\"writing/azoth.html\" style=\"font-style:italic\">Reflective essay.</a>"
OLD_RESUME = "<li>Processed 57 paper records across ML, physics, philosophy, mathematics, and neuroscience; generated 54 exhaustion records, 91 connection artifacts, and 5 candidate hypotheses under schema and gate checks.</li>"
NEW_RESUME = "<li>On one frozen 12-paper, 66-pair suite, recovered all 27 human-labeled relevant pairs while publishing the missed macro-F1, workload-reduction, and usefulness targets.</li>"

replace_template(Path("index.html"), {OLD_HOME: NEW_HOME})
replace_template(Path("resume.html"), {
    OLD_RESUME: NEW_RESUME,
    "assets/rafael-de-almeida-operations-ai-systems-resume-v4.pdf":
        "assets/rafael-de-almeida-operations-ai-systems-resume-v5.pdf",
})
PY
```

- [ ] **Step 5: Update the maintained Markdown resume source**

Copy v3 to v5, replace only the pilot inventory bullet with the exact balanced bullet, and retain the pipeline and prior-art bullets. Update any download/version references in `README.md`.

- [ ] **Step 6: Generate and visually verify the v5 PDF using the PDF skill**

Use the existing one-page v4 visual system and the v5 Markdown source. Generate `assets/rafael-de-almeida-operations-ai-systems-resume-v5.pdf` with ReportLab, then render it:

```bash
pdfinfo assets/rafael-de-almeida-operations-ai-systems-resume-v5.pdf
pdftotext assets/rafael-de-almeida-operations-ai-systems-resume-v5.pdf - | rg -n "12-paper|66-pair|macro-F1|workload-reduction|usefulness|57 paper"
pdftoppm -png -r 150 assets/rafael-de-almeida-operations-ai-systems-resume-v5.pdf /tmp/azoth-resume-v5
```

Expected: one letter-size page; new balanced bullet present; old 57-paper inventory absent; rendered page has no clipping, overlap, missing glyphs, or unintended second page.

- [ ] **Step 7: Add one contextual link to the reflective essay**

After the essay title/subtitle, add:

```html
<p class="technical-companion">Looking for the measured engineering record? Read the <a href="../case-studies/apophenia-machine.html">Apophenia Machine technical case study</a>.</p>
```

Do not alter the essay body.

- [ ] **Step 8: Run portfolio GREEN checks and local link server**

```bash
python3 -m unittest tests/test_apophenia_portfolio.py -v
python3 scripts/check_apophenia_portfolio.py
python3 -m http.server 8080
```

Expected: tests pass, `Portfolio Apophenia audit: PASS`, and the server exposes `/`, `/resume.html`, `/case-studies/apophenia-machine.html`, and `/writing/azoth.html`.

- [ ] **Step 9: Browser QA before commit**

At 1440×900 and 390×844, inspect all four routes. Record screenshots under the existing ignored audit folder. In browser evaluation, require:

```javascript
({
  overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  title: document.title,
  h1: document.querySelector('h1')?.textContent?.trim(),
  brokenImages: [...document.images].filter(img => !img.complete || img.naturalWidth === 0).map(img => img.src)
})
```

Expected: `overflow: false`, correct title/H1, no broken images, no console errors, and no visible bundle overlay.

- [ ] **Step 10: Commit Task 5**

```bash
git add index.html resume.html writing/azoth.html case-studies/apophenia-machine.html assets/portfolio.css assets/data/apophenia-v0.2.0.json assets/rafael-de-almeida-operations-ai-systems-resume-v5.md assets/rafael-de-almeida-operations-ai-systems-resume-v5.pdf README.md scripts tests
git commit -m "feat: publish Apophenia Machine case study"
```

---

### Task 6: Apophenia repository acceptance, merge, push, and GitHub release

**Files:**
- Modify only if verification reveals defects: files from Tasks 1-3
- Generated but untracked: `dist/*`, downloaded release assets, clean-clone directories

**Interfaces:**
- Consumes: accepted feature branch and exact release notes.
- Produces: pushed `main`, immutable `v0.2.0`, GitHub release assets, checksums, and exact remote proof.

- [ ] **Step 1: Run the full local acceptance bundle on the feature branch**

```bash
cd "$APOPHENIA_REPO"
uv sync --python 3.12 --extra dev
uv run --python 3.12 pytest -q
for check in scripts/check_*.py; do
  case "$check" in
    scripts/check_wheel_install.py|scripts/check_public_lineage.py) continue ;;
  esac
  uv run --python 3.12 python "$check"
done
uv run --python 3.12 python scripts/check_benchmark_protocol.py --benchmark-root benchmarks/operations-decision-support-v1 --repo-root .
uv run --python 3.12 python scripts/hardening_audit.py --project-root .
uv run --python 3.12 python -m compileall athanasor scripts
git diff --check
python3 athanasor/vigil/verify.py verify
```

Expected: every command exits 0 and all seven Vigil gates pass. If a no-argument check requires explicit arguments, run its maintained canonical invocation recorded in prior plans rather than skipping it.

`check_public_lineage.py` is intentionally excluded: it is the P4 cutover transaction
checker and requires an exactly three-commit reconstructed lineage. P9 is additive
history; its release lineage proof is the audited final tree, squash integration of
the private feature branch, exact remote SHA, and the fresh single-branch clone in
Step 5.

- [ ] **Step 2: Build and verify final local release artifacts**

```bash
rm -rf dist
uv build --wheel --sdist --out-dir dist
uv run --python 3.12 python scripts/check_wheel_install.py \
  --wheel 'dist/azoth-*.whl' --sdist 'dist/azoth-*.tar.gz' \
  --expected-version 0.2.0 --python 3.10 --python 3.11 --python 3.12
```

Expected: both artifacts pass on all three interpreters.

- [ ] **Step 3: Commit any verification-driven corrections, then fast-forward local main**

```bash
git status --short
git switch main
git merge --ff-only codex/p9-release-deployment
git status --short --branch
```

Expected: clean local `main` at the accepted P9 commit.

- [ ] **Step 4: Rerun the full suite and Vigil on merged main**

Run the commands from Step 1 plus the artifact smoke from Step 2. Do not push until the merged state passes.

- [ ] **Step 5: Push main and verify the remote ref**

```bash
git push origin main
LOCAL_SHA=$(git rev-parse HEAD)
REMOTE_SHA=$(git ls-remote origin refs/heads/main | cut -f1)
test "$LOCAL_SHA" = "$REMOTE_SHA"
```

Expected: exact SHA equality.

- [ ] **Step 6: Wait for hosted hardening on the exact SHA**

```bash
SHA=$(git rev-parse HEAD)
gh run list --repo zeroexstrat/Apophenia-Machine --branch main --commit "$SHA" --limit 10
RUN_ID=$(gh run list --repo zeroexstrat/Apophenia-Machine --branch main --commit "$SHA" --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID" --repo zeroexstrat/Apophenia-Machine --exit-status
gh run view "$RUN_ID" --repo zeroexstrat/Apophenia-Machine --json headSha,conclusion,jobs,url
```

Expected: exact `headSha`, overall `success`, and three successful Python jobs.

- [ ] **Step 7: Build assets from a fresh clone of the remote SHA**

```bash
TMP=$(mktemp -d)
git clone --depth 1 https://github.com/zeroexstrat/Apophenia-Machine.git "$TMP/repo"
cd "$TMP/repo"
test "$(git rev-parse HEAD)" = "$SHA"
uv sync --python 3.12 --extra dev
uv run --python 3.12 pytest -q
uv build --wheel --sdist --out-dir dist
uv run --python 3.12 python scripts/check_wheel_install.py \
  --wheel 'dist/azoth-*.whl' --sdist 'dist/azoth-*.tar.gz' \
  --expected-version 0.2.0 --python 3.10 --python 3.11 --python 3.12
cd dist
shasum -a 256 azoth-0.2.0-py3-none-any.whl azoth-0.2.0.tar.gz > SHA256SUMS.txt
```

Expected: clean-clone suite and six artifact/interpreter pairs pass.

- [ ] **Step 8: Create and push immutable annotated tag**

```bash
cd "$APOPHENIA_REPO"
git tag -a v0.2.0 "$SHA" -m "Azoth v0.2.0"
git push origin refs/tags/v0.2.0
test "$(git rev-list -n 1 v0.2.0)" = "$SHA"
test "$(git ls-remote origin refs/tags/v0.2.0^{} | cut -f1)" = "$SHA"
```

Expected: local and remote peeled tag targets equal the accepted SHA.

- [ ] **Step 9: Create and verify the GitHub release**

```bash
gh release create v0.2.0 \
  "$TMP/repo/dist/azoth-0.2.0-py3-none-any.whl" \
  "$TMP/repo/dist/azoth-0.2.0.tar.gz" \
  "$TMP/repo/dist/SHA256SUMS.txt" \
  --repo zeroexstrat/Apophenia-Machine \
  --title "Azoth v0.2.0" \
  --notes-file docs/releases/v0.2.0.md \
  --verify-tag
gh release view v0.2.0 --repo zeroexstrat/Apophenia-Machine --json url,tagName,targetCommitish,isDraft,isPrerelease,assets
```

Expected: non-draft, non-prerelease, correct tag, and exactly three named assets.

- [ ] **Step 10: Download and independently verify published assets**

```bash
DL=$(mktemp -d)
gh release download v0.2.0 --repo zeroexstrat/Apophenia-Machine --dir "$DL"
cd "$DL"
shasum -a 256 -c SHA256SUMS.txt
cd "$APOPHENIA_REPO"
uv run --python 3.12 python scripts/check_wheel_install.py \
  --wheel "$DL/azoth-0.2.0-py3-none-any.whl" \
  --sdist "$DL/azoth-0.2.0.tar.gz" \
  --expected-version 0.2.0 --python 3.10 --python 3.11 --python 3.12
```

Expected: checksums and all six published artifact/interpreter pairs pass.

---

### Task 7: Portfolio deployment, GitHub metadata, and production verification

**Files:**
- Modify only if live verification reveals defects: portfolio files from Tasks 4-5
- Modify GitHub metadata through `gh repo edit`

**Interfaces:**
- Consumes: live `v0.2.0` release and accepted portfolio branch.
- Produces: deployed portfolio, verified live routes, and final GitHub metadata.

- [ ] **Step 1: Re-run the complete local portfolio audit**

```bash
cd "$PORTFOLIO_REPO"
python3 -m unittest tests/test_apophenia_portfolio.py -v
python3 scripts/check_apophenia_portfolio.py
git diff --check
git status --short --branch
```

Expected: all tests pass, audit PASS, clean committed branch.

- [ ] **Step 2: Fast-forward portfolio main and push**

```bash
git switch main
git merge --ff-only codex/p9-apophenia-case-study
python3 -m unittest tests/test_apophenia_portfolio.py -v
python3 scripts/check_apophenia_portfolio.py
git push origin main
SITE_SHA=$(git rev-parse HEAD)
test "$SITE_SHA" = "$(git ls-remote origin refs/heads/main | cut -f1)"
```

Expected: exact remote SHA equality.

- [ ] **Step 3: Wait for the Pages deployment**

```bash
RUN_ID=$(gh run list --repo zeroexstrat/0xstrategies --branch main --commit "$SITE_SHA" --json databaseId,workflowName --jq '[.[] | select(.workflowName=="pages-build-deployment")][0].databaseId')
gh run watch "$RUN_ID" --repo zeroexstrat/0xstrategies --exit-status
gh run view "$RUN_ID" --repo zeroexstrat/0xstrategies --json headSha,conclusion,url
```

Expected: successful Pages run for the exact site SHA.

- [ ] **Step 4: Verify cache-busted production content and links**

```bash
STAMP=$(date +%s)
for route in / /resume.html /case-studies/apophenia-machine.html /writing/azoth.html; do
  curl -fsSL "https://0xstrategies.com${route}?v=$STAMP" -o "/tmp/site-$(echo "$route" | tr '/.' '__').html"
done
rg -n "12-paper|66-pair|macro-F1|case-studies/apophenia-machine|v0.2.0" /tmp/site-*.html
! rg -n "57 papers across ML, physics, philosophy, mathematics, and neuroscience; 5 candidates|__bundler_err|\[bundle\]" /tmp/site-*.html
```

Expected: new release/case content present and old pilot/overlay strings absent.

- [ ] **Step 5: Browser-verify production desktop and mobile**

Repeat Task 5 Step 9 against `https://0xstrategies.com` routes, with cache-busting. Confirm release, GitHub, case-study, resume PDF, and essay links. Capture production screenshots and console output in the ignored audit folder.

- [ ] **Step 6: Update and verify GitHub metadata**

```bash
gh repo edit zeroexstrat/Apophenia-Machine \
  --description "A local, schema-driven research operations pipeline that uses deterministic workflows and human review gates to turn technical documents into validated evidence records, ranked connections, and auditable decisions." \
  --homepage "https://0xstrategies.com/case-studies/apophenia-machine.html" \
  --add-topic python --add-topic cli --add-topic research-automation \
  --add-topic operations-research --add-topic human-in-the-loop \
  --add-topic knowledge-management --add-topic evidence
gh repo view zeroexstrat/Apophenia-Machine --json description,homepageUrl,repositoryTopics,defaultBranchRef,isPrivate,url
```

Expected: exact description/homepage, the seven topics, default `main`, and `isPrivate: false`.

---

### Task 8: Roadmap reconciliation, Vigil close, and completion audit

**Files:**
- Modify: `PROJECT_ROADMAP.md`
- Modify as generated by Vigil: `athanasor/lapis/state.json`
- Modify as generated by Vigil: `athanasor/lapis/codex.md`

**Interfaces:**
- Consumes: exact repository SHA, CI run URL, release URL/assets, site SHA, Pages run URL, production browser proof, test totals, and Vigil reports.
- Produces: final durable P9 completion record with no false next task.

- [ ] **Step 1: Update the roadmap with exact evidence**

Mark P9 completed only after Tasks 6-7 pass. Update the active-session table, append verification rows, decision log entries, and completed-session row with:

```text
P9 implementation SHA
GitHub hardening run ID and URL
v0.2.0 tag target and release URL
wheel/sdist/checksum asset names and verified digests
fresh-clone and downloaded-asset Python 3.10-3.12 proof
portfolio SHA and Pages run ID/URL
verified production routes and desktop/mobile dimensions
test totals and audit names
```

Set the roadmap's final state to `v0.2.0 released; portfolio deployed`. Do not invent a P10 task. State remaining limitations as release constraints, not unfinished P9 deliverables.

- [ ] **Step 2: Commit roadmap and generated close-state changes transactionally**

```bash
cd "$APOPHENIA_REPO"
git switch main
git add PROJECT_ROADMAP.md
git commit -m "docs: close P9 release and deployment"
python3 athanasor/vigil/verify.py verify
python3 athanasor/vigil/verify.py close
git status --short
```

If Vigil updates tracked state, stage only `athanasor/lapis/state.json` and `athanasor/lapis/codex.md`, commit them, then rerun `verify` and `close` until the committed tree is clean and all seven gates pass.

- [ ] **Step 3: Push final completion state and reverify remote SHA/CI**

```bash
git push origin main
FINAL_SHA=$(git rev-parse HEAD)
test "$FINAL_SHA" = "$(git ls-remote origin refs/heads/main | cut -f1)"
FINAL_RUN=$(gh run list --repo zeroexstrat/Apophenia-Machine --branch main --commit "$FINAL_SHA" --json databaseId --jq '.[0].databaseId')
gh run watch "$FINAL_RUN" --repo zeroexstrat/Apophenia-Machine --exit-status
```

Because `v0.2.0` is immutable and points at the release commit, the post-release roadmap-only closeout commit may advance `main`; record both the tag SHA and final `main` SHA explicitly.

- [ ] **Step 4: Perform the requirement-by-requirement completion audit**

Re-read `docs/superpowers/specs/2026-07-13-p9-release-deployment-design.md` acceptance criteria 1-12. For each item, record direct evidence from Git, GitHub, release downloads, local tests, production HTTP/browser checks, portfolio Git/Pages, roadmap, and Vigil. Treat missing or indirect evidence as incomplete and continue work.

- [ ] **Step 5: Remove merged feature branches only after remote proof**

```bash
git branch -d codex/p9-release-deployment
git -C "$PORTFOLIO_REPO" branch -d codex/p9-apophenia-case-study
```

Retain audit screenshots and downloaded release verification outside Git until the final handoff is delivered.
