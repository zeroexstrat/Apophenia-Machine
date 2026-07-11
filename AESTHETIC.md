# AESTHETIC.md — Azoth / Apophenia Machine

**Purpose:** Canonical naming convention for every component in the Apophenia Machine. All names are drawn from Western and Islamic alchemy. No fungal, mycelial, or biological names. No physics or philosophy names. Pure alchemy.

**Constraint:** Names are stable. A name is chosen once and applied everywhere — directories, schemas, code, docs, agent instructions.

---

## 1. The Whole

| Name | Alchemy | Meaning |
|------|---------|---------|
| **Azoth** | The universal solvent; the Alpha-Omega unity | The entire project. The research synthesis engine that dissolves all boundaries without destroying what it touches. |
| **Apophenia** | Pattern-finding across domains that refuse to connect | The act — the method, automated. Finding structural connections between papers that share no obvious domain overlap. |

The project is **Azoth**. The act it performs is **Apophenia**. Together: the Apophenia Machine.

---

## 2. The Five Phases

| Name | Alchemy | Function |
|------|---------|----------|
| **Nigredo** | Blackening · putrefaction · dissolution | The undifferentiated mass. Raw PDFs in the inbox. The state before any structure exists. |
| **Albedo** | Whitening · purification · ablution | Structured extraction. Raw matter → YAML schema. Each paper becomes a queryable node. The first light. |
| **Citrinitas** | Yellowing · solar dawn · awakening | Cross-connection. Pattern emergence across the library. The moment when connections become visible. |
| **Rubedo** | Reddening · completion · the Stone | Gap detection, hypothesis generation, research drafts. The finished work. |
| **Athanasor** | The alchemical furnace; the vessel where transformation occurs | The housing. The infrastructure that makes all phases possible — skills, cron, scripts, memory, gates. |

---

## 3. The Memory Layer (in Athanasor)

| Name | Alchemy | Function |
|------|---------|----------|
| **Lapis** | The Philosopher's Stone; the perfected substance | Generated machine state and operational counters in `state.json`; never narrative authority. |
| **Codex** | The tablet; the inscribed record | Compatibility pointer in `codex.md`; current sessions inherit `PROJECT_ROADMAP.md`. |
| **Vigil** | The furnace that watches; the athanasor's guardian flame | Gate enforcement. Drift detection, honesty enforcement, failure tracking. The `gates.yaml` + `verify.py` system. |
| **Mortems** | From *mortificatio* — the death of the session; the record of what transpired | Historical diagnostic records in `mortems/`; useful evidence, but not the current handoff. |

---

## 4. The Five Gates (in Vigil)

| Name | Alchemy | What It Enforces |
|------|---------|-----------------|
| **Corpus** | The body — claims must be embodied in evidence | Processed library records validate and contain at least one nonblank claim/evidence trace. This is structural, not a truth judgment. |
| **Coniunctio** | The marriage — genuine union, not coincidence | Connection records validate, reference library records, contain specific evidence fields, and respect citations declared in those records. This is not an external novelty search. |
| **Calcinatio** | Burning — purification through fire | Exhaustion records validate, derived/likely items name a source trace, and no run exceeds five consecutive speculative derivations. This does not prove entailment. |
| **Caput Mortuum** | The dead head — exhausted matter, not to be reprocessed | Exhausted registry and artifact paper IDs and depths agree exactly; non-exhausted rows carry no cursor. This cannot reconstruct prior token use. |
| **Nigredo Redux** | Return to black — rejected candidates must not resurface | Pending Rubedo hypotheses cannot repeat a durable rejected cluster/evidence fingerprint. Changed evidence may return; connection decisions are out of scope. |

---

## 5. Exhaustion Depth Levels

| Depth | Name | Meaning |
|-------|------|---------|
| 1 | **Skim** | Surface. Derivations from major claims only. One exercise if applicable. |
| 2 | **Moderate** | All derivations. 2–3 exercises. Obvious missing angles. |
| 3 | **Thorough** (default) | Full schema. Derivations, exercises, missing angles, open questions, unstated assumptions, experiments where applicable. |
| 4 | **Deep** | Depth 3 plus speculative derivations, challenging exercises, necessary connections outside the paper's domain. |
| 5 | **Obsessive** | Every angle. Every corollary. Every exercise the material could support. Extended reasoning, multiple passes. |

