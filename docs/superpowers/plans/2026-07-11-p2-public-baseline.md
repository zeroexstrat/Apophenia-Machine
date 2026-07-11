# P2 Sanitized Public Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a data-independent public checkout with truthful executable Vigil gates, retrieval-only no-LLM behavior, schema-validated connection and detection imports, synthetic examples, and Apache-2.0 metadata.

**Architecture:** Runtime artifacts are removed from Git and recreated only inside ignored workspaces. Structural checks operate on an explicit root and validate artifact schemas plus bounded trace invariants. Agent-produced connection and hypothesis packets enter through validate-then-commit adapters; deterministic no-LLM processing emits a separate retrieval-candidate type. Rejected Rubedo clusters are remembered through a canonical fingerprint ledger written by the existing human promotion command.

**Tech Stack:** Python 3.10-3.12, Click, PyYAML, NumPy, pytest, JSONL registries, YAML artifact schemas, Git tracked-tree audits.

## Global Constraints

- `PROJECT_ROADMAP.md` is canonical and P2-T1 is the only task ID in this session.
- Use only newly authored synthetic examples; do not transform pilot artifacts.
- Every generated research artifact remains `pending_review` until a named human records a decision.
- Scientific validity and novelty remain human judgments.
- Do not modify the sealed private archive.
- Do not rewrite history, force-update `main`, delete tags, or delete pull-request refs; those operations belong to P4-T1.
- Do not package resources or implement `azoth init`; those operations belong to P3-T1.
- Use Python 3.12 through `UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12` for local verification.
- Every production behavior change follows red-green-refactor: add one focused test, observe the intended failure, implement, and rerun.
- Keep runtime artifacts ignored and test behavior against temporary roots.

## File structure

- Create `scripts/check_public_tree.py`: Git-index-based public artifact, privacy-path, fallback, snapshot, and license audit.
- Create `tests/test_public_tree.py`: isolated unit coverage for the audit and one live tracked-tree assertion.
- Create `tests/fixture_factory.py`: deterministic synthetic registry, library, exhaustion, connection, and hypothesis builders.
- Modify `athanasor/vigil/verify.py`: exact five-gate checks and bounded language.
- Modify `athanasor/vigil/gates.yaml`: descriptions identical in scope to executable checks.
- Create `athanasor/rejections.py`: canonical Rubedo cluster/evidence fingerprints and JSONL ledger operations.
- Modify `athanasor/skills/promote.py`: transactional rejected-decision ledger write.
- Create `RETRIEVAL_SCHEMA.yaml`: deterministic retrieval-candidate contract.
- Modify `athanasor/skills/connect.py`: retrieval-only no-LLM path and atomic `apply_agent_connections` adapter.
- Modify `athanasor/skills/detect.py`: remove fallback synthesis and add atomic `apply_agent_hypotheses` adapter with rejection suppression.
- Modify `athanasor/cli.py`: mutually exclusive `connect --from-file` and `detect --from-file` modes and accurate output labels.
- Create `tests/test_connect_from_file.py`, `tests/test_detect_from_file.py`, and `tests/test_rejections.py`.
- Expand `tests/test_vigil_gates.py` and existing connect/detect tests.
- Create `examples/synthetic-agent-input/README.md`, `connections.json`, and `hypotheses.json`.
- Modify `.gitignore`, `README.md`, `USER_GUIDE.md`, `AGENTS.md`, `pyproject.toml`, `LICENSE`, `PROJECT_ROADMAP.md`, and relevant check scripts.
- Delete tracked runtime artifacts under `albedo/`, `citrinitas/`, `rubedo/`, `nigredo/`, `athanasor/lapis/`, `athanasor/vigil/reports/`, and contaminated `docs/history/` material as identified by the audit.

---

### Task 1: Tracked-tree audit and sanitized runtime boundary

**Files:**
- Create: `scripts/check_public_tree.py`
- Create: `tests/test_public_tree.py`
- Modify: `.gitignore`
- Delete: tracked files under `albedo/`, `citrinitas/`, `rubedo/`, `athanasor/vigil/reports/`, `athanasor/lapis/state.json`, `athanasor/lapis/codex.md`, `nigredo/SOURCES.md`, `nigredo/inbox/.gitkeep`, `nigredo/ouroboros/`, and `docs/history/2026-07-11-pre-portfolio-handoff.md`
- Modify: `PROJECT_ROADMAP.md` only to replace absolute archive paths with `<private-archive>/pilot-v0.1.3-20260711` while retaining P1 hashes and evidence counts

