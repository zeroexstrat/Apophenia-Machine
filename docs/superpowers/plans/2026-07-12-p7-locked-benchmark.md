# P7 Locked Benchmark Runs and Adjudication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute and seal the real Operations Decision Support v1 model and six deterministic baseline runs before gold access, then score, annotate, compare, and report them without retuning.

**Architecture:** Add a gold-blind P7 execution layer around the existing P6 prepared/run/score contracts. A public execution manifest freezes missing model-adapter and baseline semantics; focused modules generate complete response bundles, seal a seven-run private lock manifest, bind scoring to that lock, create explicit annotation templates, and render deterministic comparison and failure-analysis artifacts.

**Tech Stack:** Python 3.10–3.12, Click, PyYAML, NumPy, existing Azoth benchmark contracts, pytest, `uv`, Vigil.

## Global Constraints

- Work only on `P7-T1 — Locked benchmark runs and adjudication` at Ultra effort.
- Keep P5 sources, source versions, private-gold commitment, Rafael-authored labels, rubric, metric definitions, thresholds, uncertainty rules, blinded packet schema, and no-retuning rule unchanged.
- Commit the P7 execution amendment before preparing or generating any real run.
- Do not read real gold content, annotations, score artifacts, or prior real responses before all seven run artifacts are sealed.
- All seven runs consume one byte-identical prepared artifact and cover all 66 canonical pairs.
- Record only model provenance the execution surface can prove; do not present the declared `5.6 Sol` label as independently verified provider identity.
- Keep third-party PDFs, prepared packets, raw responses, runs, private gold, annotations, and full private reports outside Git.
- Missing metric populations remain null with numerator and denominator zero.
- Missed thresholds are reported without prompt, source, formula, threshold, or output changes.
- Preserve Python 3.10–3.12, installed-wheel execution, public-tree privacy, and all seven Vigil gates.

## File Map

- Create `benchmarks/operations-decision-support-v1/execution-manifest.yaml`: immutable P7 execution semantics and pre-run attestation.
- Create `athanasor/benchmark/execution.py`: execution-manifest validation, deterministic baselines, model-response validation, and adaptation.
- Create `athanasor/benchmark/locking.py`: private lock assembly and independent verification.
- Create `athanasor/benchmark/evaluation.py`: annotation-template, score-lock binding, comparison, and failure analysis.
- Modify `athanasor/benchmark/artifacts.py`: P7 artifact constants and validators.
- Modify `athanasor/benchmark/scoring.py`: optional required P7 lock binding for real P7 scores.
- Modify `athanasor/benchmark/cli.py`: `baseline`, `adapt`, `lock`, `annotations`, and `compare` commands plus lock-aware `score`.
- Modify `athanasor/benchmark/__init__.py`: export stable P7 interfaces.
- Create `tests/test_benchmark_execution.py`, `tests/test_benchmark_locking.py`, and `tests/test_benchmark_evaluation.py`.
- Modify `tests/test_benchmark_cli.py`, `tests/test_benchmark_scoring.py`, `tests/test_wheel_install.py`, `scripts/check_wheel_install.py`, `benchmarks/operations-decision-support-v1/README.md`, `README.md`, and `PROJECT_ROADMAP.md`.
- Create public aggregate fixtures only after real scoring under `benchmarks/operations-decision-support-v1/results/`.

---

### Task 1: Freeze and validate the P7 execution manifest

**Files:**
- Create: `benchmarks/operations-decision-support-v1/execution-manifest.yaml`
- Create: `athanasor/benchmark/execution.py`
- Modify: `athanasor/benchmark/artifacts.py`
- Create: `tests/test_benchmark_execution.py`

**Interfaces:**
- Consumes: public P5/P6 benchmark bundle and execution-manifest mapping.
- Produces: `EXECUTION_MANIFEST_VERSION`, `RUN_IDS`, `load_execution_manifest(path) -> dict[str, Any]`, `validate_execution_manifest(payload, benchmark_root) -> list[str]`, and `execution_manifest_digest(payload) -> str`.

- [ ] **Step 1: Write failing manifest validation tests**

```python
def test_live_execution_manifest_binds_public_freeze_before_runs() -> None:
    payload = load_mapping(BENCHMARK_ROOT / "execution-manifest.yaml")
    assert validate_execution_manifest(payload, BENCHMARK_ROOT) == []
    assert payload["status"] == "frozen_before_real_runs"
    assert payload["seed"] == 5607
    assert [row["run_id"] for row in payload["runs"]] == list(RUN_IDS)


def test_manifest_rejects_formula_or_public_digest_drift() -> None:
    payload = deepcopy(execution_manifest_fixture())
    payload["baselines"]["shared_tag"]["candidate_rule"] = "always"
    assert any("candidate_rule" in error for error in validate_execution_manifest(payload, BENCHMARK_ROOT))
```

