# BUILD PROMPT: Azoth — The Apophenia Machine

You are building Azoth, an open-source research synthesis engine. The project
architecture, schemas, and directory structure already exist on disk. Your job
is to build every working component — skills, infrastructure, agent instructions,
CLI — so that the system is fully operational end-to-end.

Read every file in the project before writing any code. Understand the design
decisions. Then build.

---

## 0. PROJECT LOCATION AND EXISTING FILES

Project root: `~/Desktop/apophenia-machine/`

Existing files you MUST read before building:
- `README.md` — product description and naming conventions
- `USER_GUIDE.md` — human-facing workflow instructions
- `AGENTS.md` — current agent operating instructions (you will rewrite this)
- `SCHEMA.yaml` — per-paper extraction schema
- `EXHAUST_SCHEMA.yaml` — per-paper exhaustion schema
- `EXHAUSTION_GUARDRAILS.md` — design rationale for self-termination
- `LICENSE` — MIT

Directory structure already exists:
```
apophenia-machine/
├── nigredo/inbox/, physics/, ML/, philosophy/, neuroscience/, mathematics/, unclassified/
├── albedo/library/, exhaust/, registry/
├── citrinitas/within_domain/, cross_domain/
├── rubedo/hypotheses/, drafts/
└── athanasor/skills/, cron/, scripts/
```

---

## 1. DESIGN PHILOSOPHY (NON-NEGOTIABLE)

These principles override any implementation decision you face:

1. **Every phase produces candidates. No phase produces final knowledge.**
   No output is marked `confirmed` without explicit human triage. The word
   "discovered" does not appear in any agent-facing instruction. The system
   surfaces. The human decides.

2. **Dormancy, not autonomy.** Domain subagents sleep until awakened by
   the user. No subagent runs on its own schedule without explicit
   configuration. The user controls which domains are active.

3. **Alchemical naming only.** The five phases are Nigredo, Albedo,
   Citrinitas, Rubedo, Athanasor. No fungal, mycelial, or other naming
   schemes. This is a standalone product with its own identity.

4. **Local-first, model-agnostic.** All processing happens locally by
   default. LLM calls use an abstraction layer that supports any
   OpenAI-compatible API endpoint (including local Ollama, LM Studio,
   vLLM, or remote APIs). No hard dependency on any specific provider.

5. **Transparent failure.** Every component reports what it did, what it
   failed to do, and why. No silent failures. No hallucinated completions.

---

## 2. INFRASTRUCTURE LAYER (BUILD FIRST)

### 2.1 Dependency and Project Setup

Create `pyproject.toml` with these dependencies:
- `pymupdf` (PDF text extraction)
- `pyyaml` (schema handling)
- `sentence-transformers` (embeddings — default model: `all-MiniLM-L6-v2`)
- `numpy` (vector operations)
- `click` (CLI)
- `rich` (terminal output formatting)
- `openai` (LLM API client — works with any OpenAI-compatible endpoint)
- `jsonlines` (registry I/O)

Create a package structure:
```
athanasor/
├── __init__.py
├── config.py          # Global config (model endpoints, paths, thresholds)
├── llm.py             # LLM abstraction layer
├── embeddings.py      # Embedding generation and vector store
├── registry.py        # Registry read/write operations
├── schemas.py         # Schema validation
├── pdf_parser.py      # PDF text extraction
├── domain_classifier.py
├── skills/
│   ├── __init__.py
│   ├── ingest.py      # Nigredo → Albedo
│   ├── exhaust.py     # Albedo exhaustion
│   ├── connect.py     # Citrinitas
│   ├── detect.py      # Rubedo gap detection
│   └── draft.py       # Rubedo note generation
├── cli.py             # Click CLI entry point
└── scripts/
    ├── validate.py    # Schema validation script
    └── migrate.py     # Schema migration utility
```

### 2.2 Configuration (`config.py`)

