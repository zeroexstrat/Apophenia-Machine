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
- `README.md` — pipeline overview, gating principle, naming conventions
- `USER_GUIDE.md` — human-facing usage instructions
- `albedo/registry.jsonl` — master index with processing status per paper

---

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
   - `unclassified` — does not clearly fit any domain; flag for human review
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
3. For each pair: "Do these papers share a structural claim, method, or domain? Rate confidence 1–5."
4. Save ≥3 to `citrinitas/within_domain/{domain}/{id1}_{id2}.yaml`.

### Cross-Domain Connections
1. Load all exhausted papers across all domains.
2. Prune heavily — only compare papers that share at least one tag.
3. For each pair: confidence rating with cross-domain penalty (effective -1 to confidence for different domains).
4. Save ≥3 to `citrinitas/cross_domain/{id1}_{id2}.yaml`.

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
4. Mark novelty explicitly: "novel: true" if no paper in the cluster cites the others. "novel: false" if the connection is already visible in their explicit citations.

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
