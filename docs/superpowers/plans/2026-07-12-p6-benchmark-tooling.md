# P6-T1 Benchmark Tooling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an isolated benchmark CLI, deterministic runner, complete frozen-metric scorer, reproducible report, and fictional end-to-end fixtures without exposing P5 gold to generation.

**Architecture:** Extend `athanasor.benchmark` with focused artifact, public pipeline, scoring, reporting, and CLI modules. Public preparation and run functions have no gold parameter; score requires an explicit repository-external gold path and validates the P5 commitment after the run is locked. Canonical JSON, content digests, and atomic writes make repeated fictional runs byte-reproducible.

**Tech Stack:** Python 3.10-3.12, Click, PyYAML, PyMuPDF, standard-library JSON/hashlib/math/random/statistics/tempfile/urllib, pytest, existing P5 validators and Vigil.

## Global Constraints

- Work only on `P6-T1 — Benchmark CLI, scorer, report, and synthetic fixtures` at High effort.
- Keep P5 sources, versions, prompt, blinded schema, rubric, metrics, thresholds, uncertainty, gold commitment, and no-retuning rule unchanged.
- `validate`, `fetch`, `prepare`, `run`, and `report` have no private-gold input or discovery path.
- `score` is the only P6 command that accepts `--gold`; it requires an explicit path outside the repository and validates the exact P5 commitment before calculation.
- Do not read real P5 gold or run the real 12-paper benchmark during P6.
- Tests use only newly authored fictional source bytes, labels, responses, and human annotations under temporary directories.
- Every written P6 artifact uses canonical JSON, schema version 1, exact provenance digests, atomic replacement, and overwrite refusal unless `--force` is explicit.
- A generation-side artifact containing a recursively forbidden gold field is invalid.
- Missing evaluation populations produce null values with numerator and denominator zero; never impute a result.
- Synthetic outputs must say `SYNTHETIC CONTRACT TEST — NOT A PERFORMANCE CLAIM`.
- Commit no third-party source bytes, real gold, run outputs, private paths, or performance claims.
- Preserve Python 3.10-3.12 and installed-wheel behavior.

## File Map

- Create `athanasor/benchmark/artifacts.py`: P6 artifact constants, canonical atomic JSON, validation, and repository boundary helpers.
- Create `athanasor/benchmark/pipeline.py`: public-only fetch, prepare, fallback run, and response import.
- Create `athanasor/benchmark/scoring.py`: pure frozen metric calculations, uncertainty, and score assembly.
- Create `athanasor/benchmark/reporting.py`: deterministic Markdown rendering.
- Create `athanasor/benchmark/cli.py`: thin six-command Click group.
- Modify `athanasor/benchmark/__init__.py`: stable P6 exports.
- Modify `athanasor/cli.py`: register the benchmark group.
- Create `tests/test_benchmark_artifacts.py`, `tests/test_benchmark_pipeline.py`, `tests/test_benchmark_scoring.py`, `tests/test_benchmark_cli.py`, and `tests/test_benchmark_reporting.py`.
- Modify `tests/benchmark_fixtures.py`: complete six-source private/public synthetic builders.
- Modify `benchmarks/operations-decision-support-v1/README.md`, `README.md`, and `PROJECT_ROADMAP.md` only after implementation verification.

---

### Task 1: Canonical P6 artifact and path contracts

**Files:**
- Create: `athanasor/benchmark/artifacts.py`
- Modify: `athanasor/benchmark/__init__.py`
- Create: `tests/test_benchmark_artifacts.py`

**Interfaces:**
- Consumes: arbitrary JSON mappings and explicit repository/input/output paths.
- Produces: `PREPARED_TYPE`, `RUN_TYPE`, `SCORE_TYPE`, `BenchmarkArtifactError`, `artifact_digest(payload) -> str`, `read_json_artifact(path, artifact_type=None) -> dict[str, Any]`, `atomic_write_json(path, payload, *, force=False) -> str`, `ensure_outside_repository(path, repo_root, *, label) -> Path`, `validate_prepared(payload) -> list[str]`, `validate_run(payload) -> list[str]`, and `validate_score(payload) -> list[str]`.