**Interfaces:**
- Produces: `audit_paths(paths: list[str], read_bytes: Callable[[str], bytes]) -> list[str]`
- Produces: `tracked_paths(repo_root: Path) -> list[str]`
- Produces: CLI exit code `0` with `Public tree audit: PASS` or `1` with one finding per line

- [ ] **Step 1: Write failing audit tests**

```python
from scripts.check_public_tree import audit_paths


def test_audit_rejects_runtime_paths_and_private_content() -> None:
    blobs = {
        "albedo/registry.jsonl": b"{}\n",
        "README.md": b"source: /Users/example/private.pdf\n",
        "paper.pdf": b"%PDF-1.7",
    }
    findings = audit_paths(sorted(blobs), blobs.__getitem__)
    assert any("tracked runtime artifact" in item for item in findings)
    assert any("absolute user path" in item for item in findings)
    assert any("PDF" in item for item in findings)


def test_audit_allows_code_schemas_and_synthetic_examples() -> None:
    blobs = {
        "athanasor/cli.py": b"print('ok')\n",
        "CONNECT_SCHEMA.yaml": b"schema_version: {type: integer}\n",
        "examples/synthetic-agent-input/connections.json": b"[]\n",
    }
    assert audit_paths(sorted(blobs), blobs.__getitem__) == []
```

- [ ] **Step 2: Run the focused tests and observe import failure**

Run: `UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python -m pytest tests/test_public_tree.py -q`

Expected: FAIL during collection because `scripts.check_public_tree` does not exist.

- [ ] **Step 3: Implement the index-based audit**

Implement exact constants and pure scanning first:

```python
RUNTIME_PREFIXES = (
    "albedo/", "citrinitas/", "rubedo/", "athanasor/vigil/reports/",
    "nigredo/ouroboros/",
)
RUNTIME_EXACT = {
    "athanasor/lapis/state.json", "athanasor/lapis/codex.md",
    "nigredo/SOURCES.md", "nigredo/inbox/.gitkeep",
}
ABSOLUTE_PATTERNS = (
    re.compile(rb"/Users/[^\s`\"']+"),
    re.compile(rb"[A-Za-z]:\\\\Users\\\\[^\s`\"']+"),
)
PILOT_ID_PATTERNS = (
    re.compile(rb"orcid[0-9]{8,}_[0-9]{6,}"),
    re.compile(rb"loopedworldmodels_[0-9]{6,}"),
    re.compile(rb"paper_[0-9]{6,}"),
)
FALLBACK_DUMP_PATTERNS = (
    re.compile(rb"LLM unavailable; fallback connection", re.IGNORECASE),
    re.compile(rb'"tags"\s*:\s*\[[^\]]*"fallback"', re.IGNORECASE),
)
PATTERN_LITERAL_FILES = {
    "scripts/check_public_tree.py",
    "tests/test_public_tree.py",
    "docs/superpowers/plans/2026-07-11-p2-public-baseline.md",
}
TEXT_SUFFIXES = {".md", ".py", ".toml", ".yaml", ".yml", ".json", ".jsonl", ".txt"}


def tracked_paths(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=repo_root, capture_output=True, check=True
    )
    return sorted(item.decode("utf-8") for item in result.stdout.split(b"\0") if item)


def audit_paths(paths: list[str], read_bytes: Callable[[str], bytes]) -> list[str]:
    findings: list[str] = []
    for rel in paths:
        normalized = rel.replace("\\", "/")
        if normalized.lower().endswith(".pdf"):
            findings.append(f"{rel}: tracked PDF")
        if normalized in RUNTIME_EXACT or normalized.startswith(RUNTIME_PREFIXES):
            findings.append(f"{rel}: tracked runtime artifact")
        if Path(normalized).suffix.lower() not in TEXT_SUFFIXES:
            continue
        data = read_bytes(rel)
        if normalized not in PATTERN_LITERAL_FILES:
            if any(pattern.search(data) for pattern in ABSOLUTE_PATTERNS):
                findings.append(f"{rel}: absolute user path")
            if any(pattern.search(data) for pattern in PILOT_ID_PATTERNS):
                findings.append(f"{rel}: pilot identifier")
            if Path(normalized).suffix.lower() in {".yaml", ".yml", ".json", ".jsonl"} and any(
                pattern.search(data) for pattern in FALLBACK_DUMP_PATTERNS
            ):
                findings.append(f"{rel}: fallback runtime dump")
    return findings
