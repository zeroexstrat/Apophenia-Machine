# P6-T1 Benchmark Tooling Design

**Task:** P6-T1 — Benchmark CLI, scorer, report, and synthetic fixtures

**Effort:** High

**Authority:** `PROJECT_ROADMAP.md` remains the canonical program plan. The
frozen P5 public protocol, blinded schema, generation prompt, freeze manifest,
and private-gold commitment remain immutable inputs to this design.

**Approved approach:** Add a layered `athanasor.benchmark` implementation with
one thin `azoth benchmark` command group. Public preparation and generation
paths never accept or discover gold. Only the explicit `score` path accepts a
gold packet, after a run artifact already exists.

## 1. Goal and scope

P6 supplies deterministic, schema-versioned tooling for the frozen Operations
Decision Support v1 benchmark. It implements six isolated commands:

1. `validate` verifies the public protocol and any named P6 artifact without
   loading private gold;
2. `fetch` retrieves exact source bytes into an explicit repository-external
   directory and verifies identity, redirect evidence, media type, and SHA-256;
3. `prepare` converts verified source bytes into blinded generation packets in
   an explicit repository-external run directory;
4. `run` produces a locked output artifact from prepared packets using a named
   deterministic fallback or imports externally generated responses;
5. `score` compares an already-locked run with an explicitly named private gold
   packet and optional explicitly named human-review annotations;
6. `report` renders a deterministic Markdown report from a score artifact.

P6 proves the workflow with six newly authored fictional sources. It does not
run the real benchmark, expose real gold, publish performance claims, change a
frozen P5 field, or retune a threshold. Those actions remain P7 work.

## 2. Package and command architecture

The implementation is split by authority boundary rather than by CLI command:

- `athanasor.benchmark.artifacts` defines canonical P6 artifact shapes,
  version checks, atomic JSON writes, and field-addressed validation errors.
- `athanasor.benchmark.pipeline` implements public-only fetch, prepare, fallback
  generation, and response import. This module has no gold-packet API.
- `athanasor.benchmark.scoring` implements deterministic metrics and accepts
  gold only through an explicit function argument.
- `athanasor.benchmark.reporting` renders score artifacts without recomputing
  or silently changing metrics.
- `athanasor.benchmark.cli` exposes the six commands. `athanasor.cli` registers
  it as the `benchmark` subgroup and contains no benchmark business logic.

This separation makes accidental gold leakage mechanically harder: the module
that sees generation packets cannot accept a gold path, and the scoring module
cannot start generation or mutate a run.

## 3. Artifact contracts

Every P6 artifact is canonical UTF-8 JSON with sorted keys, a trailing newline,
`schema_version: 1`, `benchmark_id`, an `artifact_type`, and content/provenance
digests. Writes are atomic and refuse overwrite unless `--force` is explicit.

### 3.1 Prepared bundle

`azoth_benchmark_prepared` contains:

- the frozen source-manifest, protocol, prompt, blinded-schema, and freeze
  digests copied from the validated P5 package;
- the exact source-directory digest and extraction-tool identity;
- all 66 canonical blinded pair packets in canonical pair order;
- no lane, selection, gold, adjudication, threshold, benchmark-acceptance, or
  private filesystem metadata;
- `status: prepared`.

Each packet is validated against the frozen blinded schema. Source text is
represented only through schema-allowed extracted records, claims, methods,
caveats, tags, and explicit citations. The prepared artifact stores no source
path and no private-root path.

### 3.2 Run artifact

`azoth_benchmark_run` contains the prepared-bundle digest, immutable run
configuration, backend identity, seed, started/finished timestamps supplied by
the caller or normalized for deterministic fixture mode, and one result per
canonical pair. Each result records:

- pair and paper IDs;
- candidate inclusion and rank data;
- predicted relevance label `0..3` when the backend supplies one;
- generated candidate items with visible evidence references and confidence;
- validation status and non-secret error data.

The deterministic fallback uses only the blinded packets. It hashes normalized
visible tags, methods, claims, and evidence to produce stable candidates and
rankings. It is an engineering baseline, not a scientific result. An import
mode accepts a complete response file only after validating exact pair coverage
and rejecting gold-only fields recursively. No partial run is written.

### 3.3 Score artifact

`azoth_benchmark_score` binds the run digest, the P5 private-gold commitment,
the exact private packet digest, optional human-review annotation digest, metric
contracts, calculation version, and seed. It reports all 13 frozen metrics.

Metrics supported by pair labels are computed from the locked run and gold.
Metrics requiring OOD or human evaluation use an explicit optional annotation
packet; absent populations return `value: null`, numerator `0`, denominator
`0`, and the frozen undefined-case explanation. The scorer never treats missing
annotations as successes or failures.

Every metric record includes numerator, denominator, averaging, value,
uncertainty method and bounds when defined, threshold, comparison, and
`threshold_met`. Undefined values use `threshold_met: null`. Wilson intervals
and the seeded paired bootstrap are deterministic and contain their confidence
level and seed where applicable.

### 3.4 Report artifact

`report` writes Markdown from the score artifact only. It contains benchmark,
run, gold-commitment, and calculation provenance; a metric table with exact
numerators and denominators; uncertainty; threshold outcomes; undefined metrics;
failure counts; and limitations. Synthetic reports are visibly and repeatedly
labelled `SYNTHETIC CONTRACT TEST — NOT A PERFORMANCE CLAIM`.

## 4. Command isolation and paths

The CLI requires explicit paths. It does not search environment variables,
well-known directories, parent directories, or the repository for private gold.

