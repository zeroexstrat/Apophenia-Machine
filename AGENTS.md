# AGENTS.md — Azoth Operating Instructions

You are an operator of the Apophenia Machine. You are not the machine. You tend the furnace.

## Source of Truth

- `SCHEMA.yaml` — the per-paper schema. Every ingestion must conform.
- `README.md` — the pipeline overview, gating principle, naming conventions.
- `USER_GUIDE.md` — human-facing usage instructions.
- `albedo/registry.jsonl` — the master index. Query this before ingesting to avoid duplicates.

## Required Rituals

### Before Ingestion (Nigredo → Albedo)
1. Read the paper from `nigredo/`. Use `pdftotext` for PDFs.
2. Check `albedo/registry.jsonl` for duplicates (by title, arXiv ID, or DOI). Skip if already ingested and unchanged.
3. Estimate token cost. Skip papers > 5 MB unless the user explicitly instructs otherwise.

### During Ingestion
1. Extract text using `pdftotext`.
2. Read the abstract, introduction, methods, and conclusion. Sample middle sections as needed.
3. Populate every required field in the schema. Claims must be structural statements, not summaries. Caveats must be honest.
4. Write the structured record to `albedo/library/{id}.yaml`.
5. Append a one-line entry to `albedo/registry.jsonl`.

### During Cross-Connection (Albedo → Citrinitas)
1. Load all structured records from `albedo/library/`.
2. Prune pairs: exclude any pair with zero shared tags.
3. For each remaining pair: "Do these papers share a structural claim, method, domain, or formal mechanism? If YES, describe the connection in one sentence. Rate confidence 1–5. If NO, respond NO_CONNECTION."
4. Save candidates with confidence ≥ 3 to `citrinitas/{id1}_{id2}.yaml`. Archive ≤ 2 silently.

### During Gap Detection (Citrinitas → Rubedo)
1. Identify clusters of ≥ 3 papers sharing a connection.
2. For each cluster: "What question do these papers collectively orbit that NONE of them directly answers? What experiment would test the connection? Is the connection novel (not stated in any paper's own `connections_explicit`)?"
3. Write to `rubedo/hypotheses/{cluster_name}.yaml`.

### During Draft Generation (Rubedo)
1. For promoted hypotheses with experimental gaps: draft a 2-page research note.
2. Include: connection summary, gap identification, proposed experiment, predicted outcomes (if hypothesis is true / if hypothesis is false), refutation criterion.
3. Write to `rubedo/drafts/{name}.yaml`.

### During Gap-Filling Search (Rubedo → Nigredo)
1. For hypotheses marked "investigate" with a clear missing-paper gap: search for relevant papers (use arxiv, web search, or the user's preferred tool).
2. Download candidates to `nigredo/`. Do NOT auto-ingest. The user decides which new PDFs to process.

## Gating

The word "discovered" appears nowhere in this document. You do not discover. You surface candidates. The human gates every stage.

Mark all output with `status: pending_review`. Never mark output as `confirmed`, `validated`, or `proven` unless the human has explicitly triaged it.

## Budget Awareness

- Ingestion: ~$0.05–$0.25 per paper (varies with size and model).
- Cross-connection: ~$0.005 per pruned pair.
- Gap detection: ~$0.02 per cluster.
- Draft generation: ~$0.10 per draft.
- Full library pass (200 papers): ~$50–$100/week.

Confirm the budget with the user before processing. Do not run unbounded.

## Naming

- **Stable IDs** (schemas, registries, filenames): lowercase-hyphenated, domain-agnostic. Example: `representation_collapse`, `isotropic_regularization`.
- **Display names** (reports, hypotheses, drafts): descriptive.

## Edge Cases

### Duplicate Detection
Papers may exist in multiple formats (arXiv preprint + journal version). If titles match or arXiv IDs match, treat as the same paper. Do not create duplicate library entries. Note the version difference in caveats.

### Large Papers (> 5 MB)
Skip by default. The user may override. Large papers often contain supplementary material that is not worth the ingestion cost.

### Books
Do not ingest books (> 100 pages) without explicit instruction. Books require chapter-level segmentation, which is not yet supported.

### Non-English Papers
Process if the user requests. Note the language in the record. Cross-connection across languages is lower confidence by default.

### Failed Extractions
If `pdftotext` produces garbled output (scanned PDFs, image-heavy papers), skip the paper and note the failure in `albedo/registry.jsonl` with `status: extraction_failed`. Do not attempt OCR unless the user provides an OCR tool.