```yaml
# azoth.config.yaml (project root)
llm:
  base_url: "http://localhost:11434/v1"   # Default: local Ollama
  model: "llama3.1:70b"                    # Default model
  api_key: "ollama"                        # Placeholder for local
  temperature: 0.3                         # Low for extraction, higher for generation
  max_tokens: 4096

embeddings:
  model: "all-MiniLM-L6-v2"               # sentence-transformers model name
  store_path: "athanasor/embeddings.store" # numpy flat index
  similarity_threshold: 0.82               # Connection candidate threshold
  redundancy_threshold: 0.85               # Exhaustion redundancy threshold

paths:
  project_root: "~/Desktop/apophenia-machine"
  nigredo: "nigredo"
  albedo: "albedo"
  citrinitas: "citrinitas"
  rubedo: "rubedo"
  athanasor: "athanasor"

domains:
  - physics
  - ML
  - philosophy
  - neuroscience
  - mathematics
  - unclassified

exhaustion:
  depth_multipliers: {1: 2, 2: 4, 3: 6, 4: 8, 5: 12}
  batch_size: 5
  redundancy_stop_threshold: 3     # In a batch of 5, if ≥3 are redundant → stop
  speculative_stop_count: 5        # 5 consecutive speculative items → stop
```

Load config from `azoth.config.yaml` at project root. Allow environment
variable overrides for `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`.

### 2.3 LLM Abstraction (`llm.py`)

Build a single `LLMClient` class that:
- Accepts a prompt string and optional system message
- Returns the response text
- Supports structured output mode (JSON mode when the endpoint supports it)
- Has configurable temperature per call (override instance default)
- Logs every call: timestamp, prompt length, response length, model, tokens used
- Handles rate limiting with exponential backoff (3 retries)
- Handles context window overflow by truncating from the middle of the prompt
  and logging a warning

The structured output mode should:
- Append "Respond ONLY with valid JSON matching this schema: ..." to the prompt
- Parse the response as JSON, retry once if parsing fails
- Return a Python dict, not a raw string

### 2.4 Embedding Infrastructure (`embeddings.py`)

Build an `EmbeddingStore` class that:
- Uses sentence-transformers to generate embeddings
- Stores embeddings as a numpy array (flat cosine similarity)
- Supports: `add(id, text)`, `search(query_text, top_k)`, `remove(id)`,
  `save()`, `load()`
- Batch operations: `add_batch(ids, texts)`, `search_batch(query_texts, top_k)`
- Persists to disk as `.npy` (vectors) + `.json` (id-to-index mapping)
- Default embedding model: `all-MiniLM-L6-v2` (384 dimensions, fast, good enough)

The embedding store is used by:
- Ingest (to embed claims, methods, techniques for later search)
- Exhaust (to check redundancy against previously generated items)
- Connect (to find candidate paper pairs for connection analysis)

### 2.5 PDF Parser (`pdf_parser.py`)

Build a `parse_pdf(path)` function that:
- Uses PyMuPDF to extract text page by page
- Attempts to detect multi-column layouts by analyzing text block x-coordinates
  (if blocks appear in two distinct x-ranges, interleave them)
- Extracts: full text, page count, section headers (detect by font size or
  numbering patterns), references section (split at "References" or
  "Bibliography" heading)
- Returns a structured dict:
  ```python
  {
      "path": str,
      "filename": str,
      "page_count": int,
      "full_text": str,
      "sections": [{"title": str, "text": str, "start_page": int}],
      "references": [str],  # Raw reference strings
      "abstract": str | None,  # If detectable
      "parse_warnings": [str]  # Any issues encountered
  }
  ```