- [ ] **Step 1: Write failing canonical-write and boundary tests**

```python
def test_atomic_json_is_canonical_and_refuses_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "artifact.json"
    digest = atomic_write_json(target, {"schema_version": 1, "b": 2, "a": 1})
    assert target.read_bytes() == b'{"a":1,"b":2,"schema_version":1}\n'
    assert digest == hashlib.sha256(target.read_bytes()[:-1]).hexdigest()
    with pytest.raises(BenchmarkArtifactError, match="already exists"):
        atomic_write_json(target, {"schema_version": 1})


def test_repository_boundary_resolves_symlink_alias(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(repo, target_is_directory=True)
    with pytest.raises(BenchmarkArtifactError, match="outside the repository"):
        ensure_outside_repository(alias / "private", repo, label="private root")


@pytest.mark.parametrize("field", ["gold_label", "gold_rationale", "target_thresholds"])
def test_generation_artifacts_reject_gold_fields_recursively(field: str) -> None:
    payload = prepared_fixture()
    payload["packets"][0]["sources"][0]["nested"] = {field: 2}
    assert any(field in error for error in validate_prepared(payload))
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run --python 3.12 pytest tests/test_benchmark_artifacts.py -q`

Expected: collection fails because `athanasor.benchmark.artifacts` does not exist.

- [ ] **Step 3: Implement canonical artifact primitives and strict validators**

Implement these exact constants and signatures:

```python
SCHEMA_VERSION = 1
PREPARED_TYPE = "azoth_benchmark_prepared"
RUN_TYPE = "azoth_benchmark_run"
SCORE_TYPE = "azoth_benchmark_score"
SYNTHETIC_NOTICE = "SYNTHETIC CONTRACT TEST — NOT A PERFORMANCE CLAIM"


class BenchmarkArtifactError(ValueError):
    """A P6 artifact or path violates the benchmark contract."""


def artifact_digest(payload: Any) -> str:
    return canonical_digest(payload)


def atomic_write_json(path: Path, payload: dict[str, Any], *, force: bool = False) -> str:
    if path.exists() and not force:
        raise BenchmarkArtifactError(f"destination already exists: {path.name}")
    encoded = canonical_json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return hashlib.sha256(encoded).hexdigest()
```

`ensure_outside_repository` resolves both paths with `strict=False` and rejects equality or repository ancestry. Each validator requires exact top-level fields for its artifact type, validates schema/benchmark identity, canonical pair coverage, digests, numeric types without accepting booleans, and calls the existing recursive forbidden-field validator for prepared/run inputs. Errors are sorted field-addressed strings.

- [ ] **Step 4: Run focused tests and commit**

Run: `uv run --python 3.12 pytest tests/test_benchmark_artifacts.py -q`

Expected: all Task 1 tests pass.

```bash
git add athanasor/benchmark/artifacts.py athanasor/benchmark/__init__.py tests/test_benchmark_artifacts.py
git commit -m "feat: add benchmark artifact contracts"
```

---

### Task 2: Offline-safe fetch and blinded preparation

**Files:**
- Create: `athanasor/benchmark/pipeline.py`
- Modify: `tests/benchmark_fixtures.py`
- Create: `tests/test_benchmark_pipeline.py`

**Interfaces:**
- Consumes: a validated public benchmark root, explicit external source/output roots, and injected byte/extraction functions.
- Produces: `FetchResponse`, `fetch_sources(source_manifest, destination, *, fetcher=fetch_https, force=False) -> dict[str, Any]`, `prepare_benchmark(benchmark_root, source_manifest, source_root, destination, *, extractor=extract_pdf_record, force=False) -> dict[str, Any]`, and `build_blinded_packets(source_records) -> list[dict[str, Any]]`.

- [ ] **Step 1: Add six-source synthetic source/retrieval fixtures**

Extend `tests/benchmark_fixtures.py` with:

```python
def synthetic_p6_sources() -> dict[str, Any]:
    path = REPO_ROOT / "benchmarks" / "operations-decision-support-v1" / "synthetic" / "sources.yaml"
    return load_mapping(path)


def write_synthetic_source_root(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for source in synthetic_p6_sources()["sources"]:
        body = source["source_text"].encode("utf-8")
        (root / f"{source['paper_id']}.pdf").write_bytes(body)
        (root / f"{source['paper_id']}.retrieval.json").write_text(json.dumps({
            "requested_url": f"https://example.invalid/{source['paper_id']}",
            "redirect_chain": [f"https://example.invalid/{source['paper_id']}"],
            "final_url": f"https://example.invalid/{source['paper_id']}",
            "media_type": "application/pdf",
            "access_date": "2026-07-12",
            "exact_version": source["exact_version"],
            "license_evidence_url": "https://example.invalid/synthetic-license",
            "sha256": hashlib.sha256(body).hexdigest(),
            "byte_count": len(body),
        }, sort_keys=True), encoding="utf-8")
    return root
```

- [ ] **Step 2: Write failing fetch/prepare tests**

```python
def test_fetch_verifies_all_bytes_before_accepting_destination(tmp_path: Path) -> None:
    manifest = synthetic_fetch_manifest_fixture()
    destination = tmp_path / "external-sources"
    responses = synthetic_fetch_responses(manifest)
    result = fetch_sources(manifest, destination, fetcher=responses.__getitem__)
    assert result["source_count"] == 6
    assert len(list(destination.glob("*.retrieval.json"))) == 6


def test_prepare_builds_all_15_pairs_without_gold(tmp_path: Path) -> None:
    source_root = write_synthetic_source_root(tmp_path / "sources")
    prepared = prepare_synthetic_benchmark(
        benchmark_root=LIVE_BENCHMARK_ROOT,
        source_manifest=synthetic_p6_sources(),
        source_root=source_root,
    )
    assert len(prepared["packets"]) == 15
    assert validate_prepared(prepared) == []
    assert not recursive_keys(prepared) & FORBIDDEN_GOLD_FIELDS


def test_prepare_fails_atomically_when_one_packet_is_invalid(tmp_path: Path) -> None:
    source_root = write_synthetic_source_root(tmp_path / "sources")
    destination = tmp_path / "prepared.json"
    with pytest.raises(BenchmarkArtifactError, match="packet"):
        prepare_benchmark(
            LIVE_BENCHMARK_ROOT,
            synthetic_p6_sources(),
            source_root,
            destination,
            extractor=extractor_with_one_invalid_record,
        )
    assert not destination.exists()
```

- [ ] **Step 3: Run tests and verify RED**

Run: `uv run --python 3.12 pytest tests/test_benchmark_pipeline.py -q`

Expected: collection fails because `athanasor.benchmark.pipeline` does not exist.

- [ ] **Step 4: Implement fetch and preparation with no gold API**

Use these signatures:

```python
@dataclass(frozen=True)
class FetchResponse:
    body: bytes
    requested_url: str
    redirect_chain: Sequence[str]
    final_url: str
    media_type: str
```

Implement `fetch_sources(source_manifest: dict[str, Any], destination: Path,
*, fetcher: Callable[[str], FetchResponse] = fetch_https, force: bool = False)
-> dict[str, Any]`, `build_blinded_packets(source_records: list[dict[str, Any]])
-> list[dict[str, Any]]`, and `prepare_benchmark(benchmark_root: Path,
source_manifest: dict[str, Any], source_root: Path, destination: Path, *,
extractor: Callable[[bytes, dict[str, Any]], dict[str, Any]] =
extract_pdf_record, force: bool = False) -> dict[str, Any]`.

`fetch_sources` downloads all inputs to a temporary sibling directory, validates HTTPS redirect chains, `application/pdf`, exact SHA-256, byte count, and manifest identity, then atomically installs the complete directory. `prepare_benchmark` validates the frozen public bundle, revalidates source bytes/sidecars, extracts all records, creates canonical combinations for the supplied manifest, validates every blinded packet against the frozen schema, constructs the prepared artifact with frozen digests, then atomically writes it. Neither signature or module contains `gold`, `label`, or adjudication inputs.

