# Azoth — The Apophenia Machine

Azoth is an opinionated, locally-runnable research synthesis pipeline. It ingests papers into structured YAML, exhaustively expands each record into derivations and missing angles, discovers structural connections across papers, and detects candidate research gaps. It is an **assistant** for candidate generation: everything leaves the pipeline in a `pending_review` state unless a human approves it.

This file is the product-facing entrypoint for the project and intended for PR review.

---

## Naming and project semantics

Azoth follows `AESTHETIC.md` conventions:

- **Azoth**: the whole engine.
- **Apophenia**: structural pattern-finding across fields.
- **Nigredo** (`nigredo/`): raw intake.
- **Albedo** (`albedo/`): structured extraction + canonical registry.
- **Citrinitas** (`citrinitas/`): structural connections.
- **Rubedo** (`rubedo/`): hypotheses and draft notes.
- **Athanasor** (`athanasor/`): orchestration, memory, gates, scripts, and state.

Non-alchemical names in machine payloads remain plain English:
- Directories: `nigredo`, `albedo`, `citrinitas`, `rubedo`, `athanasor`
- Data fields: `paper_id`, `status`, `source`, `tags`, `confidence`, etc.
- Commands: `ingest`, `awaken`, `connect`, `detect`, `draft`

---

## What makes this a real system (not prompt-only)

Azoth is validated by schema and gate checks at each stage:

- **Machine schemas** for every artifact:
  - `SCHEMA.yaml` (ingest/library)
  - `EXHAUST_SCHEMA.yaml` (exhaustion)
  - `CONNECT_SCHEMA.yaml` (pair connections)
  - `DETECT_SCHEMA.yaml` (gaps/hypotheses)
- **Schema validation command**: `azoth validate` and `scripts/validate.py` enforce structural correctness.
- **Vigil gate checks**: `python3 athanasor/vigil/verify.py start|verify|close` wraps substantive runs and blocks invalid states.
- **Registry state machine** in `albedo/registry.jsonl` tracks transitions.
- **CLI and session wrappers** convert low-level errors into command context so failures are visible in command output.

---

## Installation

