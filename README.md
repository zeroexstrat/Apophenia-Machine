# Azoth — The Apophenia Machine

> *"Solve et coagula. Dissolve and coagulate."* — Alchemical injunction

Azoth is an open-source research synthesis engine. It ingests a personal library of papers and texts, extracts their structural content into a machine-traversable schema, discovers cross-document connections, detects conceptual gaps, and generates falsifiable hypotheses — all gated by human judgment.

It is not an autonomous scientist. It does not publish papers for you. It is a candidate-generation furnace. You are the alchemist.

---

## Quick Start

```bash
git clone https://github.com/your-username/azoth.git
cd azoth
```

Drop PDFs into `nigredo/`. Run the ingestion phase. Review the output. Gate everything.

Azoth is designed to run as a periodic batch pipeline on Hermes Agent (via cron), but can be operated manually as well.

---

## The Four Phases

| Phase | Directory | Alchemy | Function |
|-------|-----------|---------|----------|
| **Nigredo** | `nigredo/` | Blackening · dissolution | Raw PDFs and texts. The undifferentiated mass awaiting processing. |
| **Albedo** | `albedo/` | Whitening · purification | Structured ingestion. Raw matter → YAML schema. Each paper becomes a queryable node. |
| **Citrinitas** | `citrinitas/` | Yellowing · solar dawn | Cross-connection. Pattern emergence across the library via pairwise comparison. |
| **Rubedo** | `rubedo/` | Reddening · completion | Gap detection, hypothesis generation, research note drafts. The Stone. |

---

## How It Works

```
Nigredo (inbox) → Albedo (structured YAML per paper)
                            ↓
                     Citrinitas (connection candidates, confidence ≥ 3)
                            ↓
                     Rubedo (gap detection → hypothesis → draft)
                            ↓
                       You (triage: confirm / reject / investigate)
```

Processing is periodic — weekly by default. Output is a triage report for human review. The engine surfaces candidates. You decide what survives.

---

## The Gating Principle

**Every phase produces candidates. No phase produces final knowledge.**

| Phase | Produces | Human Gate |
|-------|----------|------------|
| Nigredo → Albedo | Structured YAML per paper | Spot-check schema accuracy |
| Albedo → Citrinitas | Candidate connections (≥3 confidence) | confirmed · rejected · investigate |
| Citrinitas → Rubedo | Hypotheses, open questions | worth pursuing · already known · wrong |
| Rubedo → arxiv → Nigredo | New PDFs in inbox | Keep · discard |
| Rubedo → drafts | 2-page research notes | develop · shelve · wrong |

---

## Directory Layout

```
azoth/
├── nigredo/             # Inbox — raw PDFs awaiting ingestion
├── albedo/
│   ├── library/         # Structured per-paper summaries (YAML)
│   └── registry.jsonl   # Master index of all ingested papers
├── citrinitas/          # Candidate connections between papers
├── rubedo/
│   ├── hypotheses/      # Gap-detection output (≥3 paper clusters)
│   └── drafts/           # 2-page research notes
├── athanasor/
│   ├── skills/          # Hermes Agent skills
│   ├── cron/            # Processing schedules
│   └── scripts/         # Utility scripts
├── SCHEMA.yaml          # The per-paper schema definition
├── USER_GUIDE.md        # Human-readable usage instructions
├── AGENTS.md            # AI agent operating instructions
├── LICENSE              # MIT License
└── README.md            # This file
```

---

## Requirements

- [Hermes Agent](https://github.com/NousResearch/hermes-agent) (for cron-scheduled operation)
- `pdftotext` (from poppler) for PDF extraction
- `python3` 3.10+ for registry queries and schema validation
- An active LLM provider configured in Hermes (any provider; the pipeline is provider-agnostic)
- Optional: [arxiv skill](https://hermes-agent.nousresearch.com/docs/reference/skills-catalog) for gap-filling literature search

Manual operation does not require Hermes — you can run each phase by prompting your preferred LLM with the schema and instructions.

---

## The Schema (SCHEMA.yaml)

Every ingested paper becomes a structured YAML record with:
- **Bibliographic metadata** (title, authors, year, path, arXiv ID, DOI)
- **Claims** — structural statements with confidence tiers (proven / formalizable / demonstrated / hypothesized / speculative)
- **Methods** — formalisms, mathematical frameworks, inferential techniques
- **Techniques** — algorithms, architectures, implementable operations
- **Caveats** — honest constraints and limitations
- **Explicit connections** — what the paper itself cites, with relationship type and strength
- **Tags** — concept index for cross-connection pruning

See `SCHEMA.yaml` for the full specification.

---

## Naming

Every term is alchemical.

| Term | Meaning |
|------|---------|
| **Azoth** | The whole — the universal solvent, the Alpha-Omega unity |
| **Apophenia** | The act — pattern-finding across domains that refuse to connect |
| **Nigredo** | The black stage — undifferentiated input material |
| **Albedo** | The white stage — purified, structured knowledge |
| **Citrinitas** | The yellow stage — solar dawn, pattern emergence |
| **Rubedo** | The red stage — completion, the Philosopher's Stone |
| **Athanasor** | The furnace — the housing, the compute infrastructure |

---

## What Azoth Is Not

- Not an autonomous scientist. It does not claim discovery.
- Not a paper generator. Drafts are proposals for your evaluation.
- Not a replacement for reading. You must triage every candidate.
- Not a black box. Every structured record is human-readable YAML.

---

## License

MIT. See `LICENSE`.

---

## Contributing

Azoth is designed to be extended. The four-phase pipeline is modular — you can swap the cross-connection method, add domain-specific pruning rules, or build new output formats for `rubedo/drafts/`. PRs welcome.

---

> *"We have to make the impersonal personal — taking structural truths and incarnating them in specific, lived, imperfect texts."* — aleatoric, 2021

Azoth is the impersonal phase. You are the incarnation.
