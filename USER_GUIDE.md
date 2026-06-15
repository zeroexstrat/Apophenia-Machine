# Azoth — User Guide

## Overview

Azoth processes a personal research library through four phases:

1. **Nigredo** — drop papers into `nigredo/`.
2. **Albedo** — ingest into structured records (`albedo/library/`).
3. **Citrinitas** — generate cross-paper connections (`citrinitas/`).
4. **Rubedo** — detect gaps and draft hypotheses (`rubedo/`).

You are the gate at every phase.

## Prerequisites

- `pdftotext` (install via `brew install poppler` on macOS, `apt install poppler-utils` on Linux)
- Python 3.10+
- An LLM client configured in `azoth.config.yaml` (or use `--no-llm` for smoke runs)
- Optional: [Hermes Agent](https://github.com/NousResearch/hermes-agent) for cron automation

## First Run

```bash
git clone https://github.com/your-username/azoth.git
cd azoth
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

python3 scripts/incipere.py
```

Add papers and run a minimal cycle:

```bash
cp ~/Downloads/paper.pdf nigredo/
azoth ingest nigredo/paper.pdf
azoth awaken ML --depth 3 --count 3
azoth status --domain ML --status ingested_only
azoth connect --within ML
azoth detect --within ML
azoth draft --top 1
```

After each slice command (`ingest`, `awaken`, `exhaust`, `connect`, `detect`, `draft`), Azoth now writes an automatic recovery checkpoint to `athanasor/lapis/memory.jsonl` by default.
Disable this per command with `--no-auto-checkpoint` or globally with `AZOTH_AUTO_CHECKPOINT=0`.

```bash
python scripts/validate.py --all
python3 scripts/concludere.py -f "ingested 1 paper" -f "awakened ML at depth 3"
```

## Phase-by-Phase

### Nigredo — Inbox

`nigredo/` holds raw inputs. Accepted formats:

- `PDF`
- `TXT`/`MD`
- arXiv IDs (where the resolver is available)

You can place papers in domain subfolders (`nigredo/ML`, `nigredo/physics`, etc.) or in `nigredo/inbox/` for classification by tools.

### Albedo — Ingestion

Ingest PDFs to schema-conformant YAML records:

```bash
azoth ingest nigredo/paper.pdf
azoth ingest nigredo/inbox/ --domain-override ML
azoth ingest nigredo/ --reprocess
azoth status --json
```

Ingestion writes:
- `albedo/library/<paper_id>.yaml`
- one entry in `albedo/registry.jsonl` with status `pending` / `ingested_only`

### Citrinitas — Cross-Connection

Run pair discovery from exhausted papers:

```bash
azoth awaken ML --depth 3 --count 3
azoth connect --within ML
azoth connect --cross ML physics
azoth connect --all
azoth status --domain ML --json
```

`/awaken` is the conversational alias of `azoth awaken`.

### Rubedo — Gap Detection and Drafts

Detect candidate hypotheses and draft notes:

```bash
azoth detect --within ML
azoth detect --all
azoth draft --top 3
azoth draft <gap_id>
```

Draft output lands in `rubedo/drafts/`.

## Registry and status queries

```bash
azoth status
azoth status --domain ML
azoth status --status exhausted
azoth status --json
azoth config --show
azoth config --set llm.model gpt-4
```

## Validation and triage

Validate machine artifacts before review:

```bash
python scripts/validate.py --all
python scripts/validate.py albedo/library/<id>.yaml albedo/exhaust/<id>_exhaust.yaml
python scripts/validate.py citrinitas/within_domain/ML/<id1>_<id2>.yaml rubedo/hypotheses/<cluster>.yaml
```

Schema checks are strict and machine-readable. Human triage is still required:

- `pending_review` — default state after generation
- `accepted` — manually promoted
- `rejected` — intentionally discarded
- `investigate` — needs more evidence

Keep all triage decisions in your own note process (the project does not auto-confirm scientific claims).

## Session skills

### `/incipere`

```bash
python3 scripts/incipere.py
```

Refreshes session context from git, registry, and memory artifacts, then prints next actions.

### `/concludere`

```bash
cat findings.txt | python3 scripts/concludere.py --findings-file findings.txt
```

Persist findings to `athanasor/lapis/memory.*`, update `state.json`, and perform a clean commit.
This is still the manual “close” step after multiple commands; it is separate from the automatic checkpoint used
for crash-safe recovery.

## Scheduling

For optional Hermes automation, use cron in your environment. The repo does not require Hermes to run.

```bash
hermes cron create "0 2 * * 0" --name "azoth-weekly-cycle" \
  --prompt "Run ingest, exhaust, connect, detect, draft passes in a fixed order and return machine-validated outputs." \
  --skills azoth-ingest azoth-connect azoth-detect azoth-draft
```

## Library Management

### Querying the registry

```bash
wc -l albedo/registry.jsonl
python3 -m athanasor.cli status --domain ML --json
```

### Re-processing

For deterministic updates:

1. Remove the old library file and registry row.
2. Re-ingest the source from `nigredo/`.
3. Re-run `azoth awaken` and downstream commands.

## Troubleshooting

- If `azoth ingest` fails on PDFs, check `pdftotext` availability.
- If `azoth status` shows unexpected status codes, verify `albedo/registry.jsonl` entries with `json`.
- If `python scripts/validate.py --all` fails, inspect printed error lines and fix schema mismatches before triage.
- If `azoth connect` is empty repeatedly, check paper coverage (`status: exhausted`) and `--depth`.

## Limitations

- O(N²) candidate exploration before pruning; large libraries need batching.
- Large PDFs and scanned image-heavy PDFs remain hard.
- Opaque LLM confidence outputs still need human review.
- The system never substitutes for direct reading; it only accelerates candidate surfacing.