```

Add `main()` that reads tracked blobs from the working tree, prints all findings, and exits nonzero on any finding.

- [ ] **Step 4: Run tests and live audit**

Run focused tests again. Expected: PASS for pure unit tests.

Run: `UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python scripts/check_public_tree.py`

Expected: FAIL with tracked runtime, absolute path, and pilot identifier findings from the inherited tree.

- [ ] **Step 5: Remove tracked runtime material and tighten ignores**

Use `git rm -r` only for the explicitly listed tracked runtime paths. Update `.gitignore` to include:

```gitignore
albedo/
citrinitas/
rubedo/
nigredo/
athanasor/vigil/reports/
athanasor/lapis/state.json
athanasor/lapis/codex.md
athanasor/lapis/rejections.jsonl
```

Replace the three absolute paths in `PROJECT_ROADMAP.md` with the relative redaction token `<private-archive>/pilot-v0.1.3-20260711`. Delete the contaminated historical handoff after confirming every durable decision already exists in the roadmap.

- [ ] **Step 6: Prove the clean tree boundary**

Run the audit. Expected: PASS.

Run: `git ls-files | rg -i '\.pdf$|^(albedo|citrinitas|rubedo|nigredo|athanasor/vigil/reports)/'`

Expected: no output.

Run: `git grep -n -E '/Users/|[A-Za-z]:\\\\Users\\\\' -- . ':!docs/superpowers/plans/2026-07-11-p2-public-baseline.md'`

Expected: no output. The implementation plan itself may contain detector examples and is excluded only from this literal-pattern check; `check_public_tree.py` must allow its intentional test literals by exact file and line context rather than disabling repository-wide path detection.

- [ ] **Step 7: Run regression suite**

Run: `UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python -m pytest tests/test_public_tree.py tests/test_vigil_gates.py::test_live_repo_passes_all_gates -q`

Expected: PASS. The live repository gate test now passes because the runtime baseline is genuinely empty, while later tasks add non-vacuous strengthened gate fixtures.

- [ ] **Step 8: Commit**

```bash
git add -u .
git add scripts/check_public_tree.py tests/test_public_tree.py .gitignore PROJECT_ROADMAP.md
git commit -m "security: remove pilot runtime from public tree"
```

---

### Task 2: Synthetic fixture factory and exact Vigil contracts

**Files:**
- Create: `tests/fixture_factory.py`
- Modify: `tests/test_vigil_gates.py`
- Modify: `athanasor/vigil/verify.py`
- Modify: `athanasor/vigil/gates.yaml`

**Interfaces:**
- Produces: `write_library(root: Path, paper_id: str, *, explicit_targets: list[str] = []) -> Path`
- Produces: `write_exhaust(root: Path, paper_id: str, *, depth: int = 3, derivations: list[dict] | None = None) -> Path`
- Produces: `write_registry(root: Path, entries: list[dict]) -> Path`
- Produces: `write_connection(root: Path, a_id: str, b_id: str, **overrides: Any) -> Path`
- Changes: all five `check_*` functions continue returning `tuple[bool, str]` for an explicit root

- [ ] **Step 1: Add valid synthetic fixture builders**

Use IDs matching `SCHEMA.yaml`, such as `synthetic_001`. A valid claim is:

```python
{
    "statement": "A bounded queue reduces worst-case scheduling delay.",
    "confidence": "demonstrated",
    "evidence": "Synthetic result table 1, row 2.",
}
```

The source path must be relative: `sources/synthetic_001.txt`. A valid derivation includes both `follows_from: "claim_1"` and `source_claim: "claim_1"`.

- [ ] **Step 2: Write failing gate tests for every exact guarantee**

Add one focused function for each condition below; every function creates its root through `fixture_factory`, calls one `check_*` function, asserts the boolean, and asserts the failing ID or bounded-limit phrase in `detail`:

- `test_corpus_rejects_schema_invalid_record`
- `test_corpus_rejects_blank_claim_evidence`
- `test_coniunctio_rejects_schema_invalid_connection`
- `test_coniunctio_rejects_missing_library_record`
- `test_coniunctio_rejects_placeholder_evidence`
- `test_coniunctio_rejects_declared_explicit_link`
- `test_coniunctio_detail_states_declared_citation_limit`
- `test_calcinatio_rejects_schema_invalid_exhaustion`
- `test_calcinatio_rejects_missing_trace`
- `test_calcinatio_rejects_six_consecutive_speculative_items`
- `test_caput_mortuum_rejects_paper_id_mismatch`
- `test_caput_mortuum_rejects_depth_below_registry`
- `test_caput_mortuum_rejects_depth_above_registry`
- `test_caput_mortuum_rejects_cursor_on_non_exhausted_row`
- `test_empty_workspace_passes_all_structural_gates`

The blank-evidence test body is:

```python
write_registry(tmp_path, [registry_entry("synthetic_001", status="ingested_only")])
path = write_library(tmp_path, "synthetic_001")
payload = yaml.safe_load(path.read_text(encoding="utf-8"))
payload["claims"][0]["evidence"] = "   "
path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
passed, detail = vigil.check_corpus(tmp_path)
assert passed is False
assert "synthetic_001" in detail
assert "evidence" in detail
```

- [ ] **Step 3: Run tests and confirm current false passes**

Run: `UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python -m pytest tests/test_vigil_gates.py -q`

Expected: new tests fail because current gates check only partial structure.

- [ ] **Step 4: Implement strict, no-repair schema checks**

Import `parse_schema` and `validate` from `athanasor.schemas`. Add:

```python
SCHEMA_ROOT = PROJECT_ROOT


