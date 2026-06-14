# Azoth — The Apophenia Machine

> *"Solve et coagula. Dissolve and coagulate."* — Alchemical injunction

**Azoth** is a research synthesis engine. It ingests a curated library of papers and texts, extracts their structural content into a machine-traversable schema, discovers cross-document connections, detects conceptual gaps, and generates falsifiable hypotheses — all gated by human judgment.

It is not an autonomous scientist. It is a candidate-generation furnace. You are the alchemist.

---

## The Four Phases

| Phase | Directory | Alchemy | Function |
|-------|-----------|---------|----------|
| **Nigredo** | `nigredo/` | Blackening · dissolution | Inbox of raw PDFs and texts. The undifferentiated mass. |
| **Albedo** | `albedo/` | Whitening · purification | Structured ingestion. Raw matter → YAML schema. Each paper becomes a queryable node. |
| **Citrinitas** | `citrinitas/` | Yellowing · solar dawn | Cross-connection. Pattern emergence across the library. Candidates at confidence ≥ 3. |
| **Rubedo** | `rubedo/` | Reddening · completion | Gap detection. Clusters of ≥ 3 connected papers → hypotheses → research drafts. The Stone. |

---

## Directory Layout

```
apophenia-machine/
├── nigredo/             # Inbox — raw PDFs awaiting ingestion
├── albedo/
│   ├── library/         # Structured per-paper summaries (YAML)
│   └── registry.jsonl   # Master index of all ingested papers
├── citrinitas/          # Candidate connections between papers
├── rubedo/
│   ├── hypotheses/      # Gap-detection output (≥3 paper clusters)
│   └── drafts/           # 2-page research notes from promoted hypotheses
├── athanasor/
│   ├── skills/          # Hermes skills (ingest, connect, detect, draft)
│   ├── cron/            # Processing schedules
│   └── scripts/         # Utility scripts
├── SCHEMA.yaml          # The per-paper schema definition
├── AGENTS.md            # Agent instruction
├── README.md            # This file
└── .gitignore
```

---

## The Gating Principle

**Every phase produces candidates. No phase produces final knowledge.**

| Phase | Produces | Gate |
|-------|----------|------|
| Nigredo → Albedo | Structured YAML per paper | Spot-check schema accuracy |
| Albedo → Citrinitas | Candidate connections (≥3 confidence) | confirmed · rejected · investigate |
| Citrinitas → Rubedo | Hypotheses · open questions | worth pursuing · already known · wrong |
| Rubedo → (arxiv) | New PDFs in nigredo/ | Keep · discard |
| Rubedo → drafts/ | 2-page research notes | develop · shelve · wrong |

The engine surfaces. You decide.

---

## Naming Conventions

**Phases:** Alchemical — Nigredo, Albedo, Citrinitas, Rubedo.
**The whole:** Azoth — the universal solvent, the Alpha-Omega unity. Dissolves all boundaries without destroying what it touches.
**The housing:** Athanasor — the alchemical furnace. The compute substrate. The scheduling infrastructure.
**The act:** Apophenia — pattern-finding across domains that refuse to connect. The method, automated.

**Stable IDs** (for code, schemas, registries): lowercase-hyphenated, domain-agnostic.
**Display names** (for docs, UI, explanations): alchemical.
**Style reference:** `AESTHETIC.md` in `../Symmetry-Breaking/` (alchemical naming conventions only).

---

## Integration

| System | Role |
|--------|------|
| Hermes cron | Weekly processing: ingest → connect → detect |
| Arxiv skill | Gap-filling literature search |
| Sentinel (WP3) | Output artifact drift tracking |
| φ-note (WP1) | Concept definitions for tagging |
| Memory Layer | Durable recall of past connections/hypotheses |

---

## Related Artifacts

- **φ-note:** `../Symmetry-Breaking/research/symmetry-breaking-intelligence-deepening/phi-note.md`
- **Aesthetic conventions:** `../Symmetry-Breaking/AESTHETIC.md` (alchemical naming)
- **rx2 + rx3 corpora:** `../ai-projects/memory-sanity/rx2/`, `../ai-projects/memory-sanity/rx3/`
- **Essay (Anastomosis):** `../Dialogues/aleatoric-substack/mimo-substack-essay-v7.md`
- **Mimo archive analyses:** `../Dialogues/aleatoric-substack/mimo-substack-analyses.md`

---

> *"The archive was not one thing. It was a person in motion — dissolving, raging, reading, building, receiving — and the motion itself is the content."* — Rafa, *Anastomosis*

Azoth is that motion, automated.
