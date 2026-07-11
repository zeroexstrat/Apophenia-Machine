# Azoth — The Apophenia Machine

Azoth is a local, human-gated research-operations pipeline. It converts technical documents into schema-validated evidence records, ranks paper pairs for assessment, stores substantive connection candidates, and organizes candidate gaps for review.

Azoth does not establish scientific truth or novelty. Generated and imported research artifacts remain `pending_review` until a named human records a decision.

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

## Installation

Azoth supports Python 3.10 through 3.12.

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
- No benchmark or performance claim is published from the synthetic examples.

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