- [ ] **Step 5: Run focused tests and commit**

Run: `uv run --python 3.12 pytest tests/test_benchmark_pipeline.py tests/test_benchmark_artifacts.py -q`

Expected: all Task 1-2 tests pass.

```bash
git add athanasor/benchmark/pipeline.py tests/benchmark_fixtures.py tests/test_benchmark_pipeline.py
git commit -m "feat: fetch and prepare blinded benchmarks"
```

---

### Task 3: Deterministic fallback and response-import runs

**Files:**
- Modify: `athanasor/benchmark/pipeline.py`
- Modify: `athanasor/benchmark/artifacts.py`
- Modify: `tests/test_benchmark_pipeline.py`

**Interfaces:**
- Consumes: one validated prepared artifact and either a deterministic fallback configuration or complete imported responses.
- Produces: `run_fallback(prepared, *, seed=5607) -> dict[str, Any]` and `import_run(prepared, responses) -> dict[str, Any]`.

- [ ] **Step 1: Write failing deterministic run tests**

```python
def test_fallback_run_is_byte_reproducible() -> None:
    prepared = prepared_fixture(pair_count=15, synthetic=True)
    first = run_fallback(prepared, seed=5607)
    second = run_fallback(deepcopy(prepared), seed=5607)
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert validate_run(first) == []


def test_run_has_exact_pair_coverage_and_no_gold() -> None:
    result = run_fallback(prepared_fixture(pair_count=15, synthetic=True))
    assert [row["pair_id"] for row in result["results"]] == sorted(
        packet["pair_id"] for packet in prepared_fixture(pair_count=15, synthetic=True)["packets"]
    )
    assert not recursive_keys(result) & FORBIDDEN_GOLD_FIELDS


def test_import_rejects_partial_or_extra_pair_results() -> None:
    prepared = prepared_fixture(pair_count=15, synthetic=True)
    responses = imported_response_fixture(prepared)
    responses["results"].pop()
    with pytest.raises(BenchmarkArtifactError, match="exact pair coverage"):
        import_run(prepared, responses)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run --python 3.12 pytest tests/test_benchmark_pipeline.py -q -k 'fallback or import or run'`

Expected: imports fail for missing run functions.

- [ ] **Step 3: Implement stable fallback and import**

```python
def run_fallback(prepared: dict[str, Any], *, seed: int = 5607) -> dict[str, Any]:
    errors = validate_prepared(prepared)
    if errors:
        raise BenchmarkArtifactError("invalid prepared artifact: " + "; ".join(errors))
    results = [_fallback_pair(packet, seed=seed) for packet in prepared["packets"]]
    return _run_artifact(
        prepared,
        backend={"name": "deterministic_hash_fallback", "version": 1},
        seed=seed,
        results=results,
    )


```

Implement `import_run(prepared: dict[str, Any], responses: dict[str, Any]) ->
dict[str, Any]` with the validation sequence below.

Normalize visible strings with Unicode NFKC, casefolding, and whitespace
collapse. Hash each source's visible tags/methods/claims/evidence, derive stable
overlap features, assign a `0..3` fallback label by fixed documented cutoffs,
and derive stable ranks using `(score desc, pair_id asc)`. Do not use random
iteration order or wall-clock time. Import requires exact prepared digest,
backend identity, complete pair coverage, valid labels/ranks/evidence references,
and recursive forbidden-field rejection before returning any run artifact.

- [ ] **Step 4: Run focused tests and commit**

Run: `uv run --python 3.12 pytest tests/test_benchmark_pipeline.py tests/test_benchmark_artifacts.py -q`

Expected: all Task 1-3 tests pass.

```bash
git add athanasor/benchmark/pipeline.py athanasor/benchmark/artifacts.py tests/test_benchmark_pipeline.py
git commit -m "feat: add deterministic benchmark runs"
```

