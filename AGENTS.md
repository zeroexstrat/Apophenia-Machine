# AGENTS.md — Azoth Operating Instructions

You are an operator of the Apophenia Machine. You are not the machine. You tend the furnace.

There are three kinds of agents in Azoth:

1. **Separatio** — the domain classifier. Runs on any new paper entering the inbox. Assigns a primary domain and moves the paper to the correct `nigredo/{domain}/` folder. Creates new domain folders as needed.

2. **Domain subagents** — dormant per-domain workers. One per `nigredo/{domain}/` folder. They do NOT run autonomously. They sleep until awakened by the user. When awakened, they process N papers (default 3, configurable) from their domain folder: ingest each paper to Albedo (structured YAML), then exhaust each paper (derivations, missing angles, exercises, experiments). Then they report what they completed and return to sleep.

3. **Parent synthesis agent** — handles cross-domain connections. Runs on user command (or cron). Loads all Albedo records and exhaustion outputs, prunes pairs without shared tags, discovers connections across domains, detects gaps in paper clusters, and generates hypotheses.

## The Dormancy Model

Domain subagents are activated by the user. They do not run on a schedule.

```
/awaken physics    → physics subagent processes 3 papers, reports, sleeps
/awaken ML         → ML subagent processes 3 papers, reports, sleeps
/awaken --all      → all subagents process 3 papers each, report, sleep
/awaken physics --depth 5 --count 5  → deep exhaustion, 5 papers
```

Each domain subagent maintains a cursor — which paper it last processed. The next awakening resumes from the next unprocessed paper. The cursor is stored in `albedo/registry.jsonl` per paper entry: `status: exhausted | ingested_only | pending`.

## Source of Truth

- `SCHEMA.yaml` — per-paper extraction schema
- `EXHAUST_SCHEMA.yaml` — per-paper exhaustion schema
- `RETRIEVAL_SCHEMA.yaml` — deterministic pair-retrieval schema (not a connection claim)
- `CONNECT_SCHEMA.yaml` — per-connection output schema (Citrinitas)
- `DETECT_SCHEMA.yaml` — per-cluster gap report schema (Rubedo)
- `README.md` — pipeline overview, gating principle, naming conventions
- `USER_GUIDE.md` — human-facing usage instructions
- `albedo/registry.jsonl` — master index with processing status per paper
- `athanasor/lapis/state.json` — ignored generated machine state; never narrative authority
- `PROJECT_ROADMAP.md` — canonical project plan and session handoff
- `athanasor/lapis/codex.md` — ignored generated compatibility handoff
- `athanasor/vigil/gates.yaml` — gate definitions (Corpus, Coniunctio, Calcinatio, Caput Mortuum, Nigredo Redux)

## The Vigil Protocol

Before any substantive work (ingestion batch, awakening, cross-connection pass), run the Vigil:

```
python3 athanasor/vigil/verify.py start
```

This checks:
- Git worktree: uncommitted changes? (drift)
- Registry: any candidate marked 'confirmed' without human triage?
- Exhaustion: any paper re-processed without --reprocess?
- Nigredo Redux: any rejected candidate re-surfacing?

After work completes:

```
python3 athanasor/vigil/verify.py verify
```

Before ending the session:

```
python3 athanasor/vigil/verify.py close
```

This updates generated gate state in `lapis/state.json`. The Vigil report is saved to `athanasor/vigil/reports/`. Human-readable progress and the next goal belong in `PROJECT_ROADMAP.md`.

### Gate Summary

| Gate | Alchemy | What It Checks | Severity |
|------|---------|---------------|----------|
| **Corpus** | The body | Processed library schemas and nonblank claim/evidence fields | Hard |
| **Coniunctio** | The marriage | Connection schema, records, evidence fields, and declared explicit citations | Hard |
| **Calcinatio** | Burning | Exhaustion schema, confidence/trace fields, and speculative ceiling | Hard |
| **Caput Mortuum** | Dead head | Exact registry/artifact paper ID and depth agreement | Hard |
| **Nigredo Redux** | Return to black | Durable Rubedo cluster/evidence rejection fingerprints | Hard |

These are structural guarantees. They do not establish scientific truth, logical entailment, evidence adequacy, or literature-wide novelty. Nigredo Redux covers Rubedo decisions recorded through `azoth promote`, not connection decisions.

If Vigil fails: do not claim the goal is complete. Fix the drift, record the failed gate as an open gap, or state exactly what remains unverified.

### Confidence Contract

- `SCHEMA.yaml` claims keep the five-tier evidence confidence:
  `proven`, `formalizable`, `demonstrated`, `hypothesized`, `speculative`.
- `EXHAUST_SCHEMA.yaml` derivation confidence stays:
  `derived`, `likely`, `speculative`.
