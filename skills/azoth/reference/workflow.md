# Azoth workflow — stage by stage

Every command accepts `--help` and `--json`. Slice commands auto-write a recovery
checkpoint to `athanasor/lapis/memory.jsonl`; disable with `--no-auto-checkpoint` or
`AZOTH_AUTO_CHECKPOINT=0`.

## 0. Preflight (always first)

```bash
python3 skills/azoth/scripts/preflight.py --project-root <repo>
```

- Exit 0 → READY. Exit 4 → LLM unreachable; fix it or pass `--allow-no-llm` for a
  deliberate heuristic pass (and tell the user the output is low-fidelity).
- Exit 3 → azoth not installed: `pip install 'git+https://github.com/zeroexstrat/Apophenia-Machine@v0.2.0'`

## 1. Ingest — papers into structured records

```bash
azoth ingest <repo>/nigredo/inbox/            # accepts .pdf, .txt, .md
azoth ingest <path> --domain-override ML      # force a domain
azoth ingest <path> --no-llm                  # heuristic extraction (low fidelity)
azoth ingest <path> --reprocess               # re-ingest existing content
```

Writes `albedo/library/<id>.yaml`, a `registry.jsonl` entry (`ingested_only`, with a
`content_hash`), and embeddings. Files that can't be ingested are reported as `skipped`
(encrypted/image-only PDFs, parser crashes) or moved to `nigredo/duplicates/` (identical
content). **LLM ingestion is strongly preferred** — heuristic records carry a `fallback`
tag and poison everything downstream.

## 2. Reclassify — file leftovers into domains (open vocabulary)

Two modes; both preserve paper IDs and pipeline status and can adopt a **new** domain
into `azoth.config.yaml` so you never hand-edit the taxonomy.

**(a) Backend classifier** — re-runs classification from each paper's stored record:

```bash
azoth reclassify --scope unclassified          # re-file the unclassified backlog
azoth reclassify --scope all --dry-run         # preview moves across the whole library
azoth reclassify --scope unclassified --no-allow-new-domains   # only existing domains
```

`--no-llm` here catches only keyword-obvious cases; the real value needs a backend, and
a fallback-ingested record often lacks signal (see troubleshooting).

**(b) Agent-as-classifier** — *you* read the papers and supply the decisions; no backend:

```bash
# 1. Find the unclassified papers
azoth status --status ingested_only --json      # or read albedo/registry.jsonl
# 2. Read each source file under nigredo/unclassified/ and decide its domain.
# 3. Write assignments.json:
#    {"assignments": [{"paper_id": "<id>", "domain": "biology", "confidence": 0.9,
#                      "reasoning": "..."}, {"paper_id": "<id>", "domain": "chemistry",
#                      "proposed": true, "confidence": 0.85}]}
# 4. Apply
azoth reclassify --assignments assignments.json
azoth reclassify --assignments assignments.json --dry-run   # preview first
```

Reading the actual PDF beats a fallback record every time — this is the recommended path
for a fresh corpus when no backend is configured. Seeded domains: physics, ML, philosophy,
neuroscience, mathematics, biology, unclassified. Set `"proposed": true` for a domain not
in that list; it is validated (safe token) and adopted into config on apply.

## 3. Status — where things stand

```bash
azoth status                       # counts by status/domain
azoth status --domain ML --json
azoth status --status exhausted
```

## 4. Awaken / exhaust — deep work per paper

```bash
azoth awaken <domain> --depth 3 --count 5      # exhaust up to 5 papers in a domain
azoth awaken --all --depth 3 --count 2
azoth exhaust <paper_id> --depth 4             # one paper, explicit
azoth awaken <domain> --reprocess              # redo at a higher depth
```

Depth 1 (skim) → 5 (obsessive). Writes `albedo/exhaust/<id>_exhaust.yaml`, sets status
`exhausted` with `exhausted_at_depth`. Cost grows with depth — see
`reference/troubleshooting.md`.

**Agent-as-exhauster (`--from-file`) — you generate the exhaustion, no backend.** For a
cross-model study, or when no backend is configured, *you* read each paper and produce its
exhaustion, then apply it:

```bash
azoth exhaust --from-file exhaust.json     # your records, validated + filed like the backend path
```

`exhaust.json` shape (bucket lists per paper; canonical or aliased fields both accepted):

```json
{"exhaustion": [
  {"paper_id": "<id>", "depth": 4,
   "derivations": [{"statement": "...", "confidence": "derived", "follows_from": "claim_1"}],
   "missing_angles": [{"angle": "...", "where_it_lands": "..."}],
   "open_questions": [{"question": "..."}],
   "experiments": [{"hypothesis": "...", "design": "...", "predicted_true": "...", "predicted_false": "..."}],
   "unstated_assumptions": [...], "exercises": [...], "necessary_connections": [...]}
]}
```

Each item is normalized to `EXHAUST_SCHEMA` and the paper is marked `exhausted`. Because
every run validates to the same schema, exhaust from different agents on the same library
is directly comparable — see the diff harness below.

## 4b. Compare exhaust across agents/models

Run the same library through different driving agents (each in its own project root), then:

```bash
python3 scripts/exhaust_diff.py --run claude=/path/run_a --run gpt=/path/run_b --run glm=/path/run_c
python3 scripts/exhaust_diff.py --run a=./a --run b=./b --json      # machine-readable deltas
```

Reports per-run totals, per-bucket counts, confidence distribution, coverage, and
per-paper item counts side by side — the substrate for studying how models differ in
generation on identical inputs.

## 5. Connect — structural pairs (Citrinitas)

```bash
azoth connect --within <domain>
azoth connect --cross <d1> <d2>
azoth connect --all
azoth connect --within <domain> --reanalyze-depth-upgrades   # after re-exhausting deeper
```

Prunes pairs without shared tags, scores 1–5 (cross-domain penalty applied). Previously
analyzed pairs are skipped unless `--reanalyze-depth-upgrades` and a paper's depth grew.

## 6. Detect — gap hypotheses (Rubedo)

```bash
azoth detect --domain <domain>
azoth detect --all
```

Clusters ≥3 connected papers into `rubedo/hypotheses/<cluster_id>.yaml`, `pending_review`.

## 7. Draft + review packet

```bash
azoth draft --top 3                 # candidate research notes
azoth triage <cluster_id>           # evidence packet for a human
azoth review <cluster_id>           # deterministic gate checks
azoth experiment <cluster_id>       # pilot experiment spec
```

**Then STOP and hand the packet to the human.** See `reference/human-gate.md`.

## 8. Human decision, then Ouroboros (human-run)

Only a human runs `azoth promote <cluster_id> --decision … --reviewer <name> --note …`.
If prior-art review rejects a novelty claim, expand it back into the queue:

```bash
azoth ouroboros <cluster_id>        # reads rubedo/prior_art/<cluster_id>.yaml
```

## 9. Export (optional)

```bash
azoth export --signals --out signals.json   # exactly 3 bounded, pending_review signals
```

## Integrity checks (anytime)

```bash
azoth validate --all
python3 scripts/hardening_audit.py
```
