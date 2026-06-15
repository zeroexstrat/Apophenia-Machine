# Azoth — User Guide

## Overview

Azoth processes a personal research library through four phases:

1. **Drop** papers into `nigredo/`
2. **Ingest** them into structured records (`albedo/library/`)
3. **Connect** them across domains (`citrinitas/`)
4. **Hypothesize** from gaps (`rubedo/`)

You are the gate at every phase. The engine surfaces candidates. You decide.

---

## Getting Started

### Prerequisites

- A working Hermes Agent installation (for automated cron operation)
- `pdftotext` (install via `brew install poppler` on macOS, `apt install poppler-utils` on Linux)
- Python 3.10+ (for registry queries and schema validation)
- An LLM provider configured in Hermes

Manual operation does not require Hermes — see "Manual Operation" below.

### First Run

```bash
# Clone
git clone https://github.com/your-username/azoth.git
cd azoth

# Drop papers
cp ~/Downloads/some-paper.pdf nigredo/

# Run ingestion (via Hermes)
hermes chat -q "Ingest all papers in nigredo/ to albedo/library/ using the schema in SCHEMA.yaml. Write structured YAML records and update albedo/registry.jsonl."

# Review
ls albedo/library/
cat albedo/registry.jsonl

# Run cross-connection
hermes chat -q "Run the cross-connection phase: load all records from albedo/library/, compare pruned pairs, and write candidates with confidence >= 3 to citrinitas/."

# Triage
# Read citrinitas/*.yaml. Mark each: confirmed, rejected, or investigate.
```

---

## Phase-by-Phase

### Nigredo — The Inbox

`nigredo/` is where papers arrive. Accepted formats:
- PDF
- Plain text (`.txt`, `.md`)
- arXiv IDs (the ingest agent resolves them via the arxiv skill if available)

**Conventions:**
- Name PDFs with author-year-title format: `Fields2025_FEP_Compartmentalization.pdf`
- Do not add papers you do not intend to process
- Remove papers after successful ingestion (or move them to an archive of your choice)

### Albedo — Ingestion

The ingest agent reads each paper, extracts structured content, and writes a YAML file to `albedo/library/{id}.yaml`. It also appends a one-line entry to `albedo/registry.jsonl`.

**Prompt template for manual ingestion:**

```
Read the paper at nigredo/{filename} using pdftotext. 
Extract the following into a structured YAML record conforming to SCHEMA.yaml:
- Bibliographic metadata
- Structural claims (with confidence tiers: proven, formalizable, demonstrated, hypothesized, speculative)
- Methods and formalisms
- Techniques and implementable operations
- Caveats and limitations
- Explicit connections to other works (with relationship type and strength 1–5)
- Concept tags

Write the record to albedo/library/{id}.yaml. 
Append a one-line JSON entry to albedo/registry.jsonl.
```

**Schema validation:** Use `python scripts/validate.py` to validate all schema-bound artifacts before triage:

```bash
python scripts/validate.py --all
python scripts/validate.py albedo/library/<id>.yaml albedo/exhaust/<id>_exhaust.yaml \
  citrinitas/within_domain/<domain>/<id1>_<id2>.yaml rubedo/hypotheses/<cluster>.yaml
```

The validator enforces:
- `SCHEMA.yaml` for ingestion outputs
- `EXHAUST_SCHEMA.yaml` for exhaustion outputs
- `CONNECT_SCHEMA.yaml` for connection outputs
- `DETECT_SCHEMA.yaml` for hypotheses

`--fix` mode can repair obvious type/coercion issues and insert schema defaults for
missing optional fields.

### Citrinitas — Cross-Connection

The connection agent loads all structured records, prunes pairs with zero shared tags, and evaluates each remaining pair for shared claims, methods, or domains.

**How pruning works:**
- Papers with zero shared tags are excluded. This reduces the pair count from O(N²) to ~10–20%.
- Example: a paper tagged `[quantum_field_theory]` and a paper tagged `[urban_planning]` will not be compared unless you add a shared tag.

**Confidence levels:**
- 5: The papers share a central mechanism, formalism, or theorem.
- 4: The papers share a structural claim with different instantiations.
- 3: The papers share a domain and approach but differ in detail.
- ≤2: The connection is superficial or coincidental. Archived silently.

**Prompt template:**

```
Paper A (id: {id_a}):
  Claims: [list]
  Methods: [list]
  Domain: {domain}

Paper B (id: {id_b}):
  Claims: [list]
  Methods: [list]
  Domain: {domain}

Do these papers share a structural claim, a method, a formal mechanism, or a domain?
If YES: describe the connection in one sentence. Return JSON for each connection using
the fields in `CONNECT_SCHEMA.yaml`; rate confidence 1–5.
If NO: respond "NO_CONNECTION".
```

### Rubedo — Gap Detection