- [ ] **Step 2: Run RED**

Run: `uv run --python 3.12 pytest tests/test_benchmark_execution.py -q`

Expected: collection fails because `athanasor.benchmark.execution` and the manifest do not exist.

- [ ] **Step 3: Implement the exact manifest and validator**

The manifest must bind the five public digests already copied into prepared artifacts, seed `5607`, canonical pair order, the model run, six named baseline runs, exact formulas from the design, adapter mapping, lock requirements, and pre-run attestation. Reject unknown fields, duplicate/missing run IDs, changed thresholds, noncanonical formulas, a non-frozen status, or a mismatched public digest.

```python
RUN_IDS = (
    "model_5_6_sol",
    "deterministic_routing",
    "all_pairs",
    "shared_tag",
    "hash_embedding",
    "current_score",
    "fixed_seed_random",
)


def execution_manifest_digest(payload: dict[str, Any]) -> str:
    errors = validate_execution_manifest_shape(payload)
    if errors:
        raise BenchmarkArtifactError("invalid execution manifest: " + "; ".join(errors))
    return canonical_digest(payload)
```

- [ ] **Step 4: Verify GREEN and commit**

Run: `uv run --python 3.12 pytest tests/test_benchmark_execution.py -q`

Expected: all Task 1 tests pass.

```bash
git add benchmarks/operations-decision-support-v1/execution-manifest.yaml athanasor/benchmark/execution.py athanasor/benchmark/artifacts.py tests/test_benchmark_execution.py
git commit -m "feat: freeze P7 execution contract"
```

---

### Task 2: Generate all six deterministic baselines

**Files:**
- Modify: `athanasor/benchmark/execution.py`
- Modify: `tests/test_benchmark_execution.py`

**Interfaces:**
- Consumes: one validated prepared artifact, validated execution manifest, run ID, and seed.
- Produces: `generate_baseline(prepared, manifest, run_id) -> dict[str, Any]` returning a P6-valid locked run.

- [ ] **Step 1: Write exact fictional-baseline tests**

```python
@pytest.mark.parametrize("run_id", RUN_IDS[1:])
def test_each_baseline_is_complete_deterministic_and_gold_blind(run_id: str, tmp_path: Path) -> None:
    prepared = prepared_fixture(tmp_path)
    manifest = execution_manifest_fixture(synthetic=True)
    first = generate_baseline(prepared, manifest, run_id)
    second = generate_baseline(deepcopy(prepared), deepcopy(manifest), run_id)
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert validate_run(first) == []
    assert len(first["results"]) == 15
    assert not recursive_keys(first) & set(FORBIDDEN_GOLD_FIELDS)


def test_fixed_seed_random_sequence_is_frozen(tmp_path: Path) -> None:
    run = generate_baseline(prepared_fixture(tmp_path), execution_manifest_fixture(synthetic=True), "fixed_seed_random")
    assert [row["predicted_label"] for row in run["results"]] == [2, 2, 2, 0, 2, 3, 2, 1, 3, 2, 1, 3, 1, 3, 3]
```

- [ ] **Step 2: Run RED**

Run: `uv run --python 3.12 pytest tests/test_benchmark_execution.py -q -k 'baseline or random'`

Expected: fails because `generate_baseline` is absent.

- [ ] **Step 3: Implement formulas without gold APIs**

Implement exact normalization, generic-tag removal, SHA-256 fallback vectors, cosine similarity, current visible-token overlap, production routing constants, fixed-seed random labels/scores, and shared rank assignment. Hash-embedding labels use the frozen cut points `0.00`, `0.25`, and `0.50`. Deterministic routing uses `max(max(0, cosine_similarity), high_signal_match, min(1, shared_tag_count / strong_overlap_count))`. Each backend object includes `run_id`, `execution_manifest_sha256`, algorithm version, and only proved implementation metadata. Baselines emit `items: []`.

- [ ] **Step 4: Verify GREEN and commit**

Run: `uv run --python 3.12 pytest tests/test_benchmark_execution.py tests/test_benchmark_pipeline.py -q`

Expected: all execution and P6 pipeline tests pass.

```bash
git add athanasor/benchmark/execution.py tests/test_benchmark_execution.py
git commit -m "feat: add locked benchmark baselines"
```

---

### Task 3: Validate and adapt raw model responses

**Files:**
- Modify: `athanasor/benchmark/execution.py`
- Modify: `tests/test_benchmark_execution.py`

**Interfaces:**
- Consumes: prepared artifact, execution manifest, and directory containing one accepted canonical response per pair.
- Produces: `validate_model_response(response, packet) -> list[str]`, `adapt_model_responses(prepared, manifest, responses, provenance) -> dict[str, Any]`, and a complete P6-valid model run.

- [ ] **Step 1: Write failing adapter tests**

```python
def test_model_adapter_preserves_assessment_and_maps_label(tmp_path: Path) -> None:
    prepared = prepared_fixture(tmp_path)
    responses = model_response_fixture(prepared, predicted_label=3)
    run = adapt_model_responses(prepared, execution_manifest_fixture(synthetic=True), responses, proved_provenance_fixture())
    row = run["results"][0]
    assert row["candidate"] is True
    assert row["score"] == 1.0
    assert row["items"][0]["assessment"] == responses[row["pair_id"]]["structural_relation"]["assessment"]
    assert row["items"][0]["status"] == "pending_review"


def test_adapter_rejects_unresolved_evidence_or_unproved_model_identity(tmp_path: Path) -> None:
    prepared = prepared_fixture(tmp_path)
    responses = model_response_fixture(prepared)
    responses[next(iter(responses))]["structural_relation"]["evidence"][0]["paper_id"] = "paper_0000000000000000"
    with pytest.raises(BenchmarkArtifactError, match="evidence"):
        adapt_model_responses(prepared, execution_manifest_fixture(synthetic=True), responses, proved_provenance_fixture())
```

- [ ] **Step 2: Run RED**

Run: `uv run --python 3.12 pytest tests/test_benchmark_execution.py -q -k 'model or adapter'`

Expected: fails for missing adapter functions.

- [ ] **Step 3: Implement strict qualitative-response adaptation**

Require exact pair/paper IDs, `predicted_label` 0–3, exact structural-relation fields, at least one evidence reference per nonempty assessment, packet-local paper/visible-field references, caveat list, `pending_review`, and no forbidden fields. Map candidate, ordinal score, ranks, item ID, evidence, caveats, implication, and confidence exactly as the design specifies. Never infer provider/model provenance.

- [ ] **Step 4: Verify GREEN and commit**

Run: `uv run --python 3.12 pytest tests/test_benchmark_execution.py -q`

Expected: all Task 1–3 tests pass.

```bash
git add athanasor/benchmark/execution.py tests/test_benchmark_execution.py
git commit -m "feat: adapt blinded model responses"
```

---

### Task 4: Assemble and independently verify the private seven-run lock

**Files:**
- Create: `athanasor/benchmark/locking.py`
- Modify: `athanasor/benchmark/artifacts.py`
- Create: `tests/test_benchmark_locking.py`

**Interfaces:**
- Consumes: prepared path, seven named run paths, execution manifest, repository root, and private lock output.
- Produces: `build_lock_manifest(...) -> dict[str, Any]`, `verify_lock_manifest(payload, *, private_root, benchmark_root, expected_git_sha=None) -> list[str]`, and `seal_lock_tree(path) -> None`.

- [ ] **Step 1: Write failing completeness, tamper, and contamination tests**

```python
def test_lock_requires_all_seven_runs_and_exact_prepared_digest(tmp_path: Path) -> None:
    with pytest.raises(BenchmarkArtifactError, match="exact seven run IDs"):
        build_lock_manifest(prepared_path, six_run_paths, execution_manifest, private_root=tmp_path)


def test_lock_verifier_detects_byte_tamper_after_seal(complete_private_lock: Path) -> None:
    manifest = read_json_artifact(complete_private_lock / "lock-manifest.json")
    target = complete_private_lock / manifest["runs"][0]["relative_path"]
    target.chmod(0o600)
    target.write_bytes(target.read_bytes() + b" ")
    assert any("sha256" in error for error in verify_lock_manifest(manifest, private_root=complete_private_lock, benchmark_root=BENCHMARK_ROOT))
```

- [ ] **Step 2: Run RED**

Run: `uv run --python 3.12 pytest tests/test_benchmark_locking.py -q`

Expected: collection fails because locking module is absent.

- [ ] **Step 3: Implement atomic lock and independent verifier**