---

### Task 4: Frozen metric scorer and deterministic uncertainty

**Files:**
- Create: `athanasor/benchmark/scoring.py`
- Modify: `athanasor/benchmark/artifacts.py`
- Create: `tests/test_benchmark_scoring.py`

**Interfaces:**
- Consumes: validated protocol, frozen run, exact committed private gold, and optional locked human annotations.
- Produces: `wilson_interval`, `paired_bootstrap_interval`, `score_run(benchmark_root, run, gold, *, annotations=None, bootstrap_seed=5607) -> dict[str, Any]`, and one pure calculator per frozen metric.

- [ ] **Step 1: Write hand-computed metric and undefined-case tests**

```python
def test_macro_f1_uses_all_four_classes() -> None:
    result = macro_f1([0, 1, 2, 3], [0, 1, 1, 3])
    assert result.numerator == 3
    assert result.denominator == 4
    assert result.value == pytest.approx((1.0 + 2 / 3 + 0.0 + 1.0) / 4)


def test_precision_at_5_and_ndcg_use_canonical_queries() -> None:
    gold = {("a", "b"): 3, ("a", "c"): 2, ("a", "d"): 0}
    ranked = {"a": ["d", "b", "c"]}
    assert precision_at_k(gold, ranked, k=5).value == pytest.approx(2 / 3)
    assert ndcg_at_k(gold, ranked, k=10).value == pytest.approx(
        (0 + 7 / math.log2(3) + 3 / math.log2(4)) /
        (7 + 3 / math.log2(3))
    )


@pytest.mark.parametrize("name", HUMAN_ANNOTATION_METRICS)
def test_missing_human_population_is_null(name: str) -> None:
    score = score_run(protocol_fixture(), run_fixture(), synthetic_gold_fixture())
    metric = metric_by_name(score, name)
    assert metric["value"] is None
    assert metric["numerator"] == metric["denominator"] == 0
    assert metric["threshold_met"] is None


def test_gold_commitment_mismatch_writes_no_score(tmp_path: Path) -> None:
    with pytest.raises(BenchmarkArtifactError, match="commitment"):
        score_run(protocol_fixture(), run_fixture(), tampered_gold_fixture())
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run --python 3.12 pytest tests/test_benchmark_scoring.py -q`

Expected: collection fails because `athanasor.benchmark.scoring` does not exist.

- [ ] **Step 3: Implement pure metric records and intervals**

```python
@dataclass(frozen=True)
class MetricValue:
    numerator: int | float
    denominator: int | float
    value: float | None
    uncertainty: dict[str, Any]


```

Implement `wilson_interval(numerator: int, denominator: int, confidence: float
= 0.95) -> tuple[float, float] | None` and
`paired_bootstrap_interval(observations: Sequence[Any], statistic:
Callable[[Sequence[Any]], float | None], *, seed: int = 5607, samples: int =
2000) -> tuple[float, float] | None`.

Implement all 13 frozen metrics using `EXPECTED_P5_METRIC_CONTRACTS` and the
protocol's exact threshold records. Wilson uses `z=1.959963984540054`; paired
bootstrap samples observation indices with `random.Random(seed)` and uses
linear-interpolated 2.5th/97.5th percentiles. Macro-F1 reports null if any
class denominator is undefined, matching the frozen protocol. Ranking metrics
canonicalize each pair into both query orientations and deduplicate targets.

- [ ] **Step 4: Assemble score only after gold validation and commitment match**

Implement `score_run(benchmark_root: Path, run: dict[str, Any], gold:
dict[str, Any], *, annotations: dict[str, Any] | None = None, bootstrap_seed:
int = 5607) -> dict[str, Any]`.

The function validates the public bundle and run first, validates the gold with
`validate_gold_packet`, recomputes `gold_commitment(gold)`, requires exact
equality with `freeze-manifest.json`, validates every optional annotation ID
against the locked run, calculates all metrics, and returns a score artifact.
Metric order follows `protocol.yaml`; each record copies the exact population,
numerator definition, denominator definition, averaging, undefined case,
uncertainty contract, threshold, comparison, and explicit calculated counts.