- `validate` accepts public benchmark and named public P6 artifact paths only.
- `fetch` and `prepare` reject output/source roots inside the Git repository,
  including symlink and traversal aliases.
- `run` accepts prepared input and output paths but has no gold option.
- `score` requires `--gold PATH`; it rejects gold inside the repository and
  checks the private packet digest against the public freeze commitment before
  reading labels into metric calculations.
- `report` accepts only a score artifact and an output path.

Commands fail closed, emit concise field-addressed diagnostics, and leave no
partial destination. Existing destinations are immutable unless `--force` is
given. `--json` emits a stable machine-readable summary without secret or local
path disclosure.

## 5. Fetch and prepare behavior

`fetch` reuses the P5 source manifest and retrieval contract. For each source it
records requested URL, exact redirect chain, final URL, access date, media type,
byte count, exact version, license-evidence URL, and SHA-256 in a sidecar next to
the source. It downloads to a temporary file, verifies the bytes, then renames
atomically. Hash drift, unexpected media type, non-HTTPS redirects, redirect
loops, or identity mismatches abort the command without accepting the source.

For deterministic tests, a dependency-injected fetch function supplies fictional
bytes without network access. P6 tests never fetch the 12 real sources.

`prepare` first revalidates all source bytes and retrieval sidecars. It extracts
text with the installed PDF reader, normalizes visible fields deterministically,
builds canonical pair packets, validates every packet, and writes only after all
66 pass. Synthetic YAML records use a dedicated fixture loader and can exercise
the identical packet builder without masquerading as PDFs.

## 6. Deterministic scoring

The scoring library implements the frozen definitions without threshold
changes:

- four-class macro-F1 over all canonical pair predictions;
- unsafe OOD assignment;
- claim precision;
- reference recall;
- candidate recall;
- workload reduction;
- macro precision@5 by eligible query;
- macro nDCG@10 using graded relevance;
- evidence support;
- supported items;
- useful items;
- redundancy;
- unsupported `derived` items.

Pair orientation is canonical. Duplicate pairs, missing pairs, extra pairs,
invalid ranks, invalid labels, duplicate review IDs, and annotation references
outside the locked run are hard errors. Calculation functions are pure and
covered by hand-computed small examples, undefined-population tests, and repeat
runs that require byte-identical score output.

## 7. Synthetic fixture suite

The six existing fictional source records become a complete miniature
end-to-end fixture. P6 adds:

- a synthetic source-byte/retrieval bundle;
- all 15 canonical fictional pair packets;
- a synthetic gold packet and matching private commitment used only under
  temporary test directories;
- deterministic fallback and imported run fixtures;
- complete synthetic human annotations covering every non-pair metric;
- expected score and report fixtures with hand-checked numerators,
  denominators, ranking metrics, intervals, and undefined cases;
- corrupt fixtures for every schema, digest, path, leakage, incomplete coverage,
  overwrite, and isolation failure.

Test-only gold is generated in temporary private directories and is never
confused with the frozen 12-paper gold commitment. Synthetic reports carry no
public benchmark claim.

## 8. Error and recovery behavior

Validation collects deterministic field-addressed errors where safe. Fetch,
prepare, run, score, and report perform whole-input validation before replacing
any destination. Temporary files are removed on failure. Retrying the same
inputs yields the same content digest. A different input or configuration
creates a different digest and cannot silently reuse a locked artifact.

Network failures are reported per source without fabricating a successful
retrieval. Backend/import failures produce no partial run. Gold commitment
mismatch produces no score. Report rendering never falls back to recomputation.

## 9. Verification strategy

P6 acceptance requires fresh evidence for:

- CLI help and all six isolated subcommands;
- recursive gold-field rejection on every generation-side artifact;
- explicit-path and repository-external private/source boundaries, including
  symlink and traversal aliases;
- deterministic atomic artifact writing and overwrite refusal;
- offline fictional fetch and complete prepare coverage;
- byte-identical repeated fallback runs, scores, and reports;
- complete response import with no partial acceptance;
- hand-computed tests for every metric and uncertainty method;
- null/zero-denominator behavior for every unavailable population;
- private commitment mismatch rejection before score output;
- synthetic end-to-end validate/fetch/prepare/run/score/report;
- full test suite, maintained checks, public-tree audit, hardening audit,
  compileall, installed-wheel smoke on Python 3.10-3.12, and all seven Vigil
  gates;
- a clean tracked worktree and a roadmap closeout with exactly P7-T1 next.

## 10. Acceptance boundary

P6-T1 is complete only when:

1. all six commands exist and their inputs remain authority-isolated;
2. generation cannot receive, discover, or retain private gold;
3. fetch and prepare verify exact source identity and build canonical blinded
   packets without repository-private writes;
4. fallback and response-import runs lock deterministic, complete artifacts;
5. scoring reproduces all applicable frozen metrics from locked synthetic
   inputs and reports unavailable metrics honestly;
6. reporting reproduces exact score provenance, denominators, uncertainty, and
   limitations without recomputation;
7. fictional fixtures cover every contract and major failure path and are
   unmistakably non-performance evidence;
8. clean-clone and installed-wheel execution prove the CLI is package-portable;
9. public Git contains no real gold, third-party source bytes, run output,
   private paths, or benchmark performance claim;
10. Vigil passes and the roadmap records P6 evidence with exactly one next task,
    P7-T1.

P6 remains incomplete if any command shares an implicit gold path, any metric
omits its numerator or denominator, any score can be produced from a commitment
mismatch, any synthetic result can be mistaken for a real benchmark result, or
package-installed execution depends on the source checkout.