- Handles: encrypted PDFs (skip with warning), image-only PDFs (warn, do
  not OCR — that's out of scope), empty pages

### 2.6 Registry (`registry.py`)

The registry is `albedo/registry/registry.jsonl` — one JSON object per line.

Build `Registry` class with:
- `add(entry)`: Append a new entry
- `update(paper_id, fields)`: Update specific fields of an entry
- `get(paper_id)`: Retrieve entry by ID
- `list_by_status(status)`: Filter entries by processing status
- `list_by_domain(domain)`: Filter entries by domain
- `exists(paper_id)`: Check if entry exists
- `stats()`: Return counts by status, domain, etc.

Registry entry schema:
```json
{
  "paper_id": "string (filename stem, slugified)",
  "filename": "string (original PDF filename)",
  "domain": "string (physics|ML|philosophy|neuroscience|mathematics|unclassified)",
  "domain_confidence": "float (0-1)",
  "title": "string",
  "authors": ["string"],
  "year": "int|null",
  "ingested": "ISO timestamp",
  "exhausted_at_depth": "int|null (highest depth completed)",
  "connected": "bool",
  "triaged": "bool",
  "status": "string (ingested|exhausted|connected|detected|drafted|triaged)",
  "paths": {
    "library": "albedo/library/<paper_id>.yaml",
    "exhaust": "albedo/exhaust/<paper_id>.yaml",
    "pdf": "nigredo/<domain>/<filename>.pdf"
  },
  "tags": ["string"],
  "processing_notes": ["string (log of what was done)"]
}
```

### 2.7 Schema Validation (`schemas.py` + `scripts/validate.py`)

Build a validator that checks YAML files against SCHEMA.yaml and
EXHAUST_SCHEMA.yaml definitions. The validator should:

- Load the schema definition and the candidate YAML file
- Check all required fields are present
- Check field types (string, int, float, list, enum)
- Check value ranges (e.g., confidence: 0-1, depth: 1-5)
- Check list item structure (e.g., each claim has required sub-fields)
- Report errors with JSON-pointer-style paths (e.g., `/claims/2/confidence`)
- Support `--fix` mode for simple repairs (add missing optional fields with
  defaults, coerce obvious type mismatches)

Make `scripts/validate.py` a standalone CLI:
```
python scripts/validate.py albedo/library/some_paper.yaml
python scripts/validate.py --all  # Validate all files in albedo/
python scripts/validate.py --all --fix  # Validate and repair
```

Also create `scripts/migrate.py` for future schema version upgrades:
- Accept a target schema version
- Walk all YAML files, detect version, apply transformations
- Log all changes

Embed a `schema_version` field at the top of every generated YAML file.
Current version: `1`.

---

## 3. SKILL 1: INGEST (Nigredo → Albedo)

**File:** `athanasor/skills/ingest.py`

### Behavior

1. **Input:** Path to a PDF file (or directory of PDFs).

2. **Parse:** Extract text using `pdf_parser.py`.

3. **Classify Domain:**
   - Send the abstract (or first 2000 characters if no abstract detected) to
     the LLM with this prompt:
     ```
     Classify this paper into exactly one domain: physics, ML, philosophy,
     neuroscience, mathematics, or unclassified.

     Title: {title}
     Abstract: {abstract}

     Respond with JSON: {"domain": "<domain>", "confidence": <0.0-1.0>,
     "reasoning": "<one sentence>"}
     ```
   - If confidence < 0.6, place in `nigredo/unclassified/` and flag for
     human review.
   - Move/copy the PDF to `nigredo/<domain>/`.

4. **Extract Structured Record:**
   - Send the full text (truncated to fit context window if needed) to the
     LLM with the extraction prompt. The prompt should instruct the LLM to
     populate every field defined in `SCHEMA.yaml`:
     ```
     Extract a structured record from this research paper.

     [Full text here]

     Return JSON matching this schema:
     {SCHEMA.yaml contents as JSON schema}

     Rules:
     - Every claim must be a specific, falsifiable statement from the paper.
       Not a summary. Not a paraphrase. A claim the paper makes or implies.
     - Methods are what the paper DOES, not what it REFERENCES.
     - Caveats are limitations the authors acknowledge OR limitations you
       identify from the methodology.
     - Tags are 1-3 word descriptors for searchability.
     - If a field cannot be determined, use null. Do not fabricate.
     - Assign a confidence score (0.0-1.0) to each claim reflecting how
       directly the paper states it vs. how much you are inferring.
     ```
   - Parse the response into a Python dict.
   - Validate against `SCHEMA.yaml` using the schema validator.
   - If validation fails, retry extraction once with the validation errors
     included in the prompt. If it fails again, save the raw response in a
     `parse_errors` field and flag for human review.

5. **Write Output:**
   - Save structured YAML to `albedo/library/<paper_id>.yaml`
   - Embed all claims, methods, and techniques in the embedding store:
     - For each claim: embed the claim text, store with ID `<paper_id>_claim_<n>`
     - For each method: embed the method text, store with ID `<paper_id>_method_<n>`
     - For each technique: embed the technique text, store with ID `<paper_id>_technique_<n>`
   - Save the embedding store.
   - Add entry to registry with status `ingested`.

6. **Report:**
   ```
   Ingested: <filename>
   Domain: <domain> (confidence: <X>)
   Claims extracted: <N>
   Methods extracted: <N>
   Tags: <list>
   Warnings: <any parse issues>
   ```

### CLI

```
python -m athanasor.cli ingest path/to/paper.pdf
python -m athanasor.cli ingest path/to/directory/  # Batch ingest
python -m athanasor.cli ingest --reingest <paper_id>  # Overwrite existing
```

---

## 4. SKILL 2: EXHAUST (Albedo Deep Work)

**File:** `athanasor/skills/exhaust.py`

### Behavior

1. **Input:** Paper ID + depth level (1-5).

2. **Load:** Read the paper's structured YAML from `albedo/library/` and the
   raw PDF text from its `nigredo` path.

3. **Determine Exhaustion Scope:**
   - Use the depth multiplier from config: `max_items = page_count × depth_multiplier[depth]`
   - Domain-specific exhaustion strategy (see below)

4. **Domain-Sensitive Exhaustion Strategies:**

   **Physics / Mathematics:**
   - Derive corollaries from stated theorems or results
   - Solve embedded exercises (if textbook-style)
   - Extend techniques to adjacent problem domains
   - Identify unstated assumptions in derivations
   - Compare with alternative approaches to the same problem
   - Identify boundary conditions or special cases not discussed

   **ML / AI:**
   - Derive implications for other tasks or domains
   - Propose follow-up experiments with expected outcomes and what each
     outcome would imply
   - Identify ablation studies that should exist but don't
   - Compare with competing methods not discussed by the authors
   - Identify potential failure modes not addressed
   - Assess reproducibility: what information is missing to replicate?

   **Philosophy:**
   - Identify unstated assumptions the argument depends on
   - Close open questions the author's own framework could have addressed
   - Identify missing perspectives or angles (philosophical traditions,
     counterarguments, adjacent fields)
   - Extend arguments to edge cases
   - Identify where the argument relies on ambiguous terms
   - Compare with competing frameworks that address the same questions

   **Neuroscience:**
   - Identify experimental predictions not tested
   - Cross-reference with computational models from ML/physics
   - Identify methodological limitations (sample size, controls, measures)
   - Propose control experiments
   - Map findings to psychological or behavioral phenomena
   - Identify translational implications

   **Unclassified:**
   - Use a generic strategy: identify claims, gaps, implications, and
     connections to any domain

   Send the paper content to the LLM with a domain-specific system prompt
   instructing it to produce exhaustion items matching EXHAUST_SCHEMA.yaml.
   Each item must include:
   - `type`: derivation | exercise | missing_angle | open_question |
     experiment | implication | counterargument | extension
   - `content`: the item itself (specific, substantive — not vague)
   - `source_claim`: which original claim this derives from (reference by
     claim index or text)
   - `confidence`: high | medium | low — how grounded is this item in the
     source material?
   - `domain_specific_type`: the domain-specific category (e.g., "ablation
     study" for ML, "control experiment" for neuroscience)

5. **Generate in Batches with Self-Termination:**

   Generate items in batches of 5 (configurable via `exhaustion.batch_size`).

   After each batch, apply ALL THREE termination criteria:

   **Criterion 1 — Redundancy Check:**
   - For each new item, compute embedding of its `content` field
   - Search the embedding store for all items with the same `paper_id` prefix
   - If cosine similarity > `redundancy_threshold` (0.85) with any previously
     generated item, mark the new item as `redundant: true`
   - After processing the batch: if ≥ `redundancy_stop_threshold` (3) of the
     5 new items are redundant, STOP. Report: "Terminated: redundancy
     threshold reached. {N} of 5 items redundant with existing output."

   **Criterion 2 — Speculative Ceiling:**
   - Track consecutive `low`-confidence items
   - If the last `speculative_stop_count` (5) consecutive items all have
     confidence `low`, STOP. Report: "Terminated: speculative ceiling.
     Last 5 items all low-confidence."

   **Criterion 3 — Hard Cap:**
   - If total non-redundant items ≥ `max_items`, STOP. Report: "Terminated:
     hard cap reached. {max_items} items generated."

   When any criterion triggers, additionally report:
   - Total items generated (excluding redundant)
   - Distribution by type and confidence
   - Whether items appeared to still be high-quality at termination (i.e.,
     did redundancy/speculation trigger, or did the hard cap catch
     well-grounded items?)
   - Whether deeper exhaustion (higher depth level) is recommended

6. **Write Output:**
   - Save exhaustion YAML to `albedo/exhaust/<paper_id>.yaml`
   - Embed all exhaustion items in the embedding store:
     ID: `<paper_id>_exhaust_<n>`
   - Update registry: `exhausted_at_depth` = max(current, this depth)
   - Update status to `exhausted` if not already higher

7. **Report:**
   ```
   Exhausted: <paper_id> at depth <N>
   Items generated: <N>
   By type: {derivation: N, experiment: N, ...}
   By confidence: {high: N, medium: N, low: N}
   Termination: <criterion> | completed naturally
   Redundant items filtered: <N>
   Deeper exhaustion available: yes/no
   ```

### CLI

```
python -m athanasor.cli exhaust <paper_id> --depth 3
python -m athanasor.cli exhaust --domain ML --depth 2  # Exhaust all ML papers
python -m athanasor.cli exhaust --all --depth 1         # Skim everything
```

---

## 5. SKILL 3: CONNECT (Citrinitas)

**File:** `athanasor/skills/connect.py`

### Behavior

1. **Input:** Scope — either:
   - A specific paper ID (find connections for this paper)
   - A domain pair (e.g., `--within physics` or `--cross ML philosophy`)
   - `--all` (full connection pass)

2. **Candidate Generation (Embedding-Based):**
   - For within-domain: compare all paper pairs in the domain using their
     embedded claims, methods, and techniques. Compute aggregate similarity
     (mean of top-3 claim-claim similarities, top-2 method-method similarities).
   - For cross-domain: same comparison across domain boundaries.
   - Filter candidates: only pairs with aggregate similarity >
     `similarity_threshold` (0.82) AND that haven't been previously analyzed.
   - Store previously analyzed pairs in `albedo/registry/connections_analyzed.jsonl`
     to avoid re-analysis.

3. **Connection Analysis (LLM-Mediated):**
   - For each candidate pair, send both paper records (structured YAML) to the
     LLM with this prompt:
     ```
     Analyze the potential connections between these two research papers.

     Paper A: {A.title} ({A.domain})
     Claims: {A.claims}
     Methods: {A.methods}
     Techniques: {A.techniques}

     Paper B: {B.title} ({B.domain})
     Claims: {B.claims}
     Methods: {B.methods}
     Techniques: {B.techniques}

     Identify ALL substantive connections. For each connection, respond with:
     {
       "connection_type": "methodological_overlap|contradictory_claims|
         complementary_techniques|shared_assumptions|missing_citation|
         generalization|analogous_structure|extension",
       "description": "Precise description of the connection",
       "evidence_a": "Specific claim/method/technique from Paper A",
       "evidence_b": "Specific claim/method/technique from Paper B",
       "confidence": "high|medium|low",
       "novelty": "obvious|non-obvious|speculative",
       "significance": "Why this connection matters (2-3 sentences)"
     }

     If NO substantive connection exists, respond:
     {"connections": [], "reasoning": "Why no meaningful connection exists"}

     Rules:
     - Do NOT report connections based on surface-level keyword overlap.
       The connection must be conceptual or methodological.
     - A shared general method (e.g., both use "gradient descent") is NOT
       a connection unless the specific application creates insight.
     - Prefer fewer, higher-quality connections over many shallow ones.
     ```

4. **Validate and Score:**
   - Parse LLM response
   - Filter out any connection with novelty `speculative` unless it also has
     confidence `high` (speculative + low/medium = discard)
   - Score remaining connections: high confidence = 3, medium = 2, low = 1.
     Multiply by novelty weight: non-obvious = 2, obvious = 1.
   - Rank connections by score.

5. **Write Output:**
   - For within-domain connections: save to
     `citrinitas/within_domain/<domain>/<A_id>__<B_id>.yaml`
   - For cross-domain connections: save to
     `citrinitas/cross_domain/<A_domain>_<B_domain>/<A_id>__<B_id>.yaml`
   - Each connection file includes: both paper IDs, connection type,
     description, evidence, confidence, novelty, significance, score
   - Update registry: mark both papers as `connected: true`
   - Add pair to `connections_analyzed.jsonl`

6. **Report:**
   ```
   Connection pass: <scope>
   Candidate pairs analyzed: <N>
   Connections found: <N>
   By type: {methodological_overlap: N, ...}
   Top connections (by score):
     1. [score] <A.title> ↔ <B.title>: <description>
     2. ...
   Pairs with no connection: <N>
   ```

### CLI

```
python -m athanasor.cli connect --within physics
python -m athanasor.cli connect --cross ML philosophy
python -m athanasor.cli connect --paper <paper_id>
python -m athanasor.cli connect --all
```

---

## 6. SKILL 4: DETECT (Rubedo Gap Detection)

**File:** `athanasor/skills/detect.py`

### Behavior

1. **Input:** Either:
   - A specific domain (find gaps within this domain)
   - A specific cross-domain pair
   - `--all` (scan all connection clusters)

2. **Cluster Identification:**
   - Build a graph from connection files: papers are nodes, connections are
     edges (weighted by score).
   - Find clusters: connected components with ≥3 nodes.
   - For each cluster, collect: all paper records, all exhaustion records,
     all connection records.

3. **Gap Detection (LLM-Mediated):**
   - For each cluster, send the aggregated material to the LLM:
     ```
     You are analyzing a cluster of related research papers to identify
     GAPS — questions no paper in the cluster addresses, methods no one
     has applied, contradictions no one has resolved, or opportunities
     that exist at the intersections.

     Papers in cluster:
     {For each paper: title, domain, key claims, key methods, key caveats}

     Connections identified:
     {For each connection: type, description, significance}

     Exhaustion notes:
     {Key open questions and missing angles from exhaustion records}

     Identify gaps in these categories:
     1. UNEXPLORED_QUESTION: A question raised by the cluster that no
        paper addresses
     2. UNAPPLIED_METHOD: A method from one paper that could solve a
        problem in another but hasn't been tried
     3. UNRESOLVED_CONTRADICTION: Claims in the cluster that are in
        tension and no paper reconciles
     4. MISSING_EXPERIMENT: An experiment that would test a connection
        or resolve a gap
     5. THEORETICAL_OPPORTUNITY: A generalization, unification, or
        extension that the cluster's results suggest but no one has
        formalized

     For each gap, respond with:
     {
       "gap_type": "<category above>",
       "description": "Precise description (3-5 sentences)",
       "supporting_papers": ["paper_ids"],
       "supporting_evidence": "What in these papers makes you identify this gap",
       "significance": "Why filling this gap matters",
       "feasibility": "high|medium|low — how tractable is this?",
       "suggested_approach": "Brief sketch of how to address it",
       "confidence": "high|medium|low"
     }

     Rules:
     - A gap must be SURFACED BY the evidence in the cluster. Not a
       generic "more research is needed" statement.
     - Prefer specific, actionable gaps over vague ones.
     - If the cluster is too thin for meaningful gap detection, say so.
     ```

4. **Filter and Rank:**
   - Remove gaps with confidence `low` (surface but don't prioritize)
   - Rank remaining by: significance (qualitative) × feasibility weight
     (high=3, medium=2, low=1)
   - Group gaps by the papers they reference

5. **Write Output:**
   - Save gap report to `rubedo/hypotheses/<cluster_id>.yaml` where
     cluster_id is derived from the paper IDs in the cluster (e.g.,
     `cluster_<first_paper_id>_<N>.yaml`)
   - Each report includes: cluster composition, gaps found, ranking, metadata
   - Update registry status for papers in the cluster to `detected`

6. **Report:**
   ```
   Gap detection: <scope>
   Clusters analyzed: <N>
   Gaps identified: <N>
   By type: {unexplored_question: N, ...}
   Top gaps:
     1. [type, feasibility] <description>
     2. ...
   Clusters too thin for detection: <N>
   ```

### CLI

```
python -m athanasor.cli detect --domain physics
python -m athanasor.cli detect --cross ML philosophy
python -m athanasor.cli detect --all
```

---

## 7. SKILL 5: DRAFT (Rubedo Research Notes)

**File:** `athanasor/skills/draft.py`

### Behavior

1. **Input:** A gap cluster file from `rubedo/hypotheses/` (or a gap ID).

2. **Load:** The gap report, all referenced paper records, and their
   exhaustion and connection records.

3. **Draft Generation (LLM-Mediated):**
   ```
   You are drafting a 2-page research note based on a gap identified
   in a cluster of related papers. This is a CANDIDATE note — it
   proposes a direction, it does not assert findings.

   Gap: {gap.description}
   Type: {gap.gap_type}
   Suggested approach: {gap.suggested_approach}

   Supporting papers:
   {For each: title, key claims, key methods, relevant exhaustion items}

   Draft a research note with these sections:

   ## Title
   A working title for the research direction.

   ## Context (1 paragraph)
   What the cluster of papers establishes and where the gap sits.

   ## The Gap (1-2 paragraphs)
   Precise description of what's missing, with specific references to
   the supporting papers.

   ## Proposed Direction (2-3 paragraphs)
   What investigation could fill this gap. Include:
   - Specific questions to answer
   - Methods that could be applied
   - Expected outcomes and what each would imply
   - Feasibility assessment

   ## Open Questions (bullet list)
   What remains uncertain even if this direction is pursued.

   ## References
   Cite the supporting papers by their IDs.

   Rules:
   - This is a CANDIDATE. Use hedging language: "suggests", "may",
     "one approach would be". Never state findings as established.
   - Be specific. "Apply method X from paper A to problem Y in paper B"
     is good. "More research is needed" is not.
   - Target length: ~1000 words (2 pages single-spaced).
   ```

4. **Write Output:**
   - Save as Markdown to `rubedo/drafts/<descriptive_slug>.md`
   - Include YAML frontmatter with: gap_id, papers referenced, date,
     status: "candidate — requires human review"
   - Update registry for referenced papers: `status: drafted`

5. **Report:**
   ```
   Drafted: <title>
   Based on gap: <gap_id>
   Papers referenced: <N>
   Location: rubedo/drafts/<filename>.md
   Status: candidate — requires human review
   ```

### CLI

```
python -m athanasor.cli draft <gap_id>
python -m athanasor.cli draft --top 3  # Draft notes for top 3 ranked gaps
```

---

## 8. AGENT OPERATING INSTRUCTIONS (Rewrite AGENTS.md)

**File:** `AGENTS.md` (rewrite completely)

Write a complete agent operating manual that any LLM agent can follow to
operate within the Azoth system. Structure:

### 8.1 Identity and Role

You are an agent operating within the Azoth research synthesis engine. You
are a tool for surfacing candidates, not for producing knowledge. Every
output you produce is a suggestion for human review.

You do NOT:
- Claim to have "discovered" anything
- Mark any output as "confirmed" or "validated"
- Make decisions about what is true
- Prioritize your own assessments over human judgment
- Run any phase without being asked

### 8.2 Command Recognition

Recognize and respond to these commands:
- `/ingest <path>` — Run ingestion on a PDF or directory
- `/awaken <domain> --depth <N> --count <M>` — Activate a domain subagent
  and exhaust M papers at depth N
- `/connect <scope>` — Run connection discovery
- `/detect <scope>` — Run gap detection
- `/draft <gap_id>` — Generate a research note
- `/status` — Show current registry state
- `/validate` — Run schema validation on all outputs
- `/triage <paper_id>` — Present candidates for human review

### 8.3 Phase-Specific Behavior

For each phase, document:
- What inputs the agent needs
- What the agent does step by step
- What the agent NEVER does (specific prohibitions)
- How the agent reports results
- How the agent handles errors
- How the agent handles human feedback (accept, reject, modify)

### 8.4 Gate Protocol

When presenting candidates to the human:
1. Show a summary table: item type, content (truncated), confidence, source
2. Group by confidence: high first, then medium, then low
3. For each item, the human can: accept, reject, modify, flag for later
4. Accepted items get marked `triaged: true` in the registry
5. Rejected items are logged but not deleted (they may inform future passes)
6. Modified items replace the original with the human's version

### 8.5 Termination Reporting

When a self-termination criterion fires, the agent must report:
- Which criterion triggered (redundancy, speculative ceiling, hard cap)
- The specific evidence (e.g., "Items 47-51 all scored low confidence")
- Whether deeper exhaustion appears warranted
- The human can override: `/exhaust <paper_id> --depth <N> --override`

### 8.6 Error Recovery

- If an LLM call fails: retry once, then report the failure and continue
  with partial results
- If a PDF fails to parse: log the error, skip the paper, add to a
  `needs_manual_ingest` list
- If schema validation fails after retry: save raw output, flag for human
  review, continue
- If the embedding store is corrupted: rebuild from all library YAML files

### 8.7 Communication Style

- Terse in logs, clear in human-facing output
- Use structured output (tables, bullet lists) over prose
- Always report what was done, what wasn't, and why
- Never use hedging language in logs (log facts, not opinions)
- In human-facing output, distinguish clearly between what the paper says
  and what the agent infers

---

## 9. CLI ORCHESTRATOR

**File:** `athanasor/cli.py`

Build a Click-based CLI with these commands:

```
azoth ingest <path> [--reingest] [--domain-override <domain>]
azoth exhaust <paper_id> --depth <1-5>
azoth exhaust --domain <domain> --depth <1-5> [--count <N>]
azoth exhaust --all --depth <1-5>
azoth connect --within <domain> | --cross <d1> <d2> | --paper <id> | --all
azoth detect --domain <domain> | --cross <d1> <d2> | --all
azoth draft <gap_id> [--top <N>]
azoth status [--domain <domain>] [--status <status>]
azoth validate [--all] [--fix]
azoth config --show
azoth config --set <key> <value>
```

The CLI should use `rich` for formatted output:
- Progress bars for batch operations
- Tables for status reports
- Syntax-highlighted YAML for record display
- Color-coded confidence levels (green=high, yellow=medium, red=low)

Each command should:
- Load config
- Initialize required infrastructure (LLM client, embedding store)
- Execute the skill
- Display formatted results
- Exit cleanly with appropriate exit codes (0=success, 1=partial failure,
  2=total failure)

---

## 10. TESTING AND VALIDATION

After building everything, run this validation sequence:

### 10.1 Schema Validation
- Create 3 test YAML records (one per major domain) by hand that
  intentionally include errors
- Run `azoth validate` and confirm it catches all errors
- Run `azoth validate --fix` and confirm it repairs what it can

### 10.2 Ingest Pipeline
- Ingest 3 real papers from the rx2/rx3 corpus at
  `~/Desktop/ai-projects/memory-sanity/`
- Validate the output YAML against the schema
- Check that domain classification is reasonable
- Check that claims, methods, and techniques are substantive (not generic)
- Check that embeddings are generated and searchable

### 10.3 Exhaust Pipeline
- Exhaust one ingested paper at depth 3
- Verify all three termination criteria are implemented
- Check that items are domain-appropriate
- Check that redundancy detection works (some items should be filtered)
- Verify the hard cap calculation

### 10.4 Connect Pipeline
- Run connection discovery on the 3 ingested papers
- Verify candidate generation works
- Check that connection analysis produces specific, evidence-backed results
- Verify that obvious keyword-overlap connections are filtered

### 10.5 Detect Pipeline
- If enough connections exist, run gap detection
- Verify cluster identification works
- Check that gaps are specific and evidence-backed

### 10.6 Draft Pipeline
- If a gap report exists, generate a draft
- Verify the draft references specific papers and claims
- Verify the draft uses appropriate hedging language

### 10.7 End-to-End
- Run the full pipeline: ingest → exhaust → connect → detect → draft
- Verify registry updates at each stage
- Verify no silent failures
- Report the final state of the registry

---

## 11. DOCUMENTATION UPDATES

After building, update these files to reflect the actual system:

1. **README.md** — Update quick start to reflect actual CLI commands,
   actual dependencies, actual setup instructions. Include a "What This Is
   Not" section: not a search engine, not a fact-checker, not autonomous.

2. **USER_GUIDE.md** — Rewrite with actual CLI examples, actual workflow
   (step by step with real commands), troubleshooting section, FAQ.

3. **EXHAUSTION_GUARDRAILS.md** — Add a §10 "Implementation" section
   documenting how each guardrail was implemented, what thresholds were
   chosen, and how to tune them.

---

## 12. FINAL DELIVERABLES CHECKLIST

Verify every item exists and is functional:

- [ ] `pyproject.toml` with all dependencies
- [ ] `azoth.config.yaml` with all defaults
- [ ] `athanasor/config.py` — config loading
- [ ] `athanasor/llm.py` — LLM abstraction
- [ ] `athanasor/embeddings.py` — embedding store
- [ ] `athanasor/pdf_parser.py` — PDF extraction
- [ ] `athanasor/domain_classifier.py` — domain classification
- [ ] `athanasor/registry.py` — registry management
- [ ] `athanasor/schemas.py` — schema validation
- [ ] `athanasor/skills/ingest.py` — full ingest pipeline
- [ ] `athanasor/skills/exhaust.py` — full exhaust pipeline with
       all 3 termination criteria
- [ ] `athanasor/skills/connect.py` — full connection pipeline
- [ ] `athanasor/skills/detect.py` — full gap detection pipeline
- [ ] `athanasor/skills/draft.py` — full draft generation pipeline
- [ ] `athanasor/cli.py` — complete CLI
- [ ] `athanasor/scripts/validate.py` — standalone validation
- [ ] `athanasor/scripts/migrate.py` — schema migration
- [ ] `AGENTS.md` — complete agent operating instructions
- [ ] `README.md` — updated with real quick start
- [ ] `USER_GUIDE.md` — updated with real workflow
- [ ] `EXHAUSTION_GUARDRAILS.md` — updated with implementation §10
- [ ] All existing schemas (`SCHEMA.yaml`, `EXHAUST_SCHEMA.yaml`) unchanged
       unless field additions are documented
- [ ] End-to-end pipeline tested on ≥3 real papers