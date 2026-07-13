# Azoth User Guide

## Operating model

Azoth is a workspace tool. The repository supplies code and contracts; your ignored runtime workspace supplies papers and generated artifacts.

The four phases are:

1. Nigredo — intake and domain routing.
2. Albedo — structured evidence and bounded exhaustion.
3. Citrinitas — deterministic pair retrieval followed by substantive connection assessment.
4. Rubedo — candidate gap synthesis, review, and human decisions.

Every connection and hypothesis remains `pending_review` until a named human uses `azoth promote` for a Rubedo decision. Scientific validity and novelty are not automated decisions.

## Prerequisites

- Python 3.10, 3.11, or 3.12
- `pdftotext` or PyMuPDF-compatible source parsing
- Optional configured LLM backend for generative extraction, connection assessment, and gap synthesis

Install a built wheel and create an independent workspace:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install /path/to/azoth.whl
azoth init research-workspace
cd research-workspace
azoth status
```

Azoth's schemas, default configuration, and Vigil gate definitions remain immutable package resources. The initialized directory contains user-owned runtime data and a copied `azoth.config.yaml` whose project root points to that directory. Re-running `azoth init` repairs missing empty directories but does not overwrite existing config, registry, or state files. It refuses non-empty directories that are not already Azoth workspaces.

Install for development from a repository clone:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Start and inspect a session

```bash
python3 scripts/check_durable_worktree.py
python3 scripts/incipere.py
python3 scripts/incipere.py --json
python -m athanasor.vigil.verify start
```

Incipere reads live Git and runtime state plus `PROJECT_ROADMAP.md`. A fresh public checkout has no runtime registry; that is a valid empty baseline.

Authoritative work must live in durable user storage. The durability check, `/incipere`, and `/concludere` reject repository roots beneath `/tmp`, `/private/tmp`, `/var/tmp`, or the platform temporary directory after resolving aliases. Temporary clones are reserved for disposable verification and must never contain the only copy of a branch or commit. Push milestone branches early; retain a verified Git bundle in durable private storage for long-running or private milestone work.

## Ingestion

```bash
cp path/to/document.pdf nigredo/inbox/
azoth ingest nigredo/inbox/
azoth status --json
```

Accepted local sources include PDF, TXT, and Markdown. Ingestion writes a schema-valid record to `albedo/library/` and one state row to `albedo/registry.jsonl`.

When a model backend is unavailable, local ingestion heuristics may still create a candidate record. Treat heuristic extraction as a review surface, not validated research evidence.

### Agent classification

A driving agent may classify unclassified records without a provider call:

```bash
azoth reclassify --scope unclassified --dry-run
azoth reclassify --assignments classifications.json
```

The assignments file is a JSON list of objects containing `paper_id`, `domain`, and optional confidence/reasoning fields.

## Exhaustion

Wake one domain for a bounded slice:

```bash
azoth awaken ML --depth 3 --count 3
azoth awaken --all --depth 2 --count 2
azoth exhaust --paper <paper_id> --depth 4
```

Depth ranges from 1 to 5. The registry cursor and exhaustion artifact must record the same exact depth.

### Agent exhaustion

An external agent may write exhaustion buckets to JSON and import them:

```bash
azoth exhaust --from-file exhaustion.json
```

The importer validates against `EXHAUST_SCHEMA.yaml`. It never promotes the artifact beyond candidate status.

## Connection workflow

### Model-backed assessment

```bash
azoth connect --within ML
azoth connect --cross ML physics
azoth connect --paper <paper_id>
azoth connect --all
azoth connect --within ML --reanalyze-depth-upgrades
```

Pair pruning uses non-generic shared tags and available embedding similarity. Model-backed assessment then produces `CONNECT_SCHEMA.yaml` candidates.

### Deterministic retrieval

```bash
azoth connect --all --no-llm --json
```

This produces `RETRIEVAL_SCHEMA.yaml` records under `citrinitas/retrieval_candidates/`. A retrieval candidate contains pair identity, domains, shared tags, similarity when available, and deterministic selection reasons.

It intentionally contains no connection type, substantive description, evidence claims, novelty label, or inference confidence. It does not update `connected` registry state.

### Agent connection assessment

```bash
azoth connect --from-file connections.json
```

The input is either a JSON list or an exact object with a `connections` list. The importer:

- validates every record before writing any record;
- requires two distinct registry and library records;
- normalizes sorted IDs and domains from the registry;
- forces `status: pending_review`;
- applies a cross-domain confidence penalty exactly once from `confidence_raw`;
- rejects duplicate pairs and conflicting output collisions;
- rolls back output, analyzed state, and registry state on commit failure.

See `examples/synthetic-agent-input/connections.json` for a fictional contract example.

## Hypothesis workflow

### Model-backed synthesis

```bash
azoth detect --domain ML
azoth detect --cross ML physics
azoth detect --all
```

Detect builds connected components of at least three papers and asks the configured model for a schema-valid gap candidate.

### No-LLM boundary

```bash
azoth detect --all --no-llm
```

This command does not fabricate a fallback hypothesis. It returns no substantive output and directs the operator to `detect --from-file`.

### Agent hypothesis synthesis

```bash
azoth detect --from-file hypotheses.json
```

The input is either a JSON list or an exact object with a `hypotheses` list. The importer:

- validates the full packet before writes;
- requires at least three distinct existing registry/library records;
- requires the deterministic cluster ID derived from sorted paper IDs;
- rejects supporting-paper references outside the cluster;
- forces `status: pending_review`;
- suppresses a previously rejected cluster with unchanged evidence;
- permits the same cluster to return when its evidence fingerprint changes;
- rolls back files and registry state on commit failure.

See `examples/synthetic-agent-input/hypotheses.json` for a fictional contract example.

## Human review path

```bash
azoth draft <cluster_id>
azoth triage <cluster_id>
azoth review <cluster_id>
azoth experiment <cluster_id>
```

Record a decision only after reviewing the evidence packet:

```bash
azoth promote <cluster_id> \
  --decision accepted \
  --reviewer <name> \
  --note "Reviewed the evidence and external prior art."

