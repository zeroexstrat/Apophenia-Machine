# Exhaustion Guardrails — Design Discussion

**Date:** 2026-06-14
**Context:** Development of the Apophenia Machine (Azoth)
**Participants:** Rafa, Hermes (Kimi K2.6)
**Status:** Implemented in `AGENTS.md` and `EXHAUST_SCHEMA.yaml`

---

## 0. Background

Azoth ingests a personal research library and discovers cross-paper connections. The initial design had four phases: Nigredo (inbox), Albedo (structured ingestion), Citrinitas (cross-connection), and Rubedo (gap detection + drafts).

Rafa asked: what if domain subagents could be spawned per-folder, each working through papers one by one, and "exhaust real possibilities of connections and derivations within that one paper"?

---

## 1. The Problem: "Exhaust" Has No Natural Floor

The word "exhaust" implies a completion state. But for an LLM, derivation is unbounded. Given a paper's claims, the model can generate plausible-sounding corollaries, missing angles, and experiments indefinitely. The quality degrades — early derivations are grounded in the paper's actual methods; late derivations are the model confabulating from its training distribution — but the degradation is gradual. There is no cliff. Without explicit termination criteria, the subagent becomes a token furnace.

The core tension: the thing that makes LLMs useful here (generative, associative, capable of seeing angles the original authors might have missed) is the same thing that makes them unbounded. You cannot ask an LLM to "exhaust" a paper any more than you can ask a fire to "exhaust" a log. It will keep burning until something stops it.

---

## 2. The "Continuously" Trap

Rafa's first framing used the word "continuously" — subagents that "continuously go through all the files in it, one by one, and exhaust real possibilities." This would mean:

- Domain subagents running forever
- No kill criteria
- Token costs accumulating without bound
- The quality-to-cost ratio degrading over time as each subagent exhausts the high-signal derivations first, then produces increasingly speculative output

The fix: replace "continuously" with "periodically, bounded, on explicit user command." Subagents are dormant by default. They wake when called. They process N papers per awakening. They return to sleep.

---

## 3. The Dormancy Model

Rafa refined the vision: subagents sleep until awakened. The user controls which domains are active. If working on ML, awaken the ML subagent. If working on physics, awaken physics. A `--all` flag awakens everything.

The key insight: the user is the scheduler, not the cron. The subagent does not decide when to run. Rafa decides which parts of the library are relevant to current work and awakens those subagents only. This prevents the ML subagent from burning tokens making connections in physics at 3 AM.

Each awakening:
- Reads `albedo/registry.jsonl` to find unprocessed papers in the domain
- Processes N papers (default 3, configurable)
- Reports what was done
- Goes back to sleep
- The next awakening resumes from where it left off

The cursor is per-paper: `status: pending | ingested_only | exhausted_depth3 | exhausted_depth5`. No paper is reprocessed unless explicitly flagged with `--reprocess`.

---

## 4. Depth Levels

Ad-hoc exhaustion is inconsistent. One paper gets 2 derivations, another gets 20, based on the subagent's mood. Depth levels make exhaustion predictable:

| Depth | Name | What It Does | Cost (20-page paper) |
|-------|------|-------------|---------------------|
| 1 | Skim | Derivations from major claims only. One exercise. Surface missing angles. | ~$0.03 |
| 2 | Moderate | All derivations. 2–3 exercises. Obvious missing angles. | ~$0.08 |
| 3 | Thorough (default) | Full schema. Derivations, exercises, missing angles, open questions, unstated assumptions, experiments where applicable. | ~$0.10–$0.25 |
| 4 | Deep | Depth 3 + speculative derivations, challenging exercises, necessary connections outside the paper's domain. | ~$0.30–$0.50 |
| 5 | Obsessive | Every angle. Every corollary. Every exercise the material could support. Extended reasoning, multiple passes. | ~$0.50–$1.00 |

Depth is a contract. The subagent knows what is expected. The user knows what they are paying for.

---

## 5. The Self-Termination Problem

The depth contract sets an *expected* level. It does not guarantee the subagent will stop. An eager subagent at depth 5 might generate 100 derivations from a 10-page paper because it *can*, and the output will look plausible.

The question Rafa asked: "Could the subagent communicate when it has reached a maximal state of exhaustion? Is that possible?"

Possible, yes — but only with explicit self-termination criteria. Without them, the subagent has no way to distinguish "this paper genuinely contains 50 derivable corollaries" from "I am confabulating corollaries from my training distribution and dressing them in this paper's language."

---

## 6. The Three Termination Criteria

### 6.1 Redundancy Check

After each batch of 5 exhaustion items, the subagent reviews all previous items for the same paper and asks: "Is this item meaningfully distinct from what has already been derived?"

If ≥3 of 5 are redundant — restating the same idea in slightly different words, deriving the same corollary from a different starting point, proposing an experiment that is a trivial variant of an earlier one — the paper is tapped out. The subagent is no longer deriving. It is rewording.

**Rationale:** LLMs have a well-documented tendency to rephrase rather than generate genuinely novel content when operating within a constrained context. The redundancy check catches this at the unit level (5 items) rather than the paper level, making it sensitive to the moment of quality collapse.

### 6.2 Speculative Ceiling

