# HANDOFF.md — Azoth / Apophenia Machine

**Date:** 2026-06-14
**Project:** Azoth — The Apophenia Machine
**Location:** `~/Desktop/apophenia-machine/`
**Git:** 5 commits on `main`, clean worktree
**Status:** Architecture complete. Schema defined. Guardrails documented. No papers ingested yet. No skills built yet.

---

## 1. What This Is

Azoth is an open-source research synthesis engine built around an alchemical metaphor:

- **Nigredo** (blackening): raw PDF inbox, domain-classified into folders
- **Albedo** (whitening): structured YAML per paper + exhaustion (derivations, missing angles, exercises, experiments)
- **Citrinitas** (yellowing): cross-connection discovery across papers, within and across domains
- **Rubedo** (reddening): gap detection, hypothesis generation, draft research notes
- **Athanasor** (furnace): infrastructure — skills, cron, scripts

Every phase produces candidates. No phase produces final knowledge. Human gates everything.

---

## 2. Key Design Decisions

### 2.1 Dormancy Model (Not Continuous)

Domain subagents do not run autonomously. They sleep until awakened by the user. Rationale: the user controls which domains are relevant to current work. An ML subagent should not burn tokens processing physics papers at 3 AM when the user is working on ML.

Activation: `/awaken physics --depth 3 --count 5`

### 2.2 Exhaustion = Domain-Sensitive Deep Work

"Exhausting" a paper means different things by domain:
- Physics/math textbooks: solve exercises, derive corollaries, extend techniques
- Philosophy: identify missing angles, close open questions the author's own framework could have answered, name unstated assumptions
- ML papers: derive implications, propose experiments, identify gaps
- Review papers: surface necessary connections the review missed

Controlled by depth levels 1–5 (skim → obsessive). Schema in `EXHAUST_SCHEMA.yaml`.

### 2.3 Three Self-Termination Criteria

LLMs cannot naturally "exhaust" a paper — they will generate plausible derivations indefinitely. Three guardrails:

1. **Redundancy check:** After each batch of 5 items, ≥3 redundant → stop
2. **Speculative ceiling:** Last 5 consecutive items all `speculative` → stop
3. **Hard cap:** `page_count × depth_multiplier` (safety net)

When triggered, the subagent reports why it stopped and whether deeper exhaustion is available. Full design discussion in `EXHAUSTION_GUARDRAILS.md`.

### 2.4 Alchemical Naming Only

No fungal/mycelial naming. The Apophenia Machine is an independent project with its own aesthetic identity. It is not an organ of Symmetry-Breaking. It is designed to be a shareable GitHub product.

---

## 3. File Map

| File | Purpose |
|------|---------|
| `README.md` | Product landing page — what Azoth is, how it works, naming, quick start |
| `USER_GUIDE.md` | Human instructions — phase-by-phase, triage workflow, manual operation, library management |
| `AGENTS.md` | AI agent operating instructions — all four phases, Separatio, subagent awakening, termination criteria |
| `SCHEMA.yaml` | Per-paper extraction schema — claims, methods, techniques, caveats, tags |
| `EXHAUST_SCHEMA.yaml` | Per-paper exhaustion schema — derivations, exercises, missing angles, open questions, experiments |
| `EXHAUSTION_GUARDRAILS.md` | Design discussion — why each guardrail exists, rationale, unresolved questions |
| `LICENSE` | MIT |

---

## 4. Directory Structure

```
apophenia-machine/
├── nigredo/
│   ├── inbox/              # Unclassified PDFs (Separatio routes to domain folders)
│   ├── physics/
│   ├── ML/
│   ├── philosophy/
│   ├── neuroscience/
│   ├── mathematics/
│   └── unclassified/       # Papers that don't fit any domain
├── albedo/
│   ├── library/            # Per-paper structured YAML (SCHEMA.yaml)
│   ├── exhaust/            # Per-paper exhaustion output (EXHAUST_SCHEMA.yaml)
│   └── registry/           # registry.jsonl — master index with processing status
├── citrinitas/
│   ├── within_domain/      # physics↔physics, ML↔ML connections
│   └── cross_domain/       # physics↔ML, philosophy↔neuroscience
├── rubedo/
│   ├── hypotheses/         # Gap detection output (≥3 paper clusters)
│   └── drafts/             # 2-page research notes
├── athanasor/
│   ├── skills/             # Hermes Agent skills (not yet built)
│   ├── cron/               # Processing schedules (not yet configured)
│   └── scripts/            # Utility scripts (not yet written)
└── (root files as above)
```

---

## 5. What Exists vs. What Needs Building

### Done
- Architecture design (all five phases)
- Extraction schema (`SCHEMA.yaml`)
- Exhaustion schema (`EXHAUST_SCHEMA.yaml`)
- Self-termination guardrails (redundancy, speculative ceiling, hard cap)
- Agent instructions (`AGENTS.md`)
- User guide (`USER_GUIDE.md`)
- Design discussion (`EXHAUSTION_GUARDRAILS.md`)
- Git repository, clean worktree
- Directory structure

### Not Done
- Hermes skills (`athanasor/skills/`) — ingest, connect, detect, draft
- Cron configuration (`athanasor/cron/`)
- Schema validation script (`athanasor/scripts/`)
- Pilot ingestion of any paper
- Pilot cross-connection pass
- Pilot gap detection
- Any actual processing

---

## 6. Unresolved Design Questions

From `EXHAUSTION_GUARDRAILS.md` §9:

1. **Can an LLM reliably self-assess redundancy?** The redundancy check requires the subagent to compare its own output across batches. Hallucination risk. Possible mitigation: external redundancy scoring via embedding similarity.

2. **Is page count a meaningful proxy for content density?** A dense philosophy paper and a figure-heavy ML paper with the same page count have different exhaustion potentials. Possible mitigation: content-density estimation from the structured YAML record.

3. **Does the speculative ceiling prematurely terminate on genuinely speculative papers?** A paper whose claims are themselves speculative inherits that confidence. Possible mitigation: confidence inheritance rules distinguishing "derived from speculative claim" from "ungrounded speculation."

4. **Cumulative exhaustion across depth levels:** Should depth-5 output supplement or replace depth-3 output? Current design: additive. Risk: redundancy between depth levels.

---

## 7. Relationship to Other Projects

Azoth is independent of Symmetry-Breaking. It does not reference φ-note, AESTHETIC.md, or any personal project files. It is designed as a standalone GitHub product.

The rx2 and rx3 corpora in `~/Desktop/ai-projects/memory-sanity/` are the intended pilot library. They contain 41 papers (28 rx2, 13 rx3) already summarized manually. These would be the first batch ingested for schema validation and cross-connection ground-truth comparison.

---

## 8. The Gating Principle (Repeated Because It's the Most Important Thing)

**Every phase produces candidates. No phase produces final knowledge.**

The engine surfaces. The human decides. The word "discovered" appears nowhere in AGENTS.md. No output is marked `confirmed` without explicit human triage.

---

## 9. Next Steps (Suggested Order)

1. **Build Hermes skills** — `athanasor/skills/`: ingest, connect, detect, draft
2. **Pilot ingestion** — Process rx2 + rx3 (41 papers) to validate SCHEMA.yaml
3. **Run cross-connection** — Compare discovered connections to known ground truth (LeJEPA ↔ Fields, QECC ↔ anastomosis, V-JEPA 2 ↔ φ-expansion)
4. **Validate exhaustion** — Awaken one domain subagent at depth 3, test all three termination criteria
5. **Configure cron** — Weekly synthesis pass
6. **Scale** — Add remaining library sections, first full cross-connection pass
