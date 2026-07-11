# P2 Sanitized Public Baseline Design

**Task:** P2-T1 — Sanitized public baseline and honest structural gates

**Status:** approved for specification through continuation of the active P2 goal

**Authority:** `PROJECT_ROADMAP.md` remains canonical. This document resolves P2 implementation details only.

## 1. Goal

Turn the P1-preserved repository into a data-independent public product baseline. A clean checkout must contain no pilot corpus, private runtime evidence, mutable state snapshots, absolute local paths, or fallback artifacts presented as research findings. The five named Vigil gates must state and enforce exactly what the code can prove. Agent-produced connection and gap records must have schema-validated file-import paths, while deterministic no-LLM connection runs must stop short of substantive synthesis.

P2 does not rewrite Git history, force-update `main`, delete tags or pull-request refs, modify the sealed private archive, package wheel resources, or implement `azoth init`. Those responsibilities remain in P3 and P4.

## 2. Selected approach

Use a data-empty runtime baseline plus wholly authored synthetic examples and isolated test fixtures.

The alternatives were rejected:

- Sanitizing selected pilot artifacts leaves provenance and identifier leakage risk and makes it hard to prove that public claims are independent of the private experiment.
- Shipping code without examples removes the leakage risk but gives users no concrete contract for the new `--from-file` workflows.

The public tree will therefore distinguish three artifact classes:

1. Product code and schemas are tracked.
2. Small synthetic input examples are tracked under `examples/` and are visibly labeled synthetic.
3. Runtime workspaces and all generated Albedo, Citrinitas, Rubedo, Vigil-report, embedding, and Lapis state artifacts are ignored.

## 3. Repository boundary

### 3.1 Remove from the tracked product

- All tracked `albedo/`, `citrinitas/`, and `rubedo/` runtime artifacts.
- Generated `athanasor/vigil/reports/` files.
- Generated `athanasor/lapis/state.json` and `athanasor/lapis/codex.md` snapshots.
- Tracked Ouroboros queues, reports, downloaded-source placeholders, and pilot source manifests under `nigredo/`.
- Historical handoff material or current documentation containing private pilot identifiers, PII-derived filenames, absolute local paths, or mutable local counts. Durable decisions needed by the roadmap will be restated without those values before contaminated narrative files are removed.
- The existing non-Apache license text.

No private artifact is transformed into a synthetic example. Synthetic IDs, titles, claims, and evidence must be newly authored and visibly fictional.

### 3.2 Retain in the tracked product

- Python source, root schemas, configuration defaults, tests, check scripts, operator documentation, and the canonical roadmap.
- No tracked runtime-directory placeholders; commands create required workspace directories on demand.
- A concise `examples/README.md` and synthetic JSON input packets demonstrating `connect --from-file` and `detect --from-file`.

### 3.3 Ignore rules

Ignore runtime directories as complete units. Keep public examples outside those directories so a normal pipeline run can never mutate a tracked example. Add mutable Lapis state and any rejection ledger to the runtime ignore boundary. Tests must assert the boundary rather than relying on developer-local ignore state.

## 4. Synthetic examples and test workspaces

Create one minimal three-document fictional cluster under `examples/synthetic-agent-input/`:

- `connections.json` contains schema-valid pending connection records for three fictional paper IDs.
- `hypotheses.json` contains one schema-valid pending hypothesis referencing those IDs.
- `README.md` states that the packet is synthetic, shows the file-import commands, and explains that source/library records must already exist in the target runtime workspace.

These example packets are documentation, not a runnable tracked workspace and not evidence of system performance.

Tests will use factories under `tests/fixtures.py` to create complete temporary workspaces. The factories will write only the smallest records required for each test. No test may read the repository-root registry, library, exhaustion, connection, or hypothesis paths as its substantive fixture. A repository-level audit test may inspect tracked filenames and content, but pipeline behavior tests must receive a temporary root explicitly.

## 5. Gate contracts

`athanasor/vigil/gates.yaml`, function docstrings, CLI reports, README, USER_GUIDE, and AGENTS gate summaries must use the same bounded language.

### 5.1 Corpus

Executable guarantee:

- Every registry row in `ingested_only` or `exhausted` state resolves to a readable library record.
- The record validates against `SCHEMA.yaml` without coercive repair.
- It contains at least one claim with non-empty statement text and non-empty evidence text.

Explicit limit: Corpus verifies structural trace presence, not scientific truth or adequacy of the cited evidence.

### 5.2 Coniunctio

Executable guarantee:

