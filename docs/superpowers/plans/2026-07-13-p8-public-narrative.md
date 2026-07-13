# P8 Public Narrative Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a five-minute Azoth workflow, exact bounded P7 evidence, and a source-backed looped-transformer rejection/reframe case without exceeding the human-review or model-provenance boundary.

**Architecture:** Keep the README as the concise product entry point and put the complete rejection trace in one linked case-study document. Add a deterministic public-narrative auditor that derives expected metric rows from the committed P7 `locked-comparison.json`, then verifies the live README and case-study scope/provenance language.

**Tech Stack:** Python 3.10-3.12, standard-library JSON/pathlib/argparse, Markdown, pytest, existing Azoth CLI and Vigil.

## Global Constraints

- Work only on `P8-T1 — Public README and rejection/reframe case study` at High + Ultra review effort.
- Do not change P5-P7 sources, gold, prompts, metrics, thresholds, runs, annotations, scores, or results.
- Every metric claim must be scoped to the frozen 12-paper, 66-pair suite and match the committed numerator, denominator, uncertainty, and threshold outcome.
- Preserve that scientific validity and novelty remain human-reviewed.
- Preserve that `5.6 Sol` is a frozen backend label whose provider model identity was not exposed or independently verified.
- Do not track private pilot IDs, paths, raw artifacts, source bytes, rationales, pair labels, or failure details.
- The public case is a sanitized state-transition narrative supported by public primary sources, not a new research result.
- The five-minute input is newly authored fictional text and is not benchmark evidence.
- Do not perform P9 release, website, GitHub metadata, or package-version work.

---

### Task 1: Public narrative auditor

**Files:**
- Create: `scripts/check_public_narrative.py`
- Create: `tests/test_public_narrative.py`

**Interfaces:**
- Consumes: README text, case-study text, and the parsed committed `locked-comparison.json`.
- Produces: `metric_rows(comparison: dict[str, object]) -> list[str]`, `audit_public_narrative(readme: str, case_study: str, comparison: dict[str, object]) -> list[str]`, and a CLI returning `0` on PASS, `1` on findings, `2` on unreadable/invalid inputs.

- [ ] **Step 1: Write failing auditor tests**

Create tests that import the missing module and specify these behaviors:

```python
def test_live_public_narrative_matches_locked_results() -> None:
    comparison = json.loads(COMPARISON.read_text(encoding="utf-8"))
    errors = audit_public_narrative(
        README.read_text(encoding="utf-8"),
        CASE_STUDY.read_text(encoding="utf-8"),
        comparison,
    )
    assert errors == []


def test_metric_drift_is_rejected() -> None:
    comparison = json.loads(COMPARISON.read_text(encoding="utf-8"))
    readme = valid_readme(comparison).replace("0.5103", "0.9000", 1)
    assert any("macro_f1" in error for error in audit_public_narrative(readme, valid_case(), comparison))


def test_case_requires_rejection_sources_and_proposed_reframe() -> None:
    comparison = json.loads(COMPARISON.read_text(encoding="utf-8"))
    case = valid_case().replace("https://arxiv.org/html/2604.12946v1", "")
    assert any("Parcae" in error for error in audit_public_narrative(valid_readme(comparison), case, comparison))


@pytest.mark.parametrize("phrase", ["we discovered", "novel contribution", "experiment confirmed"])
def test_case_rejects_unsupported_completion_language(phrase: str) -> None:
    comparison = json.loads(COMPARISON.read_text(encoding="utf-8"))
    assert audit_public_narrative(valid_readme(comparison), valid_case() + phrase, comparison)
```

Also cover missing 12-paper/66-pair scope, missing provider-identity limitation, missing human validity/novelty boundary, case state other than rejected, missing comparison/replication wording, CLI PASS/FAIL/ERROR behavior, and sorted deterministic diagnostics.

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run --python 3.12 pytest tests/test_public_narrative.py -q`

Expected: collection fails because `scripts/check_public_narrative.py` does not exist.

- [ ] **Step 3: Implement the minimal auditor**

Use these stable contracts:

```python
SELECTED_METRICS = (
    "macro_f1", "unsafe_ood_assignment", "claim_precision",
    "reference_recall", "candidate_recall", "workload_reduction",
    "precision_at_5", "ndcg_at_10", "evidence_support",
    "supported_items", "useful_items", "redundancy",
    "unsupported_derived_items",
)

DIRECT_SOURCES = {
    "Parcae": "https://arxiv.org/html/2604.12946v1",
    "STARS": "https://arxiv.org/html/2605.26733v1",
    "CART": "https://arxiv.org/abs/2606.01495",
}

def _decimal(value: object) -> str:
    return "undefined" if value is None else f"{float(value):.4f}"

def _count(value: object) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:.4f}"

