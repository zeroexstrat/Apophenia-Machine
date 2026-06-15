# BUILD_PROMPT AUDIT — Conflict Resolution

**Date:** 2026-06-14
**Auditors:** Hermes (Kimi K2.6), Codex (GPT-5.5), Mimo (spec author)
**Status:** Resolved. Spec updated. Implementation deferred until schema conflicts fixed.

---

## Resolved Conflicts

### 1. Registry Path (HIGH)

| Source | Convention |
|--------|-----------|
| BUILD_PROMPT.md | `albedo/registry/registry.jsonl` |
| AGENTS.md, verify.py, directory structure | `albedo/registry.jsonl` |

**Resolution:** `albedo/registry.jsonl`. The extra `registry/` subdirectory adds no value and the repo already uses the flat path. AGENTS.md line 24, verify.py line 33, and the directory listing in README.md all agree.

**Action:** BUILD_PROMPT.md §2.6 line 206 corrected to `albedo/registry.jsonl`.

---

### 2. Claim Confidence Schema (HIGH)

| Source | Convention |
|--------|-----------|
| BUILD_PROMPT.md §§3-4 | `0.0-1.0` float (ingest), `high/medium/low` (exhaust) |
| SCHEMA.yaml | `proven / formalizable / demonstrated / hypothesized / speculative` (enum) |

**Resolution:** Keep SCHEMA.yaml's enum. Rationale: `0.78` confidence does not tell you *why* — is it 0.78 because the claim is implied but not stated? Because the evidence is weak? Because the claim is from a preprint? The enum tiers encode the *kind* of confidence, not just its magnitude. This matters for the Vigil's Calcinatio gate, which gates on `derived` vs. `speculative`, not on `0.82` vs. `0.47`.

For exhaustion items, BUILD_PROMPT uses `high/medium/low`. EXHAUST_SCHEMA.yaml uses `derived/likely/speculative`. These map cleanly: `derived = high`, `likely = medium`, `speculative = low`. Keep the EXHAUST_SCHEMA.yaml terms — they are more specific about *how* the item relates to the source material.

**Action:** BUILD_PROMPT.md §§3-4 corrected to use SCHEMA.yaml enum for claims and EXHAUST_SCHEMA.yaml enum for exhaustion items.

---

### 3. Exhaustion Output Contract (HIGH)

| Source | Convention |
|--------|-----------|
| BUILD_PROMPT.md §4.4 | Flat list: `{type, content, source_claim, confidence}` |
| EXHAUST_SCHEMA.yaml | Top-level buckets: `derivations: [...]`, `exercises: [...]`, `missing_angles: [...]` |

**Resolution:** Keep EXHAUST_SCHEMA.yaml's bucket structure. Rationale: the buckets encode domain-sensitive exhaustion strategies. When a user queries "what derivations did this paper produce?", they should not have to filter a flat list by `type == "derivation"`. The bucket structure does this at the file level.

**Enhancement:** Add BUILD_PROMPT's `type` field as an optional sub-field within each bucket item, allowing items to carry an additional type tag beyond their bucket placement (e.g., a derivation that is also a counterargument). Add `source_claim` as a required sub-field across all bucket item types.

**Action:** BUILD_PROMPT.md §4.4 restructured to match EXHAUST_SCHEMA.yaml. EXHAUST_SCHEMA.yaml updated to include `item_type` and `source_claim` sub-fields.

---

### 4. Status Model (MEDIUM)

| Source | Convention |
|--------|-----------|
| BUILD_PROMPT.md §2.6 | Linear status: `ingested → exhausted → connected → detected → drafted → triaged` |
| AGENTS.md | Depth-graded cursor: `pending → ingested_only → exhausted_depth3 → exhausted_depth5` plus Boolean flags |

**Resolution:** Keep the depth-graded cursor model from AGENTS.md. Rationale: exhaustion is not a binary state. A paper exhausted to depth 3 can be re-awakened at depth 5. A linear `exhausted` status loses this information, breaking the Caput Mortuum gate ("a paper exhausted to depth N must not be reprocessed at depth ≤ N").

**Enhancement:** Add Boolean flags from BUILD_PROMPT's model: `connected: bool`, `detected: bool`, `drafted: bool`, `triaged: bool`. These are phase-completion markers that coexist with the depth-graded status. A paper can be `exhausted_depth3` AND `connected: true` AND `detected: true`. The status field is the *exhaustion* state. The Booleans are the *pipeline* state.

**Action:** BUILD_PROMPT.md §2.6 registry schema updated. AGENTS.md status field clarified.

---

### 5. Exhaust Artifact Naming (MEDIUM)

| Source | Convention |
|--------|-----------|
| BUILD_PROMPT.md §4.5 | `albedo/exhaust/<paper_id>.yaml` |
| AGENTS.md, EXHAUST_SCHEMA.yaml | `albedo/exhaust/<id>_exhaust.yaml` |

**Resolution:** `albedo/exhaust/<id>_exhaust.yaml`. The `_exhaust` suffix visually distinguishes exhaustion output from the library extraction record (`<id>.yaml` in `albedo/library/`) when both are viewed in a flat file listing. This is a readability concern, not a structural one.

**Action:** BUILD_PROMPT.md §4.5 corrected.

---

### 6. CLI / Agent Command Split (MEDIUM)

| Source | Convention |
|--------|-----------|
| BUILD_PROMPT.md §3-8 | Slash commands for agents (`/ingest`, `/awaken`, `/connect`) |
| BUILD_PROMPT.md §9 | Click CLI for standalone (`azoth ingest`, `azoth exhaust`) |

**Resolution:** Both are correct and both should exist. They are different interfaces to the same skills. The Click CLI is the Python package interface for standalone operation. The slash commands are the agent interface when Azoth is operated through Hermes. They map to the same `athanasor/skills/*.py` implementations.

**Clarification:**
- `azoth ingest <path>` (CLI) ↔ `/ingest <path>` (Hermes agent)
- `azoth exhaust --domain ML --depth 3` (CLI) ↔ `/awaken ML --depth 3` (Hermes agent)
- The CLI is the automation surface. The slash commands are the conversational surface. Both invoke the same skills.

**Action:** BUILD_PROMPT.md §8 updated to clarify the mapping. No change to either interface.

---

### 7. Vigil Not Represented in Build Prompt (MEDIUM)

| Source | Coverage |
|--------|----------|
| BUILD_PROMPT.md | No mention of Vigil, lapis, gates, or the Vigil protocol |
| AGENTS.md, verify.py, gates.yaml | Full Vigil protocol: start/verify/close, five gates, state tracking |

**Resolution:** Every skill must integrate Vigil calls. Before any code is written, BUILD_PROMPT.md must be updated to include Vigil requirements per phase. The Vigil is not decorative — it is the enforcement layer for the five gates that govern the pipeline.

**Vigil Integration Per Skill:**

| Skill | Pre-Work | Post-Work | State Update |
|-------|----------|-----------|--------------|
| `ingest.py` | — | `vigil verify` (check registry: no duplicates, claims backed) | `state.json`: albedo.total_ingested += 1 |
| `exhaust.py` | Check `registry.jsonl` for Caput Mortuum (already exhausted at this depth?) | `vigil verify` (check Calcinatio: derivations honest about confidence) | `state.json`: albedo.total_exhausted += 1 |
| `connect.py` | — | `vigil verify` (check Coniunctio: novelty passes citation check) | `state.json`: citrinitas.total_connections += N |
| `detect.py` | — | `vigil verify` (check Corpus: gaps backed by specific papers) | `state.json`: rubedo.total_hypotheses += N |
| `draft.py` | — | `vigil verify` (check Corpus: draft references specific claims) | `state.json`: rubedo.total_drafts += N |

**Action:** BUILD_PROMPT.md updated with Vigil section per skill. AGENTS.md Vigil protocol unchanged.

---

## Implementation Order (Updated)

| Priority | What | Blocked By |
|----------|------|-----------|
| 1 | Fix BUILD_PROMPT.md to resolve all 7 conflicts | — |
| 2 | Update EXHAUST_SCHEMA.yaml to add `item_type` and `source_claim` sub-fields | #1 |
| 3 | Update SCHEMA.yaml to clarify confidence field: enum, not float | #1 |
| 4 | Build `pyproject.toml`, `config.py`, `llm.py`, `pdf_parser.py`, `registry.py`, `schemas.py` | #2, #3 |
| 5 | Build `domain_classifier.py`, `skills/ingest.py` (with Vigil) | #4 |
| 6 | Build `skills/exhaust.py` (with Vigil + Caput Mortuum check) | #4, #5 |
| 7 | Build `skills/connect.py`, `detect.py`, `draft.py` (with Vigil) | #4, #6 |
| 8 | Build `cli.py` | #7 |
| 9 | Append agent command mapping to AGENTS.md | #8 |
| 10 | Embedding store (v0.2) | All above |