Use relative paths only. Record byte SHA-256 and canonical artifact digest separately. Verify complete run IDs, shared prepared digest, manifest digest binding, Git SHA, backend identity, pair closure, forbidden fields, file modes, and no gold/annotation/score file names under the lock root. Seal files `0400` and directories `0500`; keep the parent private root `0700`.

- [ ] **Step 4: Verify GREEN and commit**

Run: `uv run --python 3.12 pytest tests/test_benchmark_locking.py tests/test_benchmark_execution.py -q`

Expected: all lock and execution tests pass.

```bash
git add athanasor/benchmark/locking.py athanasor/benchmark/artifacts.py tests/test_benchmark_locking.py
git commit -m "feat: seal seven-run benchmark locks"
```

---

### Task 5: Bind scoring and annotations to a verified lock

**Files:**
- Create: `athanasor/benchmark/evaluation.py`
- Modify: `athanasor/benchmark/scoring.py`
- Modify: `athanasor/benchmark/artifacts.py`
- Create: `tests/test_benchmark_evaluation.py`
- Modify: `tests/test_benchmark_scoring.py`

**Interfaces:**
- Consumes: verified lock, one locked run, optional human annotations, and explicit private gold only after lock verification.
- Produces: `build_annotation_template(run, lock) -> dict[str, Any]`, `validate_annotation_packet(...) -> list[str]`, and lock-bound score metadata.

- [ ] **Step 1: Write failing pre-lock refusal and annotation coverage tests**

```python
def test_real_score_refuses_missing_or_invalid_p7_lock(real_run_fixture: dict[str, Any], gold_fixture: dict[str, Any]) -> None:
    with pytest.raises(BenchmarkArtifactError, match="verified P7 lock"):
        score_run(BENCHMARK_ROOT, real_run_fixture, gold_fixture)


def test_annotation_template_covers_every_model_item_once(model_run_fixture: dict[str, Any], lock_fixture: dict[str, Any]) -> None:
    template = build_annotation_template(model_run_fixture, lock_fixture)
    assert {row["item_id"] for row in template["items"]} == {
        item["item_id"] for result in model_run_fixture["results"] for item in result["items"]
    }
    assert all(row["supported"] is None and row["useful"] is None and row["redundant"] is None for row in template["items"])
```

- [ ] **Step 2: Run RED**

Run: `uv run --python 3.12 pytest tests/test_benchmark_evaluation.py tests/test_benchmark_scoring.py -q`

Expected: new tests fail because lock-aware scoring/template functions are absent.

- [ ] **Step 3: Implement fail-closed real-score binding**

Add `verified_lock: dict[str, Any] | None = None` and `execution_manifest: dict[str, Any] | None = None` to `score_run`. Synthetic scores retain their existing contract. Non-synthetic P7 scores require a verified lock containing the exact run digest and execution-manifest digest; copy both into the score artifact and extend `validate_score` accordingly. Annotation templates are incomplete artifacts until every eligible boolean and concise rationale is filled; only complete packets reach scoring. OOD remains empty if no eligible decisions exist.

- [ ] **Step 4: Verify GREEN and commit**

Run: `uv run --python 3.12 pytest tests/test_benchmark_evaluation.py tests/test_benchmark_scoring.py tests/test_benchmark_reporting.py -q`

Expected: all evaluation, scoring, and report tests pass.

```bash
git add athanasor/benchmark/evaluation.py athanasor/benchmark/scoring.py athanasor/benchmark/artifacts.py tests/test_benchmark_evaluation.py tests/test_benchmark_scoring.py
git commit -m "feat: bind scoring to verified P7 locks"
```

---

### Task 6: Render deterministic comparison and failure analysis

**Files:**
- Modify: `athanasor/benchmark/evaluation.py`
- Modify: `tests/test_benchmark_evaluation.py`

**Interfaces:**
- Consumes: verified lock, seven score artifacts, and private gold for private failure detail.
- Produces: `build_comparison(lock, scores) -> dict[str, Any]`, `build_failure_analysis(lock, runs, scores, gold, annotations) -> dict[str, Any]`, and `render_public_summary(comparison, failure_analysis) -> str`.

- [ ] **Step 1: Write failing completeness and non-leakage tests**

```python
def test_comparison_requires_all_runs_and_all_thirteen_metrics(lock_fixture, score_fixtures) -> None:
    score_fixtures.pop("shared_tag")
    with pytest.raises(BenchmarkArtifactError, match="exact seven run IDs"):
        build_comparison(lock_fixture, score_fixtures)


def test_public_summary_reports_misses_and_excludes_private_text(comparison_fixture, failure_fixture) -> None:
    text = render_public_summary(comparison_fixture, failure_fixture)
    assert "threshold not met" in text.lower()
    assert "/Users/" not in text
    assert "gold_rationale" not in text
```