def metric_rows(comparison: dict[str, object]) -> list[str]:
    runs = comparison.get("runs")
    if not isinstance(runs, list):
        raise ValueError("/runs: expected a list")
    model = next(
        (run for run in runs if isinstance(run, dict) and run.get("run_id") == "model_5_6_sol"),
        None,
    )
    if model is None or not isinstance(model.get("metrics"), list):
        raise ValueError("/runs/model_5_6_sol: missing model metrics")
    metrics = {
        metric.get("name"): metric
        for metric in model["metrics"]
        if isinstance(metric, dict) and isinstance(metric.get("name"), str)
    }
    if set(metrics) != set(SELECTED_METRICS):
        raise ValueError("/runs/model_5_6_sol/metrics: expected the exact 13 metrics")
    rows: list[str] = []
    for name in SELECTED_METRICS:
        metric = metrics[name]
        uncertainty = metric.get("uncertainty_result")
        if not isinstance(uncertainty, dict):
            raise ValueError(f"/runs/model_5_6_sol/metrics/{name}/uncertainty_result: missing")
        threshold = {True: "met", False: "not met", None: "undefined"}.get(
            metric.get("threshold_met")
        )
        if threshold is None:
            raise ValueError(f"/runs/model_5_6_sol/metrics/{name}/threshold_met: invalid")
        rows.append(
            f"| `{name}` | {_decimal(metric.get('value'))} | "
            f"{_count(metric.get('numerator'))} / {_count(metric.get('denominator'))} | "
            f"{_decimal(uncertainty.get('lower'))}–{_decimal(uncertainty.get('upper'))} | "
            f"{threshold} |"
        )
    return rows

def audit_public_narrative(
    readme: str,
    case_study: str,
    comparison: dict[str, object],
) -> list[str]:
    errors: list[str] = []
    try:
        expected_rows = metric_rows(comparison)
    except ValueError as exc:
        return [f"/comparison: {exc}"]
    for name, row in zip(SELECTED_METRICS, expected_rows, strict=True):
        if row not in readme:
            errors.append(f"/README/metrics/{name}: exact locked row is missing")
    required_readme = {
        "/README/scope/papers": "12-paper",
        "/README/scope/pairs": "66-pair",
        "/README/provenance/provider": "provider model identity",
        "/README/authority": "validity and novelty remain human-reviewed",
    }
    folded_readme = readme.casefold()
    for address, phrase in required_readme.items():
        if phrase.casefold() not in folded_readme:
            errors.append(f"{address}: missing {phrase!r}")
    demo = readme.find("## Five-minute demo")
    architecture = readme.find("## Architecture")
    if demo < 0 or architecture < 0 or demo > architecture:
        errors.append("/README/order: Five-minute demo must precede Architecture")
    folded_case = case_study.casefold()
    required_case = {
        "/case/status/candidate": "pending_review",
        "/case/status/decision": "rejected",
        "/case/reframe/comparison": "comparison",
        "/case/reframe/replication": "replication",
    }
    for address, phrase in required_case.items():
        if phrase.casefold() not in folded_case:
            errors.append(f"{address}: missing {phrase!r}")
    if folded_case.find("pending_review") > folded_case.find("rejected"):
        errors.append("/case/status/order: candidate review state must precede rejection")
    for source, url in DIRECT_SOURCES.items():
        if url not in case_study:
            errors.append(f"/case/sources/{source}: missing primary-source URL")
    for phrase in ("we discovered", "novel contribution", "experiment confirmed"):
        if phrase in folded_case:
            errors.append(f"/case/unsupported_claim: prohibited phrase {phrase!r}")
    return sorted(dict.fromkeys(errors))
```

The CLI defaults to repository-relative live paths and accepts explicit `--readme`, `--case-study`, and `--comparison` overrides for testing. It prints `Public narrative audit: PASS` or sorted findings under `Public narrative audit: FAIL`.

- [ ] **Step 4: Run focused tests**

Run: `uv run --python 3.12 pytest tests/test_public_narrative.py -q`

Expected: mutation tests pass; the live-document test remains red until Task 2 creates the approved content.

---

### Task 2: Five-minute README and rejection/reframe case

**Files:**
- Create: `examples/five-minute-demo/queueing-note.txt`
- Create: `docs/case-studies/looped-transformer-prior-art.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: the committed P7 comparison and public primary-source pages.
- Produces: one runnable local demo, one compact exact metric table, and one linked case-study narrative that passes `audit_public_narrative`.

- [ ] **Step 1: Add the fictional demo input**

Create a short, explicitly fictional note with `Title`, `Abstract`, `Method`, and `Conclusion` sections. Its claim is limited to a toy queue-priority rule and it must contain the exact marker `FICTIONAL DEMO INPUT — NOT RESEARCH EVIDENCE`.