- Every persisted substantive connection validates against `CONNECT_SCHEMA.yaml`.
- Both referenced library records exist.
- A connection labeled `non-obvious` or `speculative` fails when either record's declared `connections_explicit` targets the other paper by normalized ID or exact normalized title.
- Evidence fields must be specific non-placeholder strings.

Explicit limit: this is a check against citations declared in the ingested records. It is not an external literature search and cannot establish novelty.

### 5.3 Calcinatio

Executable guarantee:

- Every exhaustion artifact for a processed registry row validates against `EXHAUST_SCHEMA.yaml`.
- Every derivation uses `derived`, `likely`, or `speculative` confidence.
- Every `derived` or `likely` derivation contains a non-placeholder trace to a source claim through the schema's trace field.
- A sequence exceeding the configured speculative ceiling fails.

Explicit limit: trace presence and enum validity do not prove that a derivation logically follows from its source.

### 5.4 Caput Mortuum

Executable guarantee:

- Each registry row marked `exhausted` has a readable exhaustion artifact.
- Artifact paper ID equals the registry paper ID.
- Artifact exhaustion depth equals the registry's `exhausted_at_depth` exactly and lies in the supported range 1 through 5.
- A non-exhausted registry row must not claim a completed exhaustion cursor.

Explicit limit: the gate detects durable state disagreement. It cannot reconstruct whether an external agent spent tokens twice before state was written.

### 5.5 Nigredo Redux

Executable guarantee:

- `azoth promote --decision rejected` writes a durable canonical fingerprint and human decision metadata to an append-only workspace rejection ledger before completing the hypothesis update.
- A later imported or generated hypothesis with the same semantic fingerprint is skipped unless its evidence fingerprint differs.
- The gate fails on a pending/investigate hypothesis matching a recorded rejected fingerprint, malformed ledger rows, or a rejected hypothesis missing its ledger entry.

The candidate fingerprint is a SHA-256 digest over canonical JSON containing the sorted paper IDs and normalized scope. It identifies the rejected cluster independently of generated wording. The evidence fingerprint is a separate digest over sorted gap types, supporting paper IDs, supporting evidence, and references. Reviewer name, note, timestamps, rank, descriptions, generated prose formatting, and mutable status are excluded from candidate identity. A cluster may re-enter review only when the evidence fingerprint changes.

Explicit limit: the first P2 integration records Rubedo hypothesis decisions because `azoth promote` is the repository's existing human-decision command. Connection-level human rejection remains unsupported and must not be claimed by gate text.

## 6. No-LLM connection behavior

`azoth connect --no-llm` may rank pairs for later assessment but may not create `CONNECT_SCHEMA` records, assign connection types, describe substantive relationships, claim novelty, or assign inference confidence.

For each pair that passes deterministic pruning, write a retrieval-candidate record under `citrinitas/retrieval_candidates/`. Its fields are limited to:

- stable pair ID and sorted paper IDs;
- within/cross scope and declared domains;
- shared non-generic tags;
- embedding similarity when available, otherwise `null`;
- deterministic selection reasons;
- `status: pending_assessment`;
- generation metadata identifying deterministic retrieval.

The command returns those records and reports them as retrieval candidates. It does not mark registry rows connected and does not append the pair to the substantive analyzed ledger. This allows a later LLM or file-import assessment to process the same pair.

A dedicated `RETRIEVAL_SCHEMA.yaml` makes this non-substantive contract explicit and machine-validatable.

## 7. `connect --from-file`

Add a mutually exclusive CLI mode accepting one JSON file containing either a list of connection objects or `{ "connections": [...] }`.

Processing is two-phase and atomic at the product level:

1. Parse and validate the entire packet without writing.
2. Normalize each pair to sorted IDs, require two distinct existing registry/library records, validate evidence fields, set `status: pending_review`, apply the cross-domain confidence penalty exactly once from `confidence_raw`, and reject duplicate pairs in the packet. P2 does not claim or apply connection-level rejection fingerprints because no connection decision command exists.
3. If any record fails, report indexed errors and write nothing.
4. If all records pass, write canonical connection YAML files, update registry connection markers, and append analyzed-ledger events.

Imported records never become accepted or confirmed through file import. Existing output collisions fail unless an existing byte-equivalent pending record makes the operation idempotent. `--from-file` cannot be combined with `--within`, `--cross`, `--paper`, `--all`, `--no-llm`, or depth-reanalysis flags.

## 8. `detect --from-file`

Add a mutually exclusive CLI mode accepting a list of hypothesis objects or `{ "hypotheses": [...] }`.