- [ ] **Step 2: Run RED**

Run: `uv run --python 3.12 pytest tests/test_benchmark_evaluation.py -q -k 'comparison or failure or public'`

Expected: fails for missing comparison functions.

- [ ] **Step 3: Implement canonical aggregate and failure artifacts**

Require every run and all 13 frozen metrics. Preserve each metric's numerator, denominator, value, interval, threshold, and threshold status. Private failure analysis includes pair IDs and confusion categories but not copied source text. Public summary includes aggregate counts, run/lock digests, model-provenance limitation, suite boundary, undefined populations, and every threshold miss; it excludes labels, rationales, source bytes, absolute paths, and item text.

- [ ] **Step 4: Verify GREEN and commit**

Run: `uv run --python 3.12 pytest tests/test_benchmark_evaluation.py -q`

Expected: all Task 5–6 tests pass.

```bash
git add athanasor/benchmark/evaluation.py tests/test_benchmark_evaluation.py
git commit -m "feat: compare locked benchmark runs"
```

---

### Task 7: Expose P7 CLI and installed-wheel workflow

**Files:**
- Modify: `athanasor/benchmark/cli.py`
- Modify: `athanasor/benchmark/__init__.py`
- Modify: `tests/test_benchmark_cli.py`
- Modify: `tests/test_wheel_install.py`
- Modify: `scripts/check_wheel_install.py`
- Modify: `benchmarks/operations-decision-support-v1/README.md`
- Modify: `README.md`

**Interfaces:**
- Produces: `azoth benchmark baseline`, `adapt`, `lock`, `annotations`, and `compare`; extends `validate` and makes real `score` require `--lock` and `--execution-manifest`.

- [ ] **Step 1: Write failing CLI isolation tests**

```python
def test_generation_side_p7_commands_expose_no_gold_option() -> None:
    for command in ("baseline", "adapt", "lock"):
        result = runner.invoke(cli, ["benchmark", command, "--help"])
        assert result.exit_code == 0
        assert "--gold" not in result.output


def test_real_score_requires_lock_and_execution_manifest() -> None:
    result = runner.invoke(cli, ["benchmark", "score", "--help"])
    assert "--lock" in result.output
    assert "--execution-manifest" in result.output
```

- [ ] **Step 2: Run RED**

Run: `uv run --python 3.12 pytest tests/test_benchmark_cli.py tests/test_wheel_install.py -q`

Expected: new CLI help assertions fail.

- [ ] **Step 3: Implement thin commands and wheel smoke**

Each command resolves private outputs outside the repository, validates whole inputs before writes, uses atomic overwrite refusal, and emits canonical JSON summaries with digests. `lock` accepts exactly seven repeatable `--run RUN_ID=PATH` arguments. `annotations` requires a verified lock. `compare` accepts exactly seven lock-bound scores. Installed-wheel smoke runs fictional validate/prepare/all-baselines/adapt/lock/score/report/compare on Python 3.10–3.12 without a checkout on `sys.path`.

- [ ] **Step 4: Verify GREEN and commit**

Run: `uv run --python 3.12 pytest tests/test_benchmark_cli.py tests/test_wheel_install.py -q`

Expected: all CLI and wheel-harness tests pass.

```bash
git add athanasor/benchmark/cli.py athanasor/benchmark/__init__.py tests/test_benchmark_cli.py tests/test_wheel_install.py scripts/check_wheel_install.py benchmarks/operations-decision-support-v1/README.md README.md
git commit -m "feat: expose locked benchmark workflow"
```

---

### Task 8: Run the complete fictional acceptance bundle

**Files:**
- Modify only if verification reveals a contract defect; follow a fresh RED/GREEN cycle for every correction.

- [ ] **Step 1: Run focused P7 tests**

Run: `uv run --python 3.12 pytest tests/test_benchmark_execution.py tests/test_benchmark_locking.py tests/test_benchmark_evaluation.py tests/test_benchmark_cli.py tests/test_benchmark_scoring.py tests/test_benchmark_reporting.py -q`

Expected: all focused tests pass.

- [ ] **Step 2: Run full repository and maintained checks**