azoth promote <cluster_id> \
  --decision rejected \
  --reviewer <name> \
  --note "The current evidence does not support this candidate."
```

For rejection, Azoth writes a durable cluster/evidence fingerprint before completing hypothesis and registry updates. If any update fails, all affected files return to their prior bytes.

## Validation

```bash
azoth validate --all
python scripts/validate.py --all
python -m athanasor.vigil.verify verify
```

The five Vigil gates are structural:

- Corpus — valid processed library records with nonblank claim evidence.
- Coniunctio — valid connection records, specific traces, and declared-citation checks.
- Calcinatio — valid exhaustion confidence/trace fields and speculative ceiling.
- Caput Mortuum — exact registry/artifact identity and depth agreement.
- Nigredo Redux — durable suppression of unchanged rejected Rubedo evidence.

The installed gate definitions are versioned with the package; the repository authoring copy is `athanasor/vigil/gates.yaml`. None of these gates establishes scientific truth or literature-wide novelty.

## Runtime state and recovery

Normal slice commands write recovery checkpoints to ignored `athanasor/lapis/memory.jsonl` unless disabled:

```bash
AZOTH_AUTO_CHECKPOINT=0 azoth connect --all --no-llm
```

Runtime directories, Lapis snapshots, rejection ledgers, and Vigil reports are ignored. Public examples live under `examples/` so normal operation cannot mutate tracked evidence.

## Close a session

Run verification before close:

```bash
python -m pytest -q
python scripts/check_public_tree.py
python -m athanasor.vigil.verify verify
python -m athanasor.vigil.verify close
```

For a memory-only checkpoint:

```bash
python3 scripts/concludere.py --no-commit -f "recorded verified session findings"
```

Tracked project progress belongs in `PROJECT_ROADMAP.md`; generated Lapis state is runtime evidence, not narrative authority.

## Troubleshooting

- Empty retrieval: check that records are exhausted and share meaningful tags or embedding similarity.
- Empty no-LLM detect: expected; use `detect --from-file` for agent-produced synthesis.
- Corpus failure: validate the referenced library record and claim evidence.
- Caput Mortuum failure: reconcile registry `exhausted_at_depth` with the artifact depth and paper ID.
- Nigredo Redux failure: inspect the rejection ledger and whether the evidence packet actually changed.
- Dirty-tree Vigil failure: commit intended tracked changes or remove unrelated drift before substantive work.

## License

Azoth is licensed under the Apache License 2.0.