The entire packet is parsed before writes. Each record must:

- validate against `DETECT_SCHEMA.yaml` without repair;
- contain at least three distinct sorted paper IDs present in the registry and library;
- reference only supporting paper IDs inside its own cluster;
- use a stable cluster ID derived from the sorted paper IDs, rejecting mismatched supplied IDs;
- be normalized to `status: pending_review`;
- not match a rejection-ledger candidate fingerprint unless its evidence fingerprint changed;
- avoid duplicate cluster identities within the packet.

If any record fails, write nothing. Valid records are written canonically and registry detection markers are updated. Existing byte-equivalent pending outputs are idempotent; conflicting collisions fail. `--from-file` cannot be combined with scope flags or `--no-llm`.

No-LLM `detect` currently fabricates a substantive fallback hypothesis. P2 removes that behavior: without an LLM or an imported packet, detect returns no hypothesis and tells the operator to provide agent output with `--from-file`.

## 9. Failure and transaction behavior

- Input parse, schema, reference, collision, and fingerprint errors are collected with record indexes and surfaced as one CLI error.
- File-import validation performs no registry or output mutation.
- Commit-stage writes use temporary files followed by atomic replacement. Registry updates happen only after all output files are ready; on an update failure, new output files and registry changes are rolled back to their pre-command bytes.
- Vigil start remains authoritative. The P2 data-empty repository may pass gates vacuously, but non-vacuous gate fixtures must independently prove every failure and success condition.
- A missing runtime registry is a valid empty workspace, not an error for a clean checkout.

## 10. Apache-2.0 metadata

- Replace `LICENSE` with the canonical Apache License 2.0 text.
- Add the PEP 639 SPDX expression `license = "Apache-2.0"` and explicit Python 3.10, 3.11, and 3.12 classifiers to `pyproject.toml` without changing the release version. Do not combine the SPDX expression with the superseded license classifier because current setuptools rejects that metadata.
- Make README and package metadata agree. P2 does not publish a release.

## 11. Test strategy

All behavior changes use red-green-refactor cycles.

### 11.1 Public-tree audit

Add a tracked-tree audit that fails on:

- PDFs or other forbidden pilot binaries;
- tracked files in runtime output directories;
- known pilot identifier shapes and fallback dumps;
- macOS or Windows user-profile absolute paths, or repository-specific private archive paths;
- mutable Lapis state/handoff snapshots;
- license or package-metadata disagreement.

The audit scans `git ls-files` and file bytes rather than the local filesystem so ignored private operator data cannot affect the result. Synthetic example IDs are allowlisted only by exact path, not by broad pattern.

### 11.2 Gate tests

For every gate, include isolated positive and negative fixtures for every bullet in Section 5. Tests must prove that an empty root passes and that malformed evidence fails, preventing deletion-only false confidence.

### 11.3 Import tests

For both import commands, cover successful list and wrapped-object packets, schema failures, missing references, duplicate identities, collision behavior, forced pending status, atomic multi-record failure, CLI flag exclusivity, JSON output, and re-import idempotency.

### 11.4 No-LLM tests

Prove that deterministic connect writes only retrieval candidates, leaves substantive connection directories and analyzed ledgers untouched, and does not mark registry rows connected. Prove that no-LLM detect writes no hypothesis.

### 11.5 Completion verification

Run under the supported Python 3.12 environment:

1. targeted red/green tests per implementation slice;
2. complete `pytest` suite;
3. every `scripts/check_*.py` contract check;
4. `scripts/hardening_audit.py`;
5. `python -m compileall athanasor scripts tests`;
6. `git diff --check`;
7. tracked-tree privacy and artifact scans;
8. Vigil `start`, `verify`, and `close` from a clean commit;
9. a temporary clone of the P2 commit running the data-independent suite and audits.

Any test or gate that reads ignored operator data is a failure of the P2 design, even if it passes locally.

## 12. Documentation and roadmap closeout

README, USER_GUIDE, AGENTS, gate definitions, and CLI help will distinguish:

- deterministic retrieval from substantive synthesis;
- structural evidence validation from scientific validation;
- declared-citation visibility from novelty research;
- agent file import from human acceptance;
- tracked synthetic examples from ignored runtime artifacts.

At closeout, update `PROJECT_ROADMAP.md` append-only ledgers with the implementation SHA and exact verification evidence, set P2 complete only if every acceptance item passes, and name P3-T1 as the sole next goal. Do not update public `main` or public tags during P2.