```bash
# Python 3.10+
git clone <repo>
cd apophenia-machine
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Optional: install GPU/offline-friendly dependencies used by LLM and embeddings as needed by your environment.

---

## Recommended workflow

### 1) Start a session

```bash
python3 scripts/incipere.py
```

`/incipere` reads git state, `albedo/registry.jsonl`, and available memory/knowledge graph files, then prints:
- what has been completed
- where counts stand by status/domain
- practical next actions.

### 2) Add and ingest material

```bash
cp ~/Downloads/paper.pdf nigredo/inbox/
azoth ingest nigredo/inbox/
azoth ingest nigredo/ML/ --domain-override ML --no-llm
azoth status
```

`ingest` runs domain classification via `SEPARATIO` with LLM-first routing, and automatically falls back to local heuristics when the LLM backend is unavailable.
It moves files to domain folders and writes:
- `albedo/library/<paper_id>.yaml`
- registry entry (`status: ingested_only`)
- embedding records for candidate retrieval

`ingest`, `awaken`, `exhaust`, `connect`, `detect`, and `draft` also persist a light checkpoint entry to
`athanasor/lapis/memory.jsonl` after successful completion for crash recovery.

### 3) Awaken and exhaust papers

```bash
azoth awaken ML --depth 3 --count 3
azoth awaken --all --depth 4 --count 2
azoth awaken physics --reprocess
azoth exhaust --domain physics --depth 2 --count 5
```

`awaken` is the domain-subagent entrypoint.

`exhaust` gives explicit control over paper/pick scope.

Both emit schema-conformant records:
- `albedo/exhaust/<paper_id>_exhaust.yaml`
- registry status updates to `status: exhausted`, with `exhausted_at_depth`

### 4) Discover connections

```bash
azoth connect --within ML
azoth connect --cross physics ML
azoth connect --paper <paper_id>
azoth connect --all
```

Outputs go to:
- `citrinitas/within_domain/<domain>/<id1>_<id2>.yaml`
- `citrinitas/cross_domain/<id1>_<id2>.yaml`

### 5) Detect hypotheses and draft notes

```bash
azoth detect --within ML
azoth detect --cross physics ML
azoth detect --all
azoth detect --cluster cluster_xxx
azoth draft --top 3
azoth draft <cluster_id>
```

Outputs:
- `rubedo/hypotheses/<cluster_id>.yaml`
- `rubedo/drafts/<slug>.md`

### 6) Close a session

```bash
python3 scripts/concludere.py --findings-file findings.txt
```

`/concludere` persists findings into persistent memory (`memory.json`/`memory.jsonl`/`knowledge_graph*`), updates `athanasor/lapis/state.json`, appends to `athanasor/lapis/codex.md`, and commits when not disabled.

---

## CLI reference (current)

All commands are under `azoth` (entrypoint from `pyproject.toml`).

- `azoth ingest <PATH ...>`
  - `--reprocess`: re-ingest even if the paper is already in registry
  - `--domain-override <domain>`
  - `--no-llm`: fallback extraction path
  - `--json`
  - `--no-auto-checkpoint`

- `azoth awaken [DOMAIN] --all`
  - `--depth 1..5` (default 3)
  - `--count N`
  - `--reprocess`
  - `--no-llm`
  - `--json`
  - `--no-auto-checkpoint`

- `azoth exhaust <paper_id>`
  - `--domain`, `--all`, `--depth`, `--count`, `--reprocess`, `--no-llm`, `--json`
  - `--no-auto-checkpoint`

- `azoth status`
  - `--domain`
  - `--status {pending,ingested_only,exhausted}`
  - `--json`

- `azoth connect`
  - `--within <domain>`
  - `--cross <d1> <d2>`
  - `--paper <paper_id>`
  - `--all`
  - `--no-llm`, `--json`
  - `--no-auto-checkpoint`

- `azoth detect`
  - `--domain <domain>`
  - `--cross <d1> <d2>`
  - `--cluster <cluster_id>`
  - `--all`
  - `--no-llm`, `--json`
  - `--no-auto-checkpoint`

- `azoth draft`
  - `gap_id` positional
  - `--top N`
  - `--no-llm`, `--json`
  - `--no-auto-checkpoint`

Automatic checkpointing can be disabled globally with:
`AZOTH_AUTO_CHECKPOINT=0`

- `azoth validate`
  - `--all` or file/directory paths
  - `--schema <path>`
  - `--fix`

- `azoth migrate`
  - `--all` or file paths
  - version normalization flags
  - `--dry-run`, `--json`

- `azoth config`
  - `--show`
  - `--set KEY VALUE` (dot notation)

Also available:
- `python3 scripts/check_cli.py`
- `python3 scripts/check_pipeline_smoke.py`
- `python3 scripts/check_negative_paths.py`
- `python3 scripts/hardening_audit.py`
- legacy wrappers: `scripts/validate.py`, `scripts/migrate.py`

---

## Directory layout

```text
azoth/
├── nigredo/
│   ├── inbox/                 # raw intake
│   ├── ML/
│   ├── physics/
│   ├── mathematics/
│   ├── neuroscience/
│   ├── philosophy/
│   └── unclassified/
├── albedo/
│   ├── library/               # SCHEMA payloads
│   ├── exhaust/               # EXHAUST payloads
│   └── registry.jsonl         # processing state
├── citrinitas/
│   ├── within_domain/
│   ├── cross_domain/
│   └── reports/
├── rubedo/
│   ├── hypotheses/
│   └── drafts/
├── athanasor/
│   ├── cli.py                 # command entrypoint
│   ├── config.py
│   ├── domain_classifier.py
│   ├── embeddings.py
│   ├── llm.py
│   ├── pdf_parser.py
│   ├── registry.py
│   ├── schemas.py
│   ├── skills/
│   ├── session/
│   ├── scripts/
│   ├── vigil/
│   └── lapis/
├── scripts/
│   ├── incipere.py
│   ├── concludere.py
│   ├── validate.py / migrate.py
│   └── hardening_audit.py
└── SCHEMA.yaml, EXHAUST_SCHEMA.yaml, CONNECT_SCHEMA.yaml, DETECT_SCHEMA.yaml
```

---

## Core helpers and function map

### Core runtime (`athanasor/`)

- `config.py`
  - `load_config()`: load defaults + `azoth.config.yaml` + env overrides
  - `save_config()`
- `llm.py`
  - `LLMClient.complete(...)`
  - `LLMClient.complete_with_fallback(...)`
- `embeddings.py`
  - `EmbeddingStore.add`, `search`, `search_batch`, `save`, `load`
- `schemas.py`
  - `validate(payload, schema, fix=False)`
- `registry.py`
  - `Registry.add/update/get/list/list_by_status/list_by_domain`
- `pdf_parser.py`
  - `parse_pdf(path)`
- `domain_classifier.py`
  - `classify(...)` with LLM + heuristic fallback

### Skill layer (`athanasor/skills/`)

- `ingest.py`
  - `ingest_path(...)`: file ingestion + classification + schema validation + registry append
- `exhaust.py`
  - `run_exhaust(...)`: depth-controlled expansion into EXHAUST schema
- `connect.py`
  - `connect(...)`: pairwise similarity pruning + LLM assessment + schema writes
- `detect.py`
  - `detect(...)`: cluster synthesis + gap hypothesis generation
- `draft.py`
  - `run_draft(...)`: markdown output generation from hypothesis files

### Shared helpers (`athanasor/skills/common.py`)

- `ensure_dir`, `slugify`, `short_id`, `write_yaml`, `write_jsonl`, `load_yaml`, `now_iso`
- `run_vigil_check` (wraps phase-level gate checks)
- `move_to_domain` (deterministic ingest moves)

---

## Confidence contract

`SCHEMA.yaml` and `EXHAUST_SCHEMA.yaml` keep their own semantic tiers.

For connection/detection outputs, use shared 1–5 numeric confidence throughout:
- 1 = very low
- 2 = low
- 3 = moderate
- 4 = high
- 5 = very high

This is applied to:
- `connect` fields: `confidence`
- `detect` fields: `gaps[].confidence`, `gaps[].feasibility`

Cross-domain penalty is numeric in `connect`, then clamped to `1..5`.

---

## Gates and review rules

All outputs default to:

- `pending_review`
- No automatic confirmation
- Human triage required

Gates (in `athanasor/vigil/gates.yaml`) used by phase wrappers:
- Corpus
- Coniunctio
- Calcinatio
- Caput Mortuum
- Nigredo Redux

`athanasor/vigil/verify.py` runs:
- `start` before substantial skill execution
- `verify` after
- `close` during session wind-down to update persistent state/codex

---

## Inbound/outbound conventions

- Raw text artifacts in `nigredo/` are expected to be PDFs (`.pdf`) or text formats accepted by ingest path handling.
- JSONL registry and report artifacts are the source of truth for machine automation.
- Drafts are intentionally lightweight and human-editable.

---

## Useful files for PR review

- `BUILD_PROMPT.md`: original build charter
- `BUILD_AUDIT.md`: latest audit notes and hardening observations
- `AGENTS.md`: operating behavior model
- `AESTHETIC.md`: canonical naming and phase map
- `USER_GUIDE.md`: user workflow reference
- `athanasor/vigil/verify.py`: gate runtime

---

## License

MIT License (`LICENSE`).