- All connection and gap-detection prompt outputs use one shared numeric scale:
  `1` (very low), `2` (low), `3` (moderate), `4` (high), `5` (very high)
  for:
  - `connect` confidence
  - `detect` confidence
  - `detect` feasibility
- For UI/reporting only, treat `4–5` as high, `3` as moderate, `1–2` as low.

---

### Session Commands

- `/incipere` — begin or resume a working session.
  - Ensures there is an active git worktree (initializes one if missing).
  - Reads git state, `PROJECT_ROADMAP.md`, `albedo/registry.jsonl`, and any memory/knowledge JSON(db) available under `athanasor/lapis/`.
  - Prints the live snapshot plus the roadmap's active and next task.
  - Never rewrites the roadmap or compatibility pointer automatically.

- `/concludere` — close a working session.
  - Captures findings and appends them to persistent memory (`memory.json`/`memory.jsonl`).
  - Commit mode requires a clean tracked worktree and repeatable explicit `--stage PATH` arguments.
  - Runs `python3 athanasor/vigil/verify.py close` before staging, refreshes ignored runtime state, and commits only explicit tracked allowlist paths.
  - Refuses a pre-staged index, dirty tracked files, path traversal, repository-external paths, and failed Vigil close.
  - `--no-commit` writes ignored recovery memory only and does not mutate tracked state.
  - Never updates `PROJECT_ROADMAP.md`; the operator records verified results and the next task manually.

Sequence: begin with `/incipere`; commit substantive work; run `/concludere --no-commit` for ignored recovery memory; then update and commit `PROJECT_ROADMAP.md` as the session closeout.

## PHASE 0: SEPARATIO — Domain Classification

### Trigger
A new PDF appears in `nigredo/inbox/`.

### Procedure
1. Read the paper's title, abstract, and introduction.
2. Classify into a primary domain. Use this taxonomy or create a new domain if none fits:
   - `physics` — quantum field theory, condensed matter, cosmology, thermodynamics
   - `ML` — machine learning, deep learning, representation learning, NLP
   - `mathematics` — pure math, applied math, statistics, information theory
   - `neuroscience` — cognitive neuroscience, computational neuroscience, systems neuroscience
   - `philosophy` — philosophy of mind, epistemology, phenomenology, metaphysics
   - `biology` — molecular/developmental biology, basal cognition, bioelectricity, morphogenesis
   - `unclassified` — does not clearly fit any domain; flag for human review

Classification is open-vocabulary: the classifier may propose a domain outside this list.
Use `azoth reclassify` to re-file already-ingested papers and adopt confidently-proposed
new domains into `azoth.config.yaml` automatically — no manual taxonomy editing. Run
`azoth reclassify --scope unclassified --dry-run` to preview.

When you (the driving agent) have no configured LLM backend, you are the classifier:
read each unclassified paper's source file, decide its domain (propose new lowercase
domains as needed), write `[{"paper_id","domain","confidence","reasoning","proposed"?}]`
to a JSON file, and apply it with `azoth reclassify --assignments <file>`. This needs no
external model — it files papers using your own judgment while preserving IDs and status.

The same pattern extends to exhaustion: you can be the exhauster. Read a paper and
produce its exhaustion buckets (derivations, missing_angles, open_questions, experiments,
unstated_assumptions, exercises, necessary_connections), then `azoth exhaust --from-file
<json>` validates them against EXHAUST_SCHEMA and files them like the backend path. Because
every run validates to one schema, running the same library through different agents and
comparing with `scripts/exhaust_diff.py` measures how models differ in generation.
3. Move the paper from `nigredo/inbox/` to `nigredo/{domain}/`.
4. If the domain folder does not exist, create it.
5. Assign secondary domain tags in `albedo/registry.jsonl` for cross-domain inclusion.
6. Report: "Classified {title} → {domain}. {N} papers now in {domain}."

### Edge Cases
- A paper clearly spanning two domains (e.g., "Quantum Error Correction for Neural Networks"): pick the dominant domain for the folder (physics or ML) and tag the secondary domain for cross-domain connection passes. Do not duplicate the file.
- A paper that does not fit any domain: place in `unclassified/` and flag for human review.

---

## PHASE 1: ALBEDO — Ingestion + Exhaustion

Performed by domain subagents when awakened.

### Part A: Ingestion (for each unprocessed paper)
1. Extract text with `pdftotext`.
2. Read abstract, introduction, methods, conclusion. Sample middle sections.
3. Populate `SCHEMA.yaml`. Claims must be structural statements. Caveats must be honest.
4. Write to `albedo/library/{id}.yaml`.
5. Append to `albedo/registry.jsonl` with `status: ingested_only`.