For each cluster of ≥3 connected papers, the detection agent asks:
1. What question do these papers collectively orbit that none of them directly answers?
2. What experiment would test the connection between them?
3. Is this connection novel? (Not stated in any paper's own `connections_explicit`.)
4. What paper, if it existed, would close the gap?

**Novelty check is critical.** If three papers already cite each other and describe the connection, you have not discovered anything. If they share a structural claim but come from different domains and none cites the others, the connection is genuinely novel.

### Draft Generation

For hypotheses marked "worth pursuing" with an experimental gap, the draft agent produces a 2-page research note:

```yaml
title: "Proposed Title"
connection_summary: "One paragraph on what connects these papers."
gap: "What question remains unanswered."
proposed_experiment:
  design: "Experimental protocol."
  predicted_true: "Expected result if hypothesis is correct."
  predicted_false: "Expected result if hypothesis is incorrect."
  refutation_criterion: "The measurement that would falsify the hypothesis."
status: DRAFT
```

---

## Triage Workflow

After each processing cycle, you receive candidates. Your triage decisions:

| Decision | Meaning | Action |
|----------|---------|--------|
| **Confirmed** | The connection or hypothesis is valid and worth preserving. | Document in your research notes. Add to your knowledge graph. |
| **Rejected** | The connection is wrong, trivial, or already known. | Archive with a note explaining the rejection. |
| **Investigate** | The connection is plausible but needs more evidence. | Trigger a gap-filling search → new papers → back to Nigredo. |

---

## Manual Operation

You do not need Hermes Agent to run Azoth. You can run each phase by pasting the prompt templates into any LLM interface (ChatGPT, Claude, Gemini, etc.) with the schema and your library files attached.

**Manual ingestion workflow:**
1. Open the LLM interface.
2. Attach `SCHEMA.yaml` and the paper from `nigredo/`.
3. Paste the Albedo prompt template.
4. Copy the output to `albedo/library/{id}.yaml`.
5. Append to `registry.jsonl` manually.

**Manual cross-connection:**
1. Attach all `albedo/library/*.yaml` files.
2. Paste the Citrinitas prompt template for each pruned pair.
3. Copy connection candidates to `citrinitas/`.

Manual operation is slower but fully functional. Automation via Hermes cron is a convenience, not a requirement.

## Session Skills

Azoth now includes two session lifecycle skills for reliable session handoff:

### `/incipere`

Run this at the start of a work cycle:

```bash
python3 scripts/incipere.py
```

It will:

- verify (or initialize) a git worktree,
- read `athanasor/lapis/state.json`, `albedo/registry.jsonl`, and existing memory/knowledge DB JSON,
- report:
  - git/worktree status,
  - counts by phase,
  - completed outputs,
  - recommended next actions.

### `/concludere`

Run this when you want to close the cycle:

```bash
cat findings.txt | python3 scripts/concludere.py -f "ingested 3 papers" -f "exhausted 2 papers"
```

Recommended usage:
- send one or more `-f/--finding` entries (repeatable),
- or pipe findings via stdin,
- or provide `--findings-file`.

`/concludere` will:

- persist findings in `athanasor/lapis/memory.*`,
- update `athanasor/lapis/state.json` and `athanasor/lapis/codex.md`,
- create a git commit containing session-state files.
- optionally run `python3 athanasor/vigil/verify.py close` (default).

---

## Scheduling

If using Hermes:

```bash
# Weekly processing: Sunday at 02:00 UTC
hermes cron create "0 2 * * 0" --name "azoth-weekly-cycle" \
  --prompt "Run the full Azoth pipeline: ingest new papers from nigredo/, cross-connect all librry records with confidence >= 3, detect gaps in clusters of >= 3 connected papers, and draft research notes for promoted hypotheses. Write the triage report for human review." \
  --skills azoth-ingest azoth-connect azoth-detect azoth-draft
```

Cron configuration lives in `athanasor/cron/`. Skills live in `athanasor/skills/`.

---

## Library Management

### Querying the Registry

```bash
# Count ingested papers
wc -l albedo/registry.jsonl

# Find papers by tag
grep "symmetry_breaking" albedo/library/*.yaml

# Find papers by author
grep "Fields" albedo/library/*.yaml

# List all unique tags
grep -h "tags:" albedo/library/*.yaml | sort -u
```

### Removing a Paper

1. Delete the YAML file from `albedo/library/`.
2. Remove the corresponding line from `albedo/registry.jsonl`.
3. The next cross-connection pass will not include it.

### Re-processing a Paper

1. Delete the YAML file and registry entry.
2. Re-add the PDF to `nigredo/`.
3. Run ingestion again.

---

## Limitations

- Cross-connection is O(N²) before pruning. Large libraries (>500 papers) will require compute budget planning.
- No automatic schema validation in v1. Spot-check manually.
- Books (>100 pages) are not supported without chapter-level segmentation.
- Scanned PDFs and image-heavy papers may fail extraction. Use OCR separately before ingestion.
- Non-English papers are lower confidence for cross-connection.
- The engine surfaces candidates at ~95% false positive rate. Triage is not optional.