- [ ] **Step 2: Write the case study**

Use these exact sections:

```markdown
# When a plausible gap fails prior-art review

## Candidate, not finding
## Why review was mandatory
## Primary-source contradiction
## Human decision: reject the novelty claim
## Reframe: controlled comparison and replication
## What this case demonstrates
## Limits
```

State the candidate premise once, immediately label it `pending_review`, cite the three direct sources plus supporting residual-scaling/Lipschitz context, record the human decision as rejected, and propose—not claim to have run—the controlled comparison from the design spec. State that the search rejects this premise but is not a literature-wide novelty proof.

- [ ] **Step 3: Reorganize the README**

Lead with product position and `## Five-minute demo`. Include the exact commands from the design spec and a concise proof/limit paragraph. Insert the exact rows returned by `metric_rows`, link the complete P7 results, add engineering decisions, summarize and link the rejection case, then retain the existing installation, workflow, Vigil, verification, limitations, and license material without contradictory P5/P6-era language.

- [ ] **Step 4: Run auditor and tests to verify GREEN**

Run:

```bash
uv run --python 3.12 pytest tests/test_public_narrative.py -q
uv run --python 3.12 python scripts/check_public_narrative.py
```

Expected: all focused tests pass and the CLI prints `Public narrative audit: PASS`.

---

### Task 3: Isolated demo proof and maintained checks

**Files:**
- Modify only if a demonstrated defect requires it; otherwise verification-only.

**Interfaces:**
- Consumes: the exact README demo block and tracked P8 files.
- Produces: fresh isolated runtime proof plus complete regression evidence.

- [ ] **Step 1: Run the exact demo from a clean tracked copy**

Create a temporary directory with `git archive HEAD`, overlay the uncommitted P8 files, create a Python 3.12 virtual environment, install editable, run the README demo commands without model/network use after installation, and assert:

```bash
test "$(wc -l < .demo-workspace/albedo/registry.jsonl)" -eq 1
grep -q '"status": "ingested_only"\|"status":"ingested_only"' .demo-workspace/albedo/registry.jsonl
python -m athanasor.vigil.verify verify
```

Expected: one registry row and Vigil PASS.

- [ ] **Step 2: Run focused and full verification**

Run:

```bash
uv run --python 3.12 pytest tests/test_public_narrative.py -q
uv run --python 3.12 pytest -q
for check in scripts/check_*.py; do uv run --python 3.12 python "$check"; done
uv run --python 3.12 python scripts/check_public_tree.py
uv run --python 3.12 python scripts/hardening_audit.py
uv run --python 3.12 python -m compileall athanasor scripts tests
git diff --check
python3 athanasor/vigil/verify.py verify
```

Expected: every command exits zero; no claim of completion before reading the full output.

---

### Task 4: Durable P8 closeout

**Files:**
- Modify: `PROJECT_ROADMAP.md`
- Generated by Vigil close if applicable: `athanasor/lapis/state.json`, `athanasor/lapis/codex.md`, and ignored Vigil report.

**Interfaces:**
- Consumes: exact implementation SHA and final verification counts.
- Produces: P8 completion record and exactly one P9 next task.

- [ ] **Step 1: Update the roadmap after green verification**

Mark P8 completed, make the active-session section P8-specific, append verification and completed-session rows, and set the next task to `P9-T1 — v0.2.0, GitHub metadata, website case study, and deployment`. Preserve P7 rows unchanged.

- [ ] **Step 2: Re-run the narrative/full checks affected by roadmap changes**

Run at minimum:

```bash
uv run --python 3.12 pytest tests/test_public_narrative.py tests/test_public_tree.py -q
uv run --python 3.12 python scripts/check_public_narrative.py
uv run --python 3.12 python scripts/check_public_tree.py
git diff --check
python3 athanasor/vigil/verify.py verify
python3 athanasor/vigil/verify.py close
git status --short
```

Expected: all checks and both Vigil modes pass; only intentional P8 tracked files remain modified before commit.

- [ ] **Step 3: Commit P8 intentionally**

Stage only the P8 spec/plan, auditor/test, demo fixture, README, case study, roadmap, and any tracked Vigil close state. Commit with `docs: publish P8 evidence narrative`.

- [ ] **Step 4: Verify committed state**

Run the full verification bundle again from the committed tree, including `git status --short`, and record the exact commit SHA and counts. Do not push unless separately authorized.

## Plan self-review

- Spec coverage: every P8 roadmap acceptance item maps to Tasks 1-4.
- Scope: no P9 release/site/metadata work and no P5-P7 mutation.
- Type consistency: the auditor consumes parsed comparison mappings and returns sorted string findings; tests and CLI use the same functions.
- Placeholder check: no deferred implementation or acceptance placeholders remain.