### Part B: Exhaustion (for each ingested paper, at user-requested depth)
1. Load the structured record from `albedo/library/{id}.yaml`.
2. Using `EXHAUST_SCHEMA.yaml`, produce domain-appropriate exhaustion:
   - **Textbooks/lecture notes:** Focus on exercises, derivations, corollaries.
   - **Research papers:** Focus on implications, experiments, missing angles, open questions.
   - **Philosophy/essays:** Focus on missing angles, unstated assumptions, necessary connections.
   - **Review papers:** Focus on necessary connections, open questions, missing angles.
3. Write exhaustion output to `albedo/exhaust/{id}_exhaust.yaml`.
4. Update `albedo/registry.jsonl` entry: `status: exhausted`.
5. Report: "Exhausted {title}. {N} derivations, {M} missing angles, {K} exercises."

### Depth Levels
- **1 (skim):** Derivations only from major claims. One exercise if applicable. Surface missing angles.
- **2 (moderate):** All derivations. 2–3 exercises. Obvious missing angles.
- **3 (thorough — default):** Full exhaustion as per schema. All derivations, all obvious exercises, all missing angles, open questions, unstated assumptions, experiments where applicable.
- **4 (deep):** Depth 3 plus speculative derivations, challenging exercises, necessary connections to works outside the paper's domain.
- **5 (obsessive):** Every angle. Every corollary. Every exercise the material could support. Expects extended reasoning and multiple passes. High token cost.

### Budget Discipline
- Depth 3 on a 20-page paper: ~$0.10–$0.25
- Depth 5: ~$0.50–$1.00 per paper
- Default slice size: 3 papers per awakening
- Report cost after each awakening

---

## PHASE 2: CITRINITAS — Cross-Connection

Performed by the parent synthesis agent. Triggered by user command or cron.

### Within-Domain Connections
1. For each domain with ≥2 exhausted papers: pairwise comparison within the domain.
2. Prune pairs with zero shared tags.
3. With an LLM, assess structural claims/methods and rate confidence 1–5.
4. Without an LLM, write only `RETRIEVAL_SCHEMA.yaml` candidates under `citrinitas/retrieval_candidates/`.
5. A driving agent may import substantive assessments through `azoth connect --from-file`.
6. Save validated substantive confidence ≥3 records to `citrinitas/within_domain/{domain}/{id1}_{id2}.yaml`.

### Cross-Domain Connections
1. Load all exhausted papers across all domains.
2. Prune heavily — only compare papers that share at least one tag.
3. For each pair: confidence rating with cross-domain penalty (effective -1 to confidence for different domains).
4. Save ≥3 to `citrinitas/cross_domain/{id1}_{id2}.yaml`.

No-LLM retrieval never assigns connection type, novelty, evidence, or confidence and never marks registry rows connected.

### Synthesis Report
After each connection pass, produce a synthesis report:
- New connections found (count by confidence level)
- Connections from the exhaustion outputs that would not have been visible from extraction alone
- Top 5 highest-confidence connections for human triage

---

## PHASE 3: RUBEDO — Gap Detection + Drafts

### Gap Detection
1. Identify clusters of ≥3 papers sharing a connection across domains.
2. For each cluster: "What question do these papers collectively orbit that NONE of them answers? What experiment would test the connection? Is this novel?"
3. Write to `rubedo/hypotheses/{cluster_name}.yaml`.
4. Treat declared citation visibility as a bounded signal only; external novelty review remains human work.
5. Without an LLM, do not fabricate a hypothesis. Import driving-agent output through `azoth detect --from-file`.

### Gap-Filling Search
For hypotheses marked "investigate": search for papers that address the gap. Download candidates to `nigredo/inbox/`. Do NOT auto-ingest. The user decides.

### Draft Generation
For promoted hypotheses with experimental gaps: draft a 2-page research note following the template in USER_GUIDE.md. Write to `rubedo/drafts/{name}.yaml`.

---

## Gating

Every output at every phase is a candidate. Never mark output as "discovered," "proven," or "confirmed" without explicit human triage.

Mark all output `status: pending_review`. The human gates everything.

---

## Integration with Hermes

### Cron
```bash
# Weekly synthesis: Sunday 02:00 UTC
hermes cron create "0 2 * * 0" --name "azoth-weekly-synthesis" \
  --prompt "Run Citrinitas cross-domain connection pass and Rubedo gap detection on all exhausted papers. Produce synthesis report for human triage."
```

### Awakening Subagents (Manual)
The user awakens domain subagents via Hermes chat commands:
```
/awaken physics --depth 3 --count 5
```
This triggers the physics subagent to process the next 5 unexhausted physics papers at depth 3, then sleep.

The `--all` flag awakens all domain subagents simultaneously (parallel processing where supported, sequential otherwise).

### Dormancy State
Each awakening reads `albedo/registry.jsonl` to find papers with `status: pending | ingested_only` in the relevant domain. It processes up to `count` papers, then stops. It does not loop. It does not re-process exhausted papers unless `--reprocess` is specified.
