# The gating constitution

Azoth's entire reason to exist is **candidate generation under human control**. The
engine surfaces; the human decides. If you break this, the tool becomes a fabrication
machine that launders LLM guesses into false "findings."

**Violating the letter of these rules is violating the spirit of them.**

## Hard rules

1. **Never run `azoth promote`.** It is the *only* command that records a human
   decision (`accepted` / `rejected` / `needs_prior_art`). It is the human's to run.
2. **Never invent a reviewer or a note.** `promote` requires a real reviewer name and
   rationale. You do not have one. Do not pass your own name, "agent", "reviewer", or a
   placeholder.
3. **Stop at the review packet.** Your last step is `experiment` (or `review`). Present
   `triage`/`review`/`experiment` outputs and explicitly ask the human to make the call.
4. **Never claim discovery.** Say "candidate", "pending review", "unverified". The words
   "discovered", "proven", "confirmed", "novel finding" are forbidden for pipeline output.
5. **Prior art is human-authored.** `rubedo/prior_art/*.yaml` artifacts are written by a
   human after a real literature check. Do not fabricate them to unlock `ouroboros`.
6. **Preflight before batches** (see SKILL.md rule 1) — a silently heuristic run produces
   candidates the human will over-trust.

## What you MAY do autonomously

Ingest, reclassify, status, awaken/exhaust, connect, detect, draft, triage, review,
experiment, validate, export. All of these produce `pending_review` artifacts and mutate
no decision.

## Rationalization table

| Excuse | Reality |
|--------|---------|
| "The evidence clearly supports it, I'll just accept it" | Acceptance is a human act with accountability. Present it; don't decide it. |
| "I'll promote with my own name as reviewer" | Fabricating a reviewer is falsifying a human decision. Forbidden. |
| "The user said 'run the whole thing'" | "The whole thing" ends at the review packet. Promotion is a separate, human step. Confirm, don't assume. |
| "needs_prior_art is harmless, it's not acceptance" | It still records a human decision and mutates status. Human-only. |
| "I'll write the prior_art file so ouroboros can run" | Prior art requires a real literature search you did not do. Fabrication. |
| "It's faster to just mark it accepted" | Speed is not the goal; a trustworthy candidate trail is. |
| "No LLM handy, I'll exhaust with --no-llm and call it done" | Heuristic exhaustion bumps depth with empty artifacts. Preflight or disclose. |

## Red flags — STOP

- About to type `azoth promote`.
- About to put any name in `--reviewer`.
- About to write a file under `rubedo/prior_art/`.
- About to describe output as discovered/proven/confirmed/novel.
- Running exhaust/connect/detect without a passing preflight.

Every one of these means: stop, surface the candidate, hand the decision to the human.
