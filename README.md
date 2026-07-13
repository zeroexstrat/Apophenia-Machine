# Azoth — The Apophenia Machine

[![hardening](https://github.com/zeroexstrat/Apophenia-Machine/actions/workflows/hardening.yml/badge.svg?branch=main)](https://github.com/zeroexstrat/Apophenia-Machine/actions/workflows/hardening.yml)

Azoth is a local, human-gated research-operations pipeline. It converts technical documents into schema-validated evidence records, ranks paper pairs for assessment, stores substantive connection candidates, and organizes candidate gaps for review.

Azoth does not establish scientific truth or novelty. Generated and imported research artifacts remain `pending_review` until a named human records a decision.

## Five-minute demo

This local demo initializes a workspace, ingests one newly authored fictional text
record without a model, shows the resulting state, and runs the structural gates.

```bash
git clone https://github.com/zeroexstrat/Apophenia-Machine.git
cd Apophenia-Machine
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
azoth init .demo-workspace
cp examples/five-minute-demo/queueing-note.txt .demo-workspace/nigredo/inbox/
cd .demo-workspace
azoth ingest nigredo/inbox/queueing-note.txt \
  --domain-override mathematics \
  --no-llm
azoth status
python -m athanasor.vigil.verify verify
```

The demo proves local workspace initialization, text ingestion, fallback evidence
extraction, registry persistence, status reporting, and structural-gate execution.
It does not demonstrate model generation, ranking quality, substantive connection
validity, novelty, or benchmark performance. The input labels itself
`FICTIONAL DEMO INPUT — NOT RESEARCH EVIDENCE`.

## Public product boundary

The Git repository contains code, schemas, tests, documentation, and explicitly fictional examples. It does not contain a research corpus or generated runtime results.

Normal runs create ignored workspace data:

- `nigredo/` — source intake and domain queues
- `albedo/` — library records, exhaustion records, and registry state
- `citrinitas/` — retrieval candidates and substantive connections
- `rubedo/` — hypotheses, reviews, decisions, and drafts
- `athanasor/lapis/` — recovery state and rejection fingerprints
- `athanasor/vigil/reports/` — generated gate reports

The examples under `examples/` are synthetic documentation, not system-performance evidence.

## Engineering decisions

- **Immutable package, mutable workspace.** Schemas, default configuration, and gate
  definitions ship as package resources; user records and review state stay in an
  initialized workspace rather than `site-packages`.
- **Retrieval is not assessment.** Deterministic no-model pairing emits retrieval
  candidates only. A substantive connection requires a model-backed assessment or a
  schema-valid agent import and still remains `pending_review`.
- **Fail closed at boundaries.** Multi-record imports validate completely before
  writing, benchmark generation cannot access gold, and scoring requires an explicit
  lock-bound external gold path.
- **Make rejection durable.** Human rejection records the reviewed evidence
  fingerprint before closing the candidate, preventing the same packet from silently
  returning as pending.
- **Prove installed behavior.** The maintained wheel smoke test initializes and runs
  Azoth outside the checkout on Python 3.10, 3.11, and 3.12.

## Rejection as an output

The [looped-transformer prior-art case](docs/case-studies/looped-transformer-prior-art.md)
shows the authority boundary end to end: Azoth stored a plausible spectral-stability
gap as a candidate, primary sources contradicted its novelty premise, the human
decision was `rejected`, and the useful remainder became a proposed controlled
comparison and replication. The comparison was not run, and the reframe carries no
novelty claim.

## Installation

Azoth supports Python 3.10 through 3.12.

Stable Git release:

```bash
pip install 'git+https://github.com/zeroexstrat/Apophenia-Machine@v0.2.0'
```

Install a built wheel into an isolated environment, then initialize a user-owned workspace:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install /path/to/azoth.whl
azoth init research-workspace
cd research-workspace
azoth status
```

The wheel embeds immutable schemas, default configuration, and Vigil definitions under the `athanasor` package. `azoth init` copies only a configured runtime seed and creates mutable Nigredo, Albedo, Citrinitas, Rubedo, Lapis, and Vigil directories in the target. It never writes workspace state into the Python environment. This repository does not claim that the package is currently published on PyPI.

For development from a clone:

```bash
git clone https://github.com/zeroexstrat/Apophenia-Machine.git
cd Apophenia-Machine
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Optional semantic embeddings install `sentence-transformers` and its transitive dependencies:

```bash
pip install -e ".[dev,embeddings]"
```

Without that extra, the embedding layer uses a deterministic local hash representation. This keeps the workflow operational but does not make deterministic pair selection a substantive connection assessment.

## Artifact contracts

| Contract | Purpose |
|---|---|
| `SCHEMA.yaml` | Per-document Albedo evidence record |
| `EXHAUST_SCHEMA.yaml` | Per-document exhaustion output |
| `RETRIEVAL_SCHEMA.yaml` | Deterministic pair queued for assessment |
| `CONNECT_SCHEMA.yaml` | Substantive connection candidate |
| `DETECT_SCHEMA.yaml` | Candidate cluster gap report |

All connection and gap artifacts use integer confidence values from 1 through 5. Imported artifacts are validated without schema repair.

## Workflow

### 1. Ingest and classify

```bash
cp path/to/paper.pdf nigredo/inbox/
azoth ingest nigredo/inbox/
azoth status
```

If no configured model is available, the driving agent can classify records explicitly:

```bash
azoth reclassify --scope unclassified --dry-run
azoth reclassify --assignments classifications.json
```

### 2. Exhaust a bounded slice

```bash
azoth awaken ML --depth 3 --count 3
azoth exhaust --domain physics --depth 2 --count 5
```

An external agent can produce schema-shaped exhaustion buckets and import them:

```bash
azoth exhaust --from-file exhaustion.json
```

### 3. Retrieve pairs, then assess connections

With an available model, `connect` performs pair pruning followed by substantive assessment:

```bash
azoth connect --within ML
azoth connect --cross ML physics
azoth connect --all
```

With `--no-llm`, `connect` stops at deterministic retrieval:

```bash
azoth connect --all --no-llm
```

That command writes `retrieval_candidate` records only. It does not assign a connection type, novelty label, evidence claim, or inference confidence; it does not mark papers connected.

A driving agent can assess those pairs and import substantive records:

```bash
azoth connect --from-file examples/synthetic-agent-input/connections.json
```

`connect --from-file` validates the entire packet before any write, forces `pending_review`, normalizes pair identity and domains from the registry, applies the cross-domain confidence penalty exactly once, and rolls back output and registry changes if commit fails.

### 4. Synthesize or import candidate gaps

With an available model:

```bash
azoth detect --domain ML
azoth detect --cross ML physics
azoth detect --all
```

No-LLM detection deliberately produces no substantive hypothesis. Provide agent output instead:

```bash
azoth detect --from-file examples/synthetic-agent-input/hypotheses.json
```

Hypothesis import requires at least three existing paper records, a deterministic cluster ID, in-cluster supporting references, and `DETECT_SCHEMA.yaml` validity. A previously rejected cluster/evidence fingerprint is suppressed; changed evidence may re-enter review.

### 5. Review and decide

```bash
azoth draft <cluster_id>
azoth triage <cluster_id>
azoth review <cluster_id>
azoth experiment <cluster_id>

azoth promote <cluster_id> \
  --decision needs_prior_art \
  --reviewer <name> \
  --note "Run an external prior-art search before acceptance."
```

Valid decisions are `accepted`, `rejected`, and `needs_prior_art`. Rejection writes a durable cluster/evidence fingerprint before completing the hypothesis update. The same evidence packet cannot silently resurface as pending.

## Synthetic examples

[`examples/synthetic-agent-input/`](examples/synthetic-agent-input/README.md) contains fictional JSON packets for the two agent-import paths. The packets reference three fictional records and require a matching runtime registry and library. They are intended to show the contract shape only.

## Measured evaluation

The locked evaluation covers one frozen 12-paper, 66-pair operations-decision-
support suite. The 4/4/4 source balance spans prescriptive operations,
ML/data-science planning, and human/organizational decision-making. Rafael is the
final label authority; generation was sealed before gold access, and the metrics
were published without retuning after threshold misses.

The complete seven-run, 91-metric report and provenance digests are in
[`benchmarks/operations-decision-support-v1/results/`](benchmarks/operations-decision-support-v1/results/README.md).
The table below reproduces every frozen metric for the declared `5.6 Sol` run
directly from `locked-comparison.json`.

| Metric | Value | Numerator / denominator | 95% interval | Threshold |
|---|---:|---:|---|---|
| `macro_f1` | 0.5103 | 33 / 66 | 0.3868–0.6212 | not met |
| `unsafe_ood_assignment` | undefined | 0 / 0 | undefined–undefined | undefined |
| `claim_precision` | 0.9394 | 62 / 66 | 0.8543–0.9762 | met |
| `reference_recall` | 1.0000 | 27 / 27 | 0.8754–1.0000 | met |
| `candidate_recall` | 1.0000 | 27 / 27 | 0.8754–1.0000 | met |
| `workload_reduction` | 0.4242 | 28 / 66 | 0.3030–0.5303 | not met |
| `precision_at_5` | 0.7667 | 46 / 60 | 0.6833–0.8504 | met |
| `ndcg_at_10` | 0.9133 | 161.2897 / 176.5038 | 0.8752–0.9472 | met |
| `evidence_support` | 1.0000 | 132 / 132 | 0.9717–1.0000 | met |
| `supported_items` | 0.9394 | 62 / 66 | 0.8543–0.9762 | met |
| `useful_items` | 0.5152 | 34 / 66 | 0.3971–0.6315 | not met |
| `redundancy` | 0.0000 | 0 / 66 | 0.0000–0.0550 | met |
| `unsupported_derived_items` | undefined | 0 / 0 | undefined–undefined | undefined |

The model run met claim precision, both recall measures, ranking, evidence-support,
supported-item, and redundancy targets. It missed macro-F1, workload reduction,
and usefulness. OOD safety and unsupported-derived rates are undefined rather than
zero because their eligible denominators were zero.

These are suite-scoped decision-support measurements, not external-validity or
scientific-validity results. Validity and novelty remain human-reviewed. `5.6 Sol`
is the frozen backend label; the provider model identity was not exposed and is not
independently verified.

The public benchmark bundle freezes exact source identities, prompt, blinded schema,
rubric, 13 metrics, thresholds, uncertainty rules, lock order, and the `no_retuning`
boundary. Third-party source bytes, gold labels, rationales, pair-level failures, and
raw runs are not distributed in Git. Six fictional benchmark records test contracts
only and are not performance evidence.

## Vigil gates

Run installed Vigil before and after substantive pipeline work:

```bash
python -m athanasor.vigil.verify start
python -m athanasor.vigil.verify verify
python -m athanasor.vigil.verify close
```

| Gate | Executable guarantee | Explicit limit |
|---|---|---|
| Corpus | Processed library records validate and contain nonblank claim/evidence fields | Does not establish truth or evidence adequacy |
| Coniunctio | Connection records validate, reference library records, carry specific evidence, and respect declared explicit citations | Does not perform an external novelty search |
| Calcinatio | Exhaustion schemas, confidence enums, trace fields, and five-item speculative ceiling validate | Does not prove logical entailment |
| Caput Mortuum | Registry and exhaustion artifact IDs/depths agree exactly | Cannot reconstruct prior work before state was written |
| Nigredo Redux | Pending hypotheses cannot repeat a recorded rejected cluster/evidence pair | Covers Rubedo decisions recorded through `azoth promote`, not connection decisions |

Vigil also checks Git drift and registry review-state integrity. A missing runtime registry is a valid empty public baseline.

## Verification

```bash
python -m pytest -q
python scripts/check_public_tree.py
python scripts/check_pipeline_smoke.py
python scripts/check_wheel_install.py --wheel 'dist/azoth-*.whl' --python 3.10 --python 3.11 --python 3.12
python scripts/hardening_audit.py
python -m compileall athanasor scripts tests
```

`check_public_tree.py` audits the Git index rather than local ignored files. It rejects tracked PDFs, runtime outputs, mutable state snapshots, pilot identifiers, fallback dumps, and absolute user paths.

## Architecture

```text
nigredo sources
    ↓ ingest / classify
albedo evidence + exhaustion + registry
    ↓ deterministic retrieval
citrinitas retrieval candidates
    ↓ model assessment or connect --from-file
citrinitas substantive connection candidates
    ↓ model synthesis or detect --from-file
rubedo candidate gaps
    ↓ triage / review / promote
human decision + durable rejection memory
```

The CLI entrypoint is `athanasor/cli.py`; phase implementations live under `athanasor/skills/`; gate code lives in `athanasor/vigil/verify.py`.

## Limitations

- PDF parsing quality constrains downstream records.
- Schema validity proves structure, not correctness.
- Declared citation visibility is not literature-wide novelty checking.
- Pair retrieval quality depends on tags and available embeddings.
- Human review is required for scientific usefulness, validity, and promotion.
- The P7 benchmark measures one 12-paper suite; it does not establish external
  validity, literature-wide novelty, or provider model identity.
- Synthetic examples and the five-minute demo are contract tests only.

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