def _schema(name: str) -> dict[str, Any]:
    return parse_schema(SCHEMA_ROOT / name)


def _schema_errors(payload: dict[str, Any], name: str) -> list[str]:
    ok, errors, _, changed = validate_schema(payload, _schema(name), path="/", fix=False)
    if changed:
        errors.append("schema validation unexpectedly coerced input")
    return [] if ok and not errors else errors


def _specific_text(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and text.lower() not in {
        "unspecified", "unknown", "n/a", "none", "shared top-level tags in registry"
    }
```

Implement the Section 5 rules from the design exactly. Caput Mortuum must compare integer depths with `==`, validate `1 <= depth <= 5`, compare `exhaustion.paper_id`, and reject a non-exhausted row with non-null `exhausted_at_depth`. Calcinatio must count consecutive speculative derivations and fail at six.

- [ ] **Step 5: Make gate text honest and identical in scope**

Update `gates.yaml` descriptions, function docstrings, and success messages. Every gate description ends with its explicit limit. Do not use `proves`, `genuine`, or `novel` without the declared-citation limitation.

- [ ] **Step 6: Run focused and full tests**

Run: `UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python -m pytest tests/test_vigil_gates.py tests/test_audit_and_release.py -q`

Expected: PASS.

Run: `UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python athanasor/vigil/verify.py start`

Expected: PASS on the empty public runtime baseline.

- [ ] **Step 7: Commit**

```bash
git add tests/fixture_factory.py tests/test_vigil_gates.py athanasor/vigil/verify.py athanasor/vigil/gates.yaml
git commit -m "feat: align Vigil gates with executable checks"
```

---

### Task 3: Persistent Rubedo rejection fingerprints

**Files:**
- Create: `athanasor/rejections.py`
- Create: `tests/test_rejections.py`
- Modify: `athanasor/skills/promote.py`
- Modify: `athanasor/vigil/verify.py`
- Modify: `tests/test_vigil_gates.py`

**Interfaces:**
- Produces: `candidate_fingerprint(hypothesis: dict[str, Any]) -> str`
- Produces: `evidence_fingerprint(hypothesis: dict[str, Any]) -> str`
- Produces: `load_rejections(path: Path) -> tuple[list[dict[str, Any]], list[str]]`
- Produces: `append_rejection(path: Path, hypothesis: dict[str, Any], triage: dict[str, Any]) -> dict[str, Any]`
- Produces: `is_rejected(path: Path, hypothesis: dict[str, Any]) -> bool`

- [ ] **Step 1: Write canonical fingerprint tests**

Add four focused tests:

- `test_candidate_fingerprint_ignores_order_wording_and_status` compares two full dictionaries with reversed paper order and different descriptions/statuses and asserts equal digests.
- `test_evidence_fingerprint_changes_when_supporting_evidence_changes` changes only `gaps[0].supporting_evidence` and asserts unequal digests.
- `test_append_rejection_is_idempotent_for_same_candidate_and_evidence` calls `append_rejection` twice and asserts the ledger contains exactly one JSONL row.
- `test_load_rejections_reports_malformed_rows` writes `{"schema_version":1}\nnot-json\n`, then asserts two indexed validation errors and no accepted entries.

The candidate canonical JSON is exactly:

```python
{"paper_ids": sorted(set(ids)), "scope": normalized_scope}
```

The evidence canonical JSON is exactly a sorted list of objects containing `gap_type`, sorted `supporting_papers`, normalized `supporting_evidence`, and sorted `references`.

- [ ] **Step 2: Run tests and observe missing module**

Run: `UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python -m pytest tests/test_rejections.py -q`

Expected: collection failure because `athanasor.rejections` does not exist.

- [ ] **Step 3: Implement fingerprint and append-only ledger helpers**

Use `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` and SHA-256. Ledger entries contain:

```python
{
    "schema_version": 1,
    "artifact_type": "rubedo_rejection",
    "candidate_fingerprint": candidate_fingerprint(hypothesis),
    "evidence_fingerprint": evidence_fingerprint(hypothesis),
    "cluster_id": hypothesis["cluster_id"],
    "paper_ids": sorted(set(hypothesis["paper_ids"])),
    "decision": "rejected",
    "reviewer": triage["reviewer"],
    "note": triage["note"],
    "reviewed_at": triage["reviewed_at"],
}
```

Write one `fsync`-flushed JSON line. Do not append a byte-different duplicate for the same candidate/evidence fingerprint pair.

- [ ] **Step 4: Write failing promotion transaction tests**

Cover successful rejected decision, accepted decision without ledger write, and a simulated ledger write failure leaving the hypothesis and registry unchanged.

- [ ] **Step 5: Implement transactional promotion**

Before mutation, capture hypothesis and registry bytes. For `rejected`, append the ledger first; then write hypothesis and registry. If any later write fails, restore captured files and remove only the newly appended ledger bytes by restoring its captured bytes. The ledger path is `athanasor/lapis/rejections.jsonl`.

- [ ] **Step 6: Strengthen Nigredo Redux tests and gate**

The gate fails on malformed ledger rows, pending/investigate hypotheses whose candidate and evidence fingerprints match a rejection, and rejected hypotheses missing the same fingerprint pair in the ledger. A changed evidence fingerprint passes.

- [ ] **Step 7: Run focused tests and commit**

Run: `UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python -m pytest tests/test_rejections.py tests/test_vigil_gates.py -q`

Expected: PASS.

```bash
git add athanasor/rejections.py athanasor/skills/promote.py athanasor/vigil/verify.py tests/test_rejections.py tests/test_vigil_gates.py
git commit -m "feat: persist rejected hypothesis fingerprints"
```

---

### Task 4: Retrieval-only deterministic connect

**Files:**
- Create: `RETRIEVAL_SCHEMA.yaml`
- Create: `tests/test_connect_retrieval.py`
- Modify: `athanasor/skills/connect.py`
- Modify: `athanasor/cli.py`
- Modify: `scripts/check_connect_pruning.py`
- Modify: `scripts/check_semantic_pipeline.py`

**Interfaces:**
- Produces: `build_retrieval_candidate(a_entry, b_entry, *, pair_scope: str, similarity: float | None) -> dict[str, Any]`
- Produces: `_write_retrieval_candidate(root: Path, payload: dict[str, Any]) -> Path`
- Changes: `connect` with `llm=None` returns retrieval-candidate dictionaries and writes no connection artifacts

- [ ] **Step 1: Define failing behavior tests**

Create two exhausted synthetic records with a shared non-generic tag. Assert:

```python
outputs = connect(config=cfg, llm=None, all_scope=True)
assert [item["artifact_type"] for item in outputs] == ["retrieval_candidate"]
assert not list((root / "citrinitas" / "within_domain").rglob("*.yaml"))
assert not (root / "albedo" / "connections_analyzed.jsonl").exists()
assert registry.get("synthetic_001")["connected"] is False
assert outputs[0]["status"] == "pending_assessment"
assert "connection_type" not in outputs[0]
assert "novelty" not in outputs[0]
assert "confidence" not in outputs[0]
```

- [ ] **Step 2: Run and observe substantive fallback failure**

Run: `UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python -m pytest tests/test_connect_retrieval.py -q`

Expected: FAIL because `_analyze_pair` currently fabricates a connection.

- [ ] **Step 3: Add strict retrieval schema**

Required fields: `schema_version`, `artifact_type` fixed to `retrieval_candidate`, `pair_id`, `paper_a_id`, `paper_b_id`, `pair_scope`, `pair_domains`, `shared_tags`, `similarity` optional number, `selection_reasons`, `status` fixed to `pending_assessment`, and `metadata.method` fixed to `deterministic_retrieval`.

- [ ] **Step 4: Split retrieval from synthesis before pair analysis**

In `connect`, after deterministic pruning and record loading, branch on `llm is None`. Build, validate, and write a retrieval candidate under `citrinitas/retrieval_candidates/<a>_<b>.yaml`, append it to output, and continue without `_analyze_pair`, `_mark_connected`, or `_append_analyzed`.

`shared_tags` must exclude `GENERIC_PAIR_TAGS`; `selection_reasons` reports exact non-generic overlap and similarity threshold facts. Similarity may be `None` when unavailable.

- [ ] **Step 5: Make CLI labeling accurate**

When all returned items have `artifact_type == "retrieval_candidate"`, print `Generated N retrieval candidate(s).`; otherwise print `Generated N connection(s).` JSON output remains the returned list.

- [ ] **Step 6: Update deterministic check scripts and run tests**

Update check scripts to assert retrieval outputs rather than substantive fallbacks.

Run: `UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python -m pytest tests/test_connect_retrieval.py tests/test_common.py -q`

Run: `UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python scripts/check_connect_pruning.py && UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python scripts/check_semantic_pipeline.py`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add RETRIEVAL_SCHEMA.yaml athanasor/skills/connect.py athanasor/cli.py tests/test_connect_retrieval.py scripts/check_connect_pruning.py scripts/check_semantic_pipeline.py
git commit -m "feat: separate retrieval from connection synthesis"
```

---

### Task 5: Atomic `connect --from-file`

**Files:**
- Create: `tests/test_connect_from_file.py`
- Modify: `athanasor/skills/connect.py`
- Modify: `athanasor/cli.py`

**Interfaces:**
- Produces: `load_agent_connections(path: Path) -> list[dict[str, Any]]`
- Produces: `apply_agent_connections(records: list[dict[str, Any]], *, config: Config | None = None) -> list[dict[str, Any]]`

- [ ] **Step 1: Write parser and successful-import tests**

Cover bare-list input, wrapper-object input using the exact `connections` key, sorted pair normalization, forced `pending_review`, once-only cross penalty, canonical output path, registry `connected` markers, and analyzed ledger events.

- [ ] **Step 2: Write failure and atomicity tests**

Cover invalid JSON, wrong wrapper key, non-list records, schema errors, blank/placeholder evidence, same paper twice, missing registry/library records, packet duplicate, output collision, and a two-record packet with one invalid record producing no output or registry mutation.

- [ ] **Step 3: Run and observe missing adapter failures**

Run: `UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python -m pytest tests/test_connect_from_file.py -q`

Expected: FAIL because loader and adapter do not exist.

- [ ] **Step 4: Implement parse and prepare phase**

`load_agent_connections` accepts only a JSON list or exact `connections` wrapper. `apply_agent_connections` first builds a `PreparedConnection` list in memory containing normalized payload and destination. Use `validate_schema(payload, schema, path="/", fix=False)`. Set:

```python
payload["paper_a_id"], payload["paper_b_id"] = sorted((a_id, b_id))
payload["status"] = "pending_review"
payload["confidence_raw"] = _coerce_confidence(payload.get("confidence_raw", payload["confidence"]), fallback=0)
payload["confidence"] = max(1, payload["confidence_raw"] - (1 if scope == "cross_domain" else 0))
payload["score"] = _score_connection(payload, novelty_weight=True)
```

Reject placeholder evidence using the same shared helper as Coniunctio.

- [ ] **Step 5: Implement commit and rollback phase**

Capture registry and analyzed-ledger bytes plus any existing destination bytes. Write YAML to sibling temporary files, atomically replace all destinations, then update the registry and analyzed ledger. On any exception, restore all captured bytes and remove newly created destinations. Byte-equivalent existing pending files are idempotent and are returned without duplicate ledger events.

- [ ] **Step 6: Add mutually exclusive CLI mode**

Add `@click.option("--from-file", type=click.Path(exists=True, dir_okay=False, path_type=Path))`. Exactly one of `from_file`, `within`, `cross`, `paper_id`, and `all_scope` is required. Reject `--from-file` combined with `--no-llm` or `--reanalyze-depth-upgrades`. Loading the file must not construct an LLM client.

- [ ] **Step 7: Run tests and commit**

Run: `UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python -m pytest tests/test_connect_from_file.py tests/test_connect_retrieval.py tests/test_cli_errors.py -q`

Expected: PASS.

```bash
git add athanasor/skills/connect.py athanasor/cli.py tests/test_connect_from_file.py
git commit -m "feat: import agent connection records"
```

---

### Task 6: Atomic `detect --from-file` and no-fallback detection

**Files:**
- Create: `tests/test_detect_from_file.py`
- Modify: `athanasor/skills/detect.py`
- Modify: `athanasor/cli.py`
- Modify: existing detect/check tests that expect fallback hypotheses

**Interfaces:**
- Produces: `stable_cluster_id(paper_ids: Iterable[str]) -> str`
- Produces: `load_agent_hypotheses(path: Path) -> list[dict[str, Any]]`
- Produces: `apply_agent_hypotheses(records: list[dict[str, Any]], *, config: Config | None = None) -> list[dict[str, Any]]`

- [ ] **Step 1: Write import contract tests**

Cover bare-list packets and wrapper-object packets using the exact `hypotheses` key, stable sorted IDs, forced pending status, successful output, registry `detected` markers, and idempotent re-import.

`stable_cluster_id` is exactly:

```python
def stable_cluster_id(paper_ids: Iterable[str]) -> str:
    ids = sorted(set(str(item).strip() for item in paper_ids if str(item).strip()))
    digest = hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest()[:12]
    return f"cluster_{digest}"
```

- [ ] **Step 2: Write failure, rejection, and no-LLM tests**

Cover schema errors, fewer than three distinct papers, missing records, supporting paper outside cluster, mismatched cluster ID, duplicates, collision, packet atomicity, same rejected fingerprint suppression, changed-evidence re-entry, and no-LLM `detect` producing no hypothesis file.

- [ ] **Step 3: Run and observe failures**

Run: `UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python -m pytest tests/test_detect_from_file.py -q`

Expected: FAIL because import functions are absent and fallback detect still creates a hypothesis.

- [ ] **Step 4: Remove substantive fallback synthesis**

When `llm is None`, `_synthesize_cluster` returns `None`. Delete `_fallback_detect`. If the CLI no-LLM run has eligible clusters but no output, print a concise instruction to use `detect --from-file` rather than presenting a generated count as synthesis.

- [ ] **Step 5: Implement validate-then-commit hypothesis import**

Use `validate_schema(payload, schema, path="/", fix=False)`, require exact stable cluster ID, normalize paper IDs, verify supporting IDs, set `pending_review`, and call `is_rejected`. A matching candidate/evidence fingerprint is skipped and reported in structured output as `{"cluster_id": payload["cluster_id"], "status": "suppressed_rejection"}` without a hypothesis write. Changed evidence proceeds. Automated LLM detection uses the same `stable_cluster_id` and applies the same rejection check before writing.

Use the same temporary-file and registry-byte rollback pattern as Task 5.

- [ ] **Step 6: Add mutually exclusive CLI mode**

Exactly one of `from_file`, `domain`, `cross`, `cluster`, and `all_scope` is required. Reject `from_file` with `--no-llm`. File import does not construct an LLM client.

- [ ] **Step 7: Run tests and commit**

Run: `UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python -m pytest tests/test_detect_from_file.py tests/test_rejections.py tests/test_cli_errors.py -q`

Expected: PASS.

```bash
git add athanasor/skills/detect.py athanasor/cli.py tests/test_detect_from_file.py
git commit -m "feat: import agent hypothesis records"
```

---

### Task 7: Synthetic examples, Apache metadata, and truthful documentation

**Files:**
- Create: `examples/synthetic-agent-input/README.md`
- Create: `examples/synthetic-agent-input/connections.json`
- Create: `examples/synthetic-agent-input/hypotheses.json`
- Modify: `LICENSE`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `USER_GUIDE.md`
- Modify: `AGENTS.md`
- Modify: `tests/test_audit_and_release.py`
- Modify: `tests/test_public_tree.py`

**Interfaces:**
- Examples validate through the Task 5 and Task 6 loaders.
- Package metadata exposes SPDX `Apache-2.0` without changing version `0.1.3` during P2.

- [ ] **Step 1: Write failing metadata and example validation tests**

Assert:

```python
assert project["license"] == "Apache-2.0"
assert "License :: OSI Approved :: Apache Software License" not in project["classifiers"]
assert {"Programming Language :: Python :: 3.10", "Programming Language :: Python :: 3.11", "Programming Language :: Python :: 3.12"}.issubset(project["classifiers"])
assert "Apache License" in Path("LICENSE").read_text()
assert load_agent_connections(example_connections)
assert load_agent_hypotheses(example_hypotheses)
```

- [ ] **Step 2: Run and observe metadata/example failures**

Run: `UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python -m pytest tests/test_audit_and_release.py tests/test_public_tree.py -q`

Expected: FAIL because license metadata and examples are absent.

- [ ] **Step 3: Add authored synthetic packets**

Use exactly `synthetic_001`, `synthetic_002`, and `synthetic_003`. All content must be fictional and operational: bounded queues, threshold-based routing, and staged resource allocation. Example connection records contain specific fictional evidence labels such as `Synthetic claim 1` and never cite real papers or results. The hypothesis cluster ID must be generated by `stable_cluster_id`.

- [ ] **Step 4: Replace license and metadata**

Replace `LICENSE` with the unmodified Apache License, Version 2.0, January 2004 text. Add:

```toml
license = "Apache-2.0"
classifiers = [
  "Programming Language :: Python :: 3.10",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
]
```

The SPDX expression is the authoritative license metadata. Current setuptools rejects the superseded license classifier when a PEP 639 license expression is present.

- [ ] **Step 5: Align operator documentation**

Replace pilot counts and fallback demonstrations with the synthetic import flow. Copy the bounded gate contracts from the design without broadening them. State that retrieval candidates are not connections, declared citation visibility is not novelty research, imported artifacts remain pending review, and runtime directories are ignored.

- [ ] **Step 6: Run focused tests, audit, and check scripts**

Run: `UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python -m pytest tests/test_audit_and_release.py tests/test_public_tree.py -q`

Run: `UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python scripts/check_public_tree.py`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add examples LICENSE pyproject.toml README.md USER_GUIDE.md AGENTS.md tests/test_audit_and_release.py tests/test_public_tree.py
git commit -m "docs: publish synthetic Apache baseline"
```

---

### Task 8: Full P2 verification, clean-clone audit, and roadmap closeout

**Files:**
- Modify only if verification exposes P2 defects: files owned by Tasks 1-7
- Modify after all verification passes: `PROJECT_ROADMAP.md`

**Interfaces:**
- Produces: one clean P2 implementation commit SHA and one closeout commit if Vigil close mutates tracked authority state; mutable Lapis state should now be ignored and must not create a closeout commit.

- [ ] **Step 1: Run the complete local verification bundle**

```bash
UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python -m pytest -q
for script in scripts/check_*.py; do UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python "$script"; done
UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python scripts/hardening_audit.py
UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python -m compileall athanasor scripts tests
UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python scripts/check_public_tree.py
git diff --check
python3 athanasor/vigil/verify.py start
python3 athanasor/vigil/verify.py verify
```

Expected: every command exits `0`. Record exact test and script counts.

- [ ] **Step 2: Inspect the diff and acceptance matrix**

For each roadmap acceptance clause, record direct evidence:

| Requirement | Evidence |
|---|---|
| No PDFs, private IDs, paths, fallback dumps, snapshots, runtime evidence | `check_public_tree.py`, `git ls-files`, and `git grep` |
| Isolated tests | fixture factory plus no pipeline test reading root runtime data |
| Five gate descriptions equal executable scope | gate tests plus manual YAML/docstring comparison |
| No-LLM retrieval only | `test_connect_retrieval.py` and direct CLI run |
| `connect --from-file` | success, negative, atomicity, and CLI tests |
| `detect --from-file` | success, rejection, negative, atomicity, and CLI tests |
| Apache-2.0 metadata | metadata test and direct `pyproject.toml`/LICENSE inspection |

Any missing or indirect evidence keeps P2 open.

- [ ] **Step 3: Commit verified implementation state**

If verification fixes remain, commit them with a scoped message. Confirm `git status --short` is empty before the clean-clone check.

- [ ] **Step 4: Verify from a temporary clone**

```bash
tmp_clone=$(mktemp -d /tmp/azoth-p2-clone.XXXXXX)
git clone --no-local . "$tmp_clone/repo"
cd "$tmp_clone/repo"
UV_PROJECT_ENVIRONMENT="$tmp_clone/venv" uv sync --python 3.12 --extra dev
UV_PROJECT_ENVIRONMENT="$tmp_clone/venv" uv run --python 3.12 python -m pytest -q
UV_PROJECT_ENVIRONMENT="$tmp_clone/venv" uv run --python 3.12 python scripts/check_public_tree.py
UV_PROJECT_ENVIRONMENT="$tmp_clone/venv" uv run --python 3.12 python scripts/hardening_audit.py
python3 athanasor/vigil/verify.py start
```

Expected: all pass without ignored operator data.

- [ ] **Step 5: Record P2 completion in the roadmap**

Update the task ledger status to completed, replace the active-session table with P2 evidence, append verification rows, append a completed-session row, and set exactly one next task: `P3-T1 — Wheel resources and azoth init`. Do not rewrite earlier ledger rows except to redact absolute paths required by the public-tree contract.

- [ ] **Step 6: Run close and final cleanliness checks**

```bash
python3 athanasor/vigil/verify.py close
git status --short
UV_PROJECT_ENVIRONMENT=/tmp/azoth-p2-venv uv run --python 3.12 python scripts/check_public_tree.py
git diff --check
```

Expected: close passes, ignored runtime state does not dirty Git, public-tree audit passes, and only the intended roadmap closeout edit is present.

- [ ] **Step 7: Commit the roadmap closeout and verify the commit**

```bash
git add PROJECT_ROADMAP.md
git commit -m "docs: close P2 public baseline"
git status --short --branch
git show --stat --oneline HEAD
```

Expected: clean feature branch with P2 acceptance recorded. Do not push unless the user explicitly requests a push.