```bash
uv run --python 3.12 pytest -q
for check in scripts/check_*.py; do uv run --python 3.12 python "$check"; done
uv run --python 3.12 python scripts/hardening_audit.py
uv run --python 3.12 python -m compileall -q athanasor scripts tests
git diff --check
python3 athanasor/vigil/verify.py verify
```

Expected: full suite, all maintained checks, hardening, compileall, diff, and all seven Vigil gates pass.

- [ ] **Step 3: Prove installed-wheel execution**

Build once and run the existing wheel harness for Python 3.10, 3.11, and 3.12. Expected: all resources and fictional P7 workflow pass outside the checkout with no checkout path on `sys.path`.

- [ ] **Step 4: Commit any verified corrections**

Use narrowly scoped commits naming the corrected contract. Do not proceed to real data until the committed tree passes the complete bundle.

---

### Task 9: Execute and seal all real gold-blind runs

**Files:**
- Private only: `<private-p7-root>/prepared.json`, response attempts, seven runs, and `lock-manifest.json`.
- Do not modify repository files during this task.

- [ ] **Step 1: Verify pre-run state and public/private commitments without opening gold content**

Run public benchmark validation, source-file SHA/permission checks, execution-manifest validation, Git clean/SHA checks, and Vigil start. Record that no real prepared/run/score artifact exists under the new P7 root.

- [ ] **Step 2: Prepare exactly one real blinded artifact**

Run `azoth benchmark prepare` against the existing 12 verified private source files and the new empty private P7 root. Validate it independently and record its canonical digest.

- [ ] **Step 3: Generate and lock six deterministic baselines**

Run `azoth benchmark baseline` once per declared baseline. Verify exact prepared digest, pair closure, backend/execution-manifest binding, and byte SHA-256 for every run.

- [ ] **Step 4: Generate 66 blinded model responses in canonical batches**

Read only the generation prompt, rubric, execution manifest, and one blinded packet at a time. Produce one canonical response attempt per pair using the active Codex task. Validate each response immediately but do not view any gold or score. Record available client/task/runtime provenance without claiming unexposed provider identity.

- [ ] **Step 5: Adapt and lock the model run**

Require all 66 responses, adapt them deterministically, validate pair/rank/item/evidence closure, and write the model run without overwrite.

- [ ] **Step 6: Build, seal, and independently reverify the seven-run lock**

Write the lock manifest atomically, seal permissions, rerun the independent verifier, and record exact digests. If any check fails, remain gold blind and repair only the failing implementation or response before rebuilding the lock.

---

### Task 10: Score, annotate, compare, and close P7

**Files:**
- Private: seven scores/reports, model annotation packet, comparison, and detailed failure analysis.
- Public: aggregate result JSON/Markdown, roadmap/README references that quote only verified suite-scoped metrics.

- [ ] **Step 1: Open gold only after lock verification**

Verify the private gold file's canonical commitment against the unchanged public freeze, then score all six deterministic baselines with the same lock and no annotations. Generate the model annotation template from the locked model run.

- [ ] **Step 2: Complete explicit human item annotations**

Rafael reviews every eligible model item for support, usefulness, redundancy, and evidence validity. Validate exact item coverage and concise rationales. Leave OOD metrics undefined when no eligible OOD decisions exist.

- [ ] **Step 3: Score the model and render all reports**

Score the locked model run with the complete annotation packet. Render seven deterministic reports, comparison, private failure analysis, and public summary. Re-run each scoring/report command and prove byte-identical output in a fresh temporary directory.

- [ ] **Step 4: Audit public result fixtures**

Prove the tracked aggregate contains all run IDs, 13 metric records per run, numerators, denominators, uncertainty, thresholds, missed-target flags, lock/run digests, provenance limitation, suite boundary, and no private paths, raw labels, rationales, source bytes, or model item text.

- [ ] **Step 5: Run final acceptance and close the roadmap**

Run the full Task 8 bundle again on committed result fixtures, then Vigil verify and close. Update `PROJECT_ROADMAP.md` to mark P7 complete with exact evidence and exactly `P8-T1 — Public README and rejection/reframe case study` next. Commit tracked P7 results and closeout state only after all checks pass.

```bash
git add benchmarks/operations-decision-support-v1/results README.md PROJECT_ROADMAP.md athanasor/lapis/state.json athanasor/lapis/codex.md
git commit -m "docs: close P7 locked benchmark evaluation"
```

Expected final state: clean worktree; all seven Vigil gates; complete seven-run private lock; reproducible lock-bound scores and reports; explicit human annotation evidence; honest aggregate results; P8-T1 as the only next task.
