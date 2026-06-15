# Azoth — The Apophenia Machine

> *"Solve et coagula. Dissolve and coagulate."* — Alchemical injunction

Azoth is an open-source research synthesis engine. It ingests a personal library of papers and texts, extracts their structural content into a machine-traversable schema, discovers cross-document connections, detects conceptual gaps, and generates falsifiable hypotheses — all gated by human judgment.

It is not an autonomous scientist. It does not publish papers for you. It is a candidate-generation furnace. You are the alchemist.

---

## Quick Start

```bash
git clone https://github.com/your-username/azoth.git
cd azoth
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

```bash
# 1) Start with a session check-in
python3 scripts/incipere.py

# 2) Drop papers and ingest
cp ~/Downloads/paper.pdf nigredo/
azoth ingest nigredo/paper.pdf

# 3) Exhaust papers in a domain (default depth 3, batch 3)
azoth awaken ML --depth 3 --count 3

# 4) Discover cross-domain/domain connections
azoth connect --within ML

# 5) Detect hypotheses from connected clusters
azoth detect --within ML

# 6) Draft notes from top hypotheses
azoth draft --top 1
```

Use `azoth status` anytime for registry health, and `azoth validate --all` before triage.
Use the CLI smoke check when you want fast interface regression coverage:

```bash
python3 scripts/check_cli.py
```

The pipeline is also mapped to conversational commands when driven by Hermes:
`/awaken`, `/connect`, `/detect`, and `/draft` map to the same underlying skills.

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
├── nigredo/             # Inbox + domain folders
│   ├── inbox/           # Unclassified PDFs
│   ├── physics/
│   ├── ML/
│   ├── philosophy/
│   ├── neuroscience/
│   ├── mathematics/
│   └── unclassified/
├── albedo/
│   ├── library/         # Structured per-paper summaries (YAML)
│   ├── exhaust/         # Per-paper exhaustion output
│   └── registry.jsonl   # Master index with processing status + gate state
├── citrinitas/
│   ├── within_domain/   # Connections within a single domain
│   └── cross_domain/    # Connections across domains
├── rubedo/
│   ├── hypotheses/      # Gap-detection output (≥3 paper clusters)
│   └── drafts/           # 2-page research notes
├── athanasor/
│   ├── skills/          # Hermes Agent skills
│   ├── cron/            # Processing schedules
│   ├── scripts/         # Utility scripts
│   ├── lapis/           # Durable project state
│   │   ├── state.json   # Pipeline progress, gate status, session count
│   │   └── codex.md     # Session handoff (the tablet)
│   ├── vigil/           # Gate enforcement
│   │   ├── gates.yaml   # Gate definitions
│   │   ├── verify.py    # Gate checker (start / verify / close)
│   │   └── reports/     # Per-run verification output
│   └── mortems/         # Session postmortems
├── SCHEMA.yaml          # Per-paper extraction schema
├── EXHAUST_SCHEMA.yaml  # Per-paper exhaustion schema
├── EXHAUSTION_GUARDRAILS.md  # Design discussion
├── USER_GUIDE.md        # Human-readable usage instructions
├── AGENTS.md            # AI agent operating instructions
├── HANDOFF.md           # For external agent review
├── LICENSE              # MIT
└── README.md            # This file
```

---

## Requirements

- `pdftotext` (from poppler) for PDF extraction
- `python3` 3.10+ for registry queries and schema validation
- An active LLM provider (OpenAI API format is the current client path)
- Optional: [Hermes Agent](https://github.com/NousResearch/hermes-agent) for scheduled, batch operation
- Optional: [arXiv skill](https://hermes-agent.nousresearch.com/docs/reference/skills-catalog) for gap-filling literature search

Manual operation does not require Hermes — this repo ships a CLI-first path.

Before starting a new cycle, run:

```bash
python3 scripts/incipere.py
```

To close a cycle and persist session state:

```bash
python3 scripts/concludere.py --findings-file findings.txt
```

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