---

## 6. Confidence Tiers

### For Claims (SCHEMA.yaml)
| Tier | Meaning |
|------|---------|
| **proven** | The paper provides a theorem, proof, or rigorous experimental result. |
| **formalizable** | The paper provides a framework that can be formalized but does not yet have a full proof. |
| **demonstrated** | The paper provides empirical evidence but not a formal proof. |
| **hypothesized** | The paper proposes the claim but does not test or prove it. |
| **speculative** | The paper suggests the claim as a possibility without evidence. |

### For Exhaustion Items (EXHAUST_SCHEMA.yaml)
| Tier | Meaning |
|------|---------|
| **derived** | Strict logical consequence of a paper's claim or method. Traceable to a specific source. |
| **likely** | Probable given the paper's framework with minor assumptions. |
| **speculative** | Interesting possibility with no rigorous grounding in the paper. Triggers the speculative ceiling at 5 consecutive items. |

---

## 7. The Separatio

| Name | Alchemy | Function |
|------|---------|----------|
| **Separatio** | Separation — the division of the unified mass into distinct components | Domain classification. A new paper enters `nigredo/inbox/` and is classified into a domain folder (`physics/`, `ML/`, `philosophy/`, etc.). The first act of structure. |

Separatio is not a formal phase. It is the threshold between Nigredo and Albedo — the moment undifferentiated matter becomes classifiable.

---

## 8. The Domain Subagents

Domain subagents are dormant workers, one per `nigredo/{domain}/` folder. They sleep until awakened by the user. Their names are the domain names — no additional alchemical mapping. The dormancy itself is alchemical: the **Cibatio** (feeding phase) where the embryo is nourished, followed by **Fermentatio** (bubbling transformation) during active work.

---

## 9. Naming Discipline

- **Directories:** alchemical names. `nigredo/`, `albedo/`, `citrinitas/`, `rubedo/`, `athanasor/`. Within Athanasor: `lapis/`, `vigil/`, `mortems/`.
- **Code symbols:** lowercase-hyphenated English. `domain_classifier.py`, `exhaust.py`, `verify.py`. Alchemical names appear in comments and docstrings only.
- **Schema identifiers:** lowercase_with_underscores. `paper_id`, `exhaustion_depth`, `source_claim`. No alchemical names in data fields.
- **Registry fields:** English, descriptive. `status`, `domain`, `triaged`. The registry is a machine interface, not a human aesthetic artifact.
- **CLI commands:** English verbs. `ingest`, `exhaust`, `connect`, `detect`, `draft`. Slash commands mirror CLI: `/ingest`, `/awaken`, `/connect`.
- **Display names:** alchemical. Docs, README, reports, triage output — the user-facing surfaces use the alchemical vocabulary.

---

## 10. What Is Not Named Alchemically

| Component | Naming | Reason |
|-----------|--------|--------|
| Python package name | `azoth` | The whole |
| CLI entry point | `azoth` | Matches package |
| YAML field names | descriptive English | Machine interface |
| Registry fields | descriptive English | Machine interface |
| Domain names | descriptive English (`physics`, `ML`) | User clarity |
| Skill filenames | descriptive English (`ingest.py`) | Code readability |

---

## 11. The Solve et Coagula

The alchemical injunction — dissolve and coagulate — is the project's motto. It names the fundamental cycle:

- **Solve (dissolve):** A paper is dissolved into its constituent claims, methods, techniques, and caveats. The unified mass is broken apart.
- **Coagula (coagulate):** The dissolved parts are recombined — across papers, across domains — into connections, gaps, and hypotheses. New structure emerges from the solution.

Every phase is either solve (Nigredo, Albedo) or coagula (Citrinitas, Rubedo). Athanasor is the vessel where both occur.