Derivations and missing angles have a confidence field: `derived | likely | speculative`.

- `derived`: strict logical consequence of a paper's claim or method
- `likely`: probable but not rigorous; follows from the paper's framework with minor assumptions
- `speculative`: interesting possibility with no rigorous grounding in the paper

If the last 5 consecutive items are all `speculative`, the subagent has left the paper behind and is generating content from its own distribution. The ceiling is hit.

**Rationale:** Confidence degradation is the primary signal of exhaustion. Early derivations are grounded. Late ones are invented. The `speculative` tag is the canary. Five in a row means the mine is empty.

### 6.3 Hard Cap

`paper_page_count × depth_multiplier`:

- Depth 3: 1 item per page
- Depth 5: 2 items per page

A 20-page paper at depth 3 produces at most ~20 exhaustion items across all fields. At depth 5: ~40.

This is crude. It prevents runaway on the subagent's worst day — when it fails the redundancy check and the speculative ceiling simultaneously, or when the paper genuinely contains an unusual number of high-confidence derivations. The hard cap is the safety net. It should rarely be the binding constraint. If it triggers frequently, bump the multiplier.

**Rationale:** Page count is a crude proxy for paper complexity, but it is the only one that does not require the subagent to judge its own judgment. The subagent's confidence assessment can be wrong. The page count cannot.

---

## 7. The Termination Report

When the subagent stops — for any reason — it reports:

```
Exhaustion complete for {title}.
  12 derivations (3 derived, 6 likely, 3 speculative)
  4 missing angles
  2 exercises solved
  3 open questions identified
  1 experiment proposed
  
Termination: speculative ceiling. Last 5 derivations were speculative.
Paper exhausted to depth 3 of 5. Deeper exhaustion available at
--depth 4 or --depth 5.
```

The report includes:
- **What was produced** (counts by type and confidence)
- **Why it stopped** (which criterion triggered)
- **Whether deeper exhaustion is available** (depth ceiling not yet reached)
- **Whether re-exhaustion at current depth is pointless** (redundancy or speculative ceiling triggered — the paper has nothing more to give at this depth)

The registry is updated: `status: exhausted_depth3`. A paper exhausted at depth 3 but not at depth 5 can be re-awakened. A paper already exhausted at depth 5 with speculative ceiling is done.

---

## 8. What This Enables

The termination criteria transform exhaustion from an unbounded prompt into a bounded research operation:

1. **The user awakens a subagent at depth 3.** The subagent exhausts papers until it hits a ceiling.
2. **The user reviews the output.** The 12 derivations include 2 that are genuinely novel — connections the user had not considered.
3. **The user awakens the subagent at depth 5 on those specific papers.** The subagent goes deeper, finds more speculative connections, and reports which are speculative vs. grounded.
4. **The user triages.** The grounded ones enter the knowledge graph. The speculative ones are marked for future investigation. The redundant ones are ignored.

The loop is: awaken → receive → triage → decide whether to go deeper. Not: awaken → burn tokens forever.

---

## 9. Unresolved Questions

1. **Can an LLM reliably self-assess redundancy?** The redundancy check requires the subagent to compare its own output across batches. This is asking an LLM to evaluate its own coherence over a 20+ item span. Hallucination risk: the subagent may fail to detect redundancy when it is present, or claim redundancy when items are genuinely distinct. Mitigation: keep batch size small (5 items). Future work: external redundancy scoring via embedding similarity.

2. **Is page count a meaningful proxy for paper "content density"?** A 20-page philosophy paper with dense argumentation may genuinely contain 30 derivable corollaries. A 20-page ML paper with 5 pages of related work and 8 pages of experimental tables may contain 5. The hard cap uniformizes across paper types. Mitigation: depth levels adjust the multiplier. Future work: content-density estimation from the structured YAML record (claims count, methods count).

3. **Does the speculative ceiling prematurely terminate on genuinely speculative papers?** A paper proposing a novel framework may have claims that are themselves speculative. If every derivation from a speculative claim is speculative by inheritance, the ceiling triggers immediately. Mitigation: the `likely` confidence tier is available for grounded extensions of speculative claims. Future work: confidence inheritance rules.

4. **Should exhaustion be cumulative across awakenings?** If the user awakens a subagent at depth 3 and gets 12 derivations, then awakens again at depth 5, should the depth-5 pass re-derive everything, or add to the existing output? Current design: additive. Depth 5 output supplements depth 3 output. Risk: redundancy between depth levels. Mitigation: the redundancy check operates across all items, including those from previous depths.

---

## 10. Design Principles

1. **Exhaustion is a spectrum, not a switch.** A paper is never fully exhausted. It is exhausted *to a given depth*. Deeper work is always available at the cost of lower confidence.

2. **The subagent reports why it stopped.** The termination reason is as important as the output. "Speculative ceiling at item 17" tells the user more than "12 derivations produced."

3. **Confidence degrades. The mechanism for detecting that degradation is the mechanism for stopping.**

4. **The user is the gate.** The subagent surfaces candidates. The subagent decides to stop. But only the user decides whether the output is valuable.

"5. **Hard caps are safety nets, not constraints.** If the hard cap triggers regularly, the cap is wrong. If it never triggers, it is doing its job."
