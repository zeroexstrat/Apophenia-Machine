---
name: azoth
description: Use when the user wants to run the Azoth / Apophenia Machine research-synthesis pipeline, or points you at a folder of papers (PDF/TXT/MD) to process — ingesting, classifying or reclassifying into domains, exhausting papers into derivations, finding cross-paper connections, detecting research gaps, or building review packets. Also use when they mention azoth, apophenia machine, or a nigredo/albedo/citrinitas/rubedo pipeline.
---

# Azoth — Apophenia Machine Operator

Azoth is a locally-runnable research-synthesis pipeline. It ingests papers into
schema-validated records, exhausts each into derivations/missing-angles/experiments,
finds structural connections across papers, and detects candidate research gaps.
**It is a candidate generator. The human decides. Nothing is ever "discovered" or
"confirmed" by the tool.**

You are the operator, not the machine. Bootstrap it, preflight it, drive the cycle,
and hand every decision back to the human.

## Who is the LLM? Two modes

Azoth's generative stages (classification, extraction, exhaustion, connection, gap
detection) need a language model. There are two ways to supply one:

- **Configured backend** — azoth calls its own LLM: Ollama (default,
  `nemotron-3-super:cloud`) or any OpenAI-compatible endpoint. Best for bulk/cheap
  runs. Requires setup; `preflight.py` tells you if it's reachable.
- **You, the driving agent** — when azoth runs as this skill, *you* are a capable model
  already. For **classification** you do not need a separate backend: read the papers,
  decide their domains, and apply your decisions with `azoth reclassify --assignments`
  (below). This is the default for the fresh-clone / no-backend case.

Classification works agent-native with zero backend. The heavier generative stages
(`exhaust`, `connect`, `detect`) still want a configured backend for quality — if none
is reachable, tell the user their options rather than running them degraded.

## Two non-negotiable rules

1. **Preflight the LLM before any batch run.** A dead backend silently degrades to
   heuristics that still write artifacts and bump `exhausted_at_depth` — a broken run
   that looks successful. Always run `scripts/preflight.py` first and stop if it says
   NOT READY (unless the user explicitly wants a heuristic offline pass).
2. **Never promote. Never invent a reviewer.** You run the pipeline up to the review
   packet (`triage` → `review` → `experiment`) and then STOP. `azoth promote` records a
   *human* decision and requires a real reviewer name + note. Do not run it, do not
   fabricate a reviewer, do not mark anything `accepted`. See `reference/human-gate.md`.

**Violating the letter of these rules is violating the spirit of them.** Details and the
full rationalization table are in `reference/human-gate.md` — read it before your first
`triage`/`review`/`promote` interaction.

## The cycle (commands, one line each)

```
preflight → ingest → reclassify → status → awaken(exhaust) → connect → detect
          → draft → triage → review → experiment → [STOP: human promote] → ouroboros
```

Full stage-by-stage detail, flags, and what each writes: **`reference/workflow.md`**.

## Quick start

```bash
python3 skills/azoth/scripts/preflight.py --project-root <repo>   # verify env + LLM
azoth ingest <repo>/nigredo/inbox/ --no-llm                      # PDF/TXT/MD into the registry
# --- classify: if preflight was READY, let the backend do it ---
azoth reclassify --scope unclassified
# --- or, no backend: YOU classify. Read each unclassified paper, then: ---
azoth reclassify --assignments assignments.json                 # your decisions, applied
azoth awaken <domain> --depth 3 --count 5                       # exhaust a slice (wants a backend)
azoth connect --within <domain>                                 # structural pairs
azoth detect --domain <domain>                                  # gap hypotheses
azoth triage <cluster_id> && azoth review <cluster_id>          # build the review packet — then STOP
```

**Agent-as-classifier (`--assignments`):** read each unclassified paper's source file,
decide its domain (propose a new lowercase domain when none fit), write your decisions to
`assignments.json`, and apply with `azoth reclassify --assignments assignments.json`. It
moves files, preserves ids and status, and adopts any `proposed` domain into config — no
backend contacted. Exact JSON shape and steps: **`reference/workflow.md`** §2(b).

Run any command with `--help`; add `--json` for machine-readable output; add `--no-llm`
only for a deliberate heuristic run.

## Reference (load when needed)

- **`reference/workflow.md`** — every stage, its flags, and its outputs.
- **`reference/config-recipes.md`** — pointing azoth at Ollama, LM Studio, or any
  OpenAI-compatible endpoint; environment overrides.
- **`reference/human-gate.md`** — the gating constitution and rationalization table.
- **`reference/troubleshooting.md`** — fallback tags, duplicates, `AZOTH_SKIP_VIGIL`,
  cost expectations, and common errors.

## Installing this skill

The skill ships inside the repo at `skills/azoth/`. To make Claude Code load it, copy or
symlink it into your skills dir:

```bash
ln -s "$(pwd)/skills/azoth" ~/.claude/skills/azoth
```

Codex reads the repo's `AGENTS.md` automatically when working in-tree; this skill's
reference files supplement it. Wherever it runs, azoth needs a shell, a Python
environment, and a reachable LLM backend.