- [ ] **Step 5: Run focused tests and commit**

Run: `uv run --python 3.12 pytest tests/test_benchmark_scoring.py tests/test_benchmark_artifacts.py -q`

Expected: all Task 1 and Task 4 tests pass, including byte-identical repeated score assembly.

```bash
git add athanasor/benchmark/scoring.py athanasor/benchmark/artifacts.py tests/test_benchmark_scoring.py
git commit -m "feat: score frozen benchmark metrics"
```

---

### Task 5: Deterministic provenance-first report

**Files:**
- Create: `athanasor/benchmark/reporting.py`
- Create: `tests/test_benchmark_reporting.py`

**Interfaces:**
- Consumes: one validated score artifact.
- Produces: `render_markdown(score) -> str`.

- [ ] **Step 1: Write failing report tests**

```python
def test_synthetic_report_is_unmistakably_non_performance() -> None:
    rendered = render_markdown(synthetic_score_fixture())
    assert rendered.count(SYNTHETIC_NOTICE) >= 2
    assert "| Metric | Value | Numerator | Denominator | Uncertainty | Threshold |" in rendered
    assert "## Provenance" in rendered
    assert "## Undefined metrics" in rendered
    assert "## Limitations" in rendered


def test_report_is_byte_deterministic_and_does_not_recompute() -> None:
    score = synthetic_score_fixture()
    score["metrics"][0]["value"] = 0.123456
    first = render_markdown(score)
    second = render_markdown(deepcopy(score))
    assert first == second
    assert "0.123456" in first
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run --python 3.12 pytest tests/test_benchmark_reporting.py -q`

Expected: collection fails because `athanasor.benchmark.reporting` does not exist.

- [ ] **Step 3: Implement stable Markdown rendering**

```python
def render_markdown(score: dict[str, Any]) -> str:
    errors = validate_score(score)
    if errors:
        raise BenchmarkArtifactError("invalid score artifact: " + "; ".join(errors))
    lines = [f"# Benchmark Report — {score['benchmark_id']}", ""]
    if score.get("synthetic") is True:
        lines.extend([f"> **{SYNTHETIC_NOTICE}**", ""])
    lines.extend(_provenance_lines(score))
    lines.extend(_metric_table_lines(score["metrics"]))
    lines.extend(_undefined_metric_lines(score["metrics"]))
    lines.extend(_failure_lines(score))
    lines.extend(_limitation_lines(score))
    if score.get("synthetic") is True:
        lines.extend(["", f"> **{SYNTHETIC_NOTICE}**"])
    return "\n".join(lines).rstrip() + "\n"
```

Escape Markdown table delimiters, preserve metric order, render null as
`undefined (0/0)`, print exact threshold operators, show interval bounds and
method, and include run/gold/annotation/protocol/calculation digests. Do not
import a calculator or recompute any metric.

- [ ] **Step 4: Run focused tests and commit**

Run: `uv run --python 3.12 pytest tests/test_benchmark_reporting.py -q`

Expected: all report tests pass.

```bash
git add athanasor/benchmark/reporting.py tests/test_benchmark_reporting.py
git commit -m "feat: render benchmark score reports"
```

---

### Task 6: Isolated `azoth benchmark` CLI

**Files:**
- Create: `athanasor/benchmark/cli.py`
- Modify: `athanasor/cli.py`
- Modify: `athanasor/benchmark/__init__.py`
- Create: `tests/test_benchmark_cli.py`

**Interfaces:**
- Consumes: explicit CLI paths and options.
- Produces: `benchmark_cli` Click group with `validate`, `fetch`, `prepare`, `run`, `score`, and `report`.

- [ ] **Step 1: Write failing CLI surface and isolation tests**

```python
def test_benchmark_help_lists_exact_commands() -> None:
    result = CliRunner().invoke(main, ["benchmark", "--help"])
    assert result.exit_code == 0
    for command in ("validate", "fetch", "prepare", "run", "score", "report"):
        assert command in result.output


@pytest.mark.parametrize("command", ["validate", "fetch", "prepare", "run", "report"])
def test_generation_side_commands_have_no_gold_option(command: str) -> None:
    result = CliRunner().invoke(main, ["benchmark", command, "--help"])
    assert result.exit_code == 0
    assert "--gold" not in result.output


def test_score_requires_explicit_external_gold(tmp_path: Path) -> None:
    result = CliRunner().invoke(main, ["benchmark", "score", "--help"])
    assert result.exit_code == 0
    assert "--gold" in result.output
    assert "required" in result.output.casefold()
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run --python 3.12 pytest tests/test_benchmark_cli.py -q`

Expected: `No such command 'benchmark'`.

- [ ] **Step 3: Implement the thin group and exact options**

Register with `main.add_command(benchmark_cli)` after defining `main`.

```python
@click.group("benchmark")
def benchmark_cli() -> None:
    """Validate, prepare, run, score, and report frozen benchmarks."""
```

Exact command options:

- `validate --benchmark-root PATH [--artifact PATH] [--json]`
- `fetch --benchmark-root PATH --source-dir PATH --repo-root PATH [--force] [--json]`
- `prepare --benchmark-root PATH --source-dir PATH --output PATH --repo-root PATH [--synthetic-sources PATH] [--force] [--json]`
- `run --prepared PATH --output PATH [--backend fallback] [--responses PATH] [--seed 5607] [--force] [--json]`
- `score --benchmark-root PATH --run PATH --gold PATH --output PATH --repo-root PATH [--annotations PATH] [--force] [--json]`
- `report --score PATH --output PATH [--force] [--json]`

Each handler only parses paths, calls one library function, atomically writes
the result, and emits a stable summary. Convert `BenchmarkProtocolError` and
`BenchmarkArtifactError` into `click.ClickException` without tracebacks. `score`
calls `ensure_outside_repository` for gold and annotations before reading them.
No command reads `AZOTH_P5_PRIVATE_ROOT` or searches for files.

- [ ] **Step 4: Add CLI end-to-end fictional flow**

```python
def test_fictional_cli_flow_is_reproducible(tmp_path: Path) -> None:
    paths = synthetic_cli_paths(tmp_path)
    first = run_synthetic_cli_flow(paths / "first")
    second = run_synthetic_cli_flow(paths / "second")
    assert first.prepared_bytes == second.prepared_bytes
    assert first.run_bytes == second.run_bytes
    assert first.score_bytes == second.score_bytes
    assert first.report_bytes == second.report_bytes
    assert SYNTHETIC_NOTICE.encode() in first.report_bytes
```

- [ ] **Step 5: Run focused tests and commit**

Run: `uv run --python 3.12 pytest tests/test_benchmark_cli.py tests/test_benchmark_artifacts.py tests/test_benchmark_pipeline.py tests/test_benchmark_scoring.py tests/test_benchmark_reporting.py -q`

Expected: all P6 focused tests pass.

```bash
git add athanasor/benchmark/cli.py athanasor/benchmark/__init__.py athanasor/cli.py tests/test_benchmark_cli.py
git commit -m "feat: expose isolated benchmark CLI"
```

---

### Task 7: Documentation, package portability, and P6 closeout

**Files:**
- Modify: `benchmarks/operations-decision-support-v1/README.md`
- Modify: `README.md`
- Modify: `PROJECT_ROADMAP.md`
- Modify tests/checks only if a failing acceptance command exposes an owned P6 defect.

**Interfaces:**
- Consumes: verified implementation and command evidence.
- Produces: public usage documentation, exact non-claim boundary, P6 ledger evidence, and P7-T1 as the only next task.

- [ ] **Step 1: Add a failing documentation contract test**

Add to `tests/test_benchmark_cli.py`:

```python
def test_public_docs_show_isolated_flow_and_non_claim_boundary() -> None:
    benchmark_readme = (LIVE_BENCHMARK_ROOT / "README.md").read_text(encoding="utf-8")
    root_readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for command in ("validate", "fetch", "prepare", "run", "score", "report"):
        assert f"azoth benchmark {command}" in benchmark_readme
    assert SYNTHETIC_NOTICE in benchmark_readme
    assert "P6 publishes no benchmark performance result" in root_readme
```

- [ ] **Step 2: Run the test and verify RED**

Run: `uv run --python 3.12 pytest tests/test_benchmark_cli.py::test_public_docs_show_isolated_flow_and_non_claim_boundary -q`

Expected: fails because P6 commands are not yet documented.

- [ ] **Step 3: Document exact commands and boundaries**

Document a reproducible fictional sequence with explicit external paths and
state clearly that real gold must not be supplied until a P7 run is locked.
Describe fallback as an engineering baseline, not a model-quality result. Do
not add measured values from synthetic fixtures to public claims.

- [ ] **Step 4: Run focused and full verification before roadmap closeout**

Run, in order:

```bash
uv run --python 3.12 pytest tests/test_benchmark_artifacts.py tests/test_benchmark_pipeline.py tests/test_benchmark_scoring.py tests/test_benchmark_reporting.py tests/test_benchmark_cli.py -q
uv run --python 3.12 python -m pytest -q
for check in scripts/check_*.py; do uv run --python 3.12 python "$check"; done
uv run --python 3.12 python scripts/check_public_tree.py
uv run --python 3.12 python scripts/hardening_audit.py
uv run --python 3.12 python -m compileall -q athanasor scripts tests
git diff --check
python3 athanasor/vigil/verify.py verify
```

Expected: all tests/checks/audits/compile/Vigil pass with no real benchmark run or performance claim.

- [ ] **Step 5: Verify installed wheel outside the checkout**

```bash
uv build --wheel --out-dir /tmp/azoth-p6-dist
uv run --python 3.12 python scripts/check_wheel_install.py --wheel /tmp/azoth-p6-dist/azoth-*.whl --python 3.10 --python 3.11 --python 3.12
```

Expected: wheel smoke passes on all three interpreters and `azoth benchmark --help` plus the fictional validate/run/report smoke operate without checkout imports. If the existing wheel checker lacks the benchmark smoke, extend it test-first before accepting this task.

- [ ] **Step 6: Close P6 in the roadmap from fresh evidence**

Update the ordered ledger to mark P6 completed, record the exact implementation
commit SHA only after the implementation commit exists, append verification
evidence with exact counts, append a decision that generation-side commands have
no gold API, append the completed-session row, and set exactly:

```markdown
**Next task:** P7-T1 — Locked benchmark runs and adjudication.
```

Keep the inherited statement that no real benchmark performance result exists.

- [ ] **Step 7: Run Vigil close, verify cleanliness, and commit closeout**

```bash
python3 athanasor/vigil/verify.py close
git status --short
git add benchmarks/operations-decision-support-v1/README.md README.md PROJECT_ROADMAP.md athanasor/lapis/state.json athanasor/lapis/codex.md
git commit -m "docs: close P6 benchmark tooling"
git status --short
```

Expected: Vigil close passes, only explicitly listed closeout files are staged,
the commit succeeds, and the final tracked worktree is clean.

## Plan self-review

- P6 scope coverage: six isolated commands, deterministic artifacts, full frozen scorer, report, fictional success/failure fixtures, packaging, and closeout are each owned by one task.
- P5 boundary: no generation-side signature accepts gold; only score accepts an explicit validated packet after run locking.
- Type consistency: prepared, run, and score mappings use schema version 1 and canonical digests across all tasks; command options map directly to library signatures.
- No-retuning: all metric contracts and thresholds are consumed from the frozen protocol and never redefined by P6.
- Completion evidence: focused tests alone are insufficient; full suite, maintained checks, audits, compileall, wheel smoke, Vigil, clean status, and roadmap next-task evidence are mandatory.
