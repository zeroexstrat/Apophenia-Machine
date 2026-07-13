# P7-T1 Locked Benchmark Runs and Adjudication Design

**Task:** P7-T1 — Locked benchmark runs and adjudication

**Effort:** Ultra

**Authority:** `PROJECT_ROADMAP.md` remains the canonical program plan. The
P5 source set, private-gold commitment, Rafael-authored labels, rubric, metric
definitions, thresholds, uncertainty rules, blinded packet schema, and
no-retuning rule remain immutable. P6 remains the authority for prepared, run,
score, and report artifact validation.

**Approved operating assumption:** The active Codex task is the model-response
operator. Execution metadata records only runtime identifiers that can be
proved. `5.6 Sol` remains the frozen declared backend label from the generation
contract; it is not presented as independently verified provider provenance.

## 1. Pre-run correction and scope

No real benchmark output or score has been produced. Preflight found two
underspecified execution contracts that must be fixed before the first run:

1. the roadmap names six deterministic comparisons, but P6 implements only the
   deterministic hash-overlap fallback; and
2. the frozen generation prompt requests a qualitative structural-relation
   object, while the P6 run/scorer requires a complete row containing
   `predicted_label`, `candidate`, numeric `score`, ranks, and generated items.

P7 adds a public, immutable execution manifest before source preparation or
model generation. This is a preregistration amendment, not post-result tuning.
It binds the exact formulas, response adapter, run order, seed, tool/version
identity, and output-lock policy. It does not replace or edit any P5 authority
artifact. The amendment is invalid if any real gold content, score, threshold
outcome, or prior real response is read before the manifest is committed.

## 2. Authority and contamination boundaries

P7 has three strictly ordered states:

1. **Gold blind:** validate the public freeze, verify source bytes, prepare the
   66 blinded packets, create all deterministic and model responses, import all
   runs, and seal a digest manifest. No command in this state accepts a gold or
   annotation path.
2. **Locked:** independently verify every prepared, response, and run digest;
   make the private run directory read-only; record the Git implementation SHA,
   Python/package versions, seed, backend identity, and exact canonical digest
   of every artifact. Only a complete lock allows transition to scoring.
3. **Gold open:** supply the existing explicit private-gold path to `score`,
   collect only the separately defined human annotations, render reports and
   failure analysis, and publish every result without changing inputs,
   formulas, prompts, thresholds, or outputs.

The repository contains public contracts, tests, verification tooling, and
suite-scoped result fixtures only. Third-party PDFs, prepared packets, raw model
responses, private gold, full score artifacts, and private annotations remain
outside Git with mode `0600` below a mode-`0700` private P7 root.

## 3. P7 execution manifest

Create `benchmarks/operations-decision-support-v1/execution-manifest.yaml` with
schema version 1 and status `frozen_before_real_runs`. It binds:

- benchmark ID and canonical digests of the P5 freeze, protocol, source
  manifest, generation prompt, and blinded schema;
- implementation Git SHA used to prepare and lock runs;
- seed `5607` and canonical pair order;
- all seven run IDs: one model run and six deterministic baselines;
- exact baseline formulas and rank tie-breaking;
- the model response adapter and generated-item mapping;
- the lock manifest schema and required provenance fields;
- the annotation schema and the metrics each annotation field enables;
- an explicit statement that no real output or score preceded the amendment.

The execution manifest digest is copied into every response backend object,
the lock manifest, each score artifact, the comparison report, and the public
result summary. Any mismatch fails closed.

## 4. Deterministic baseline contracts

Every baseline consumes the same validated prepared artifact and emits all 66
canonical pairs. All text normalization is Unicode NFKC, whitespace-collapsed,
and case-folded. Generic tag filtering reuses Azoth's checked-in
`GENERIC_PAIR_TAGS`; production routing constants are copied by name and value
into the execution manifest. Numeric ties are ordered by counterpart paper ID,
then pair ID.

1. **deterministic-routing:** Reproduce the current no-LLM candidate gate:
   candidate when deterministic embedding similarity is at least the frozen
   production threshold, when shared tags intersect the frozen high-signal tag
   set, or when meaningful shared-tag count reaches the frozen strong-overlap
   count. Predict 2 for candidates and 0 otherwise. The numeric routing score is
   `max(max(0, cosine_similarity), high_signal_match, min(1,
   shared_tag_count / strong_overlap_count))`, rounded to 12 decimals. Rank by
   descending score, counterpart paper ID, then pair ID.
2. **all-pairs:** Include all 66 pairs, predict 2, assign score 1, and rank only
   by the deterministic tie-break. This measures exhaustive-review workload
   and an always-relevant classifier.
3. **shared-tag:** Use exact normalized meaningful-tag Jaccard similarity.
   Predict 2 when the intersection is nonempty and 0 otherwise; candidate is
   equivalent to label 2. Rank by Jaccard and the deterministic tie-break.
4. **hash-embedding:** Use Azoth's deterministic SHA-256 fallback embedding on
   the same normalized visible claims, methods, tags, and extracted records.
   Use raw cosine similarity as the score and map `< 0.00` to label 0,
   `[0.00, 0.25)` to label 1, `[0.25, 0.50)` to label 2, and `>= 0.50` to label
   3; candidate means label 2–3.
5. **current-score:** Use the checked-in P6 visible-token overlap score and its
   exact label thresholds (`0.10`, `0.25`, `0.50`). This is the existing
   `deterministic_hash_fallback`, renamed only at the report layer.
6. **fixed-seed-random:** Use `random.Random(5607)` over canonical pair order.
   For each pair call `randrange(4)` for the label and then `random()` for the
   ranking score; candidate means label 2–3. The generated sequence is fixture
   tested so interpreter drift cannot silently change the baseline.

Baselines emit no substantive generated items. Metrics whose population
requires items or human item annotations remain undefined with numerator and
denominator zero; they are not imputed.

## 5. Model response and adapter contract

The model sees one blinded packet at a time plus the exact P5 generation prompt
and rubric scale. It receives no gold, lane, selection, threshold, result, or
cross-pair summary. For each pair it returns the frozen qualitative
`structural_relation` object and one explicit `predicted_label` in `0..3` under
the P5 rubric. `status` remains `pending_review`.

The deterministic adapter verifies IDs and evidence references, then maps:

- `candidate = predicted_label >= 2`;
- `score = predicted_label / 3`, with ranks resolving ties by counterpart paper
  ID and pair ID rather than by an invented confidence probability;
- a nonempty structural assessment to one generated item whose assessment,
  evidence, caveats, transferable implication, and `pending_review` status are
  preserved verbatim;
- `confidence = speculative` for labels 0–2 and `likely` for label 3. The
  adapter never creates `derived` confidence, so the corresponding metric is
  honestly undefined when its denominator is zero.

Raw per-pair responses are canonical JSON and append-only. Retrying a failed
pair creates a separately named attempt; it never overwrites an accepted
response. A run can lock only when exactly one accepted response exists for
each canonical pair and all visible evidence references resolve inside its
packet.

## 6. Lock manifest and recovery

The private lock manifest contains relative paths, byte counts, SHA-256 hashes,
artifact digests, run IDs, backend metadata, seed, implementation SHA, package
versions, start/end timestamps, and a contamination attestation. It excludes
gold paths and gold-derived values. The verifier recomputes all hashes, exact
pair coverage, prepared/run validation, backend-manifest binding, permissions,
and absence of forbidden gold fields.

Locking is atomic: build a temporary manifest, verify it, rename it into place,
chmod the run tree read-only, then verify again. Failure leaves the state
`gold_blind_incomplete`; it never advances to `locked`. Recovery resumes only
missing deterministic/model responses and retains prior attempts for audit.

## 7. Post-lock annotations

After the lock verifies, P7 creates a separate private annotation packet for
model-generated items only. Rafael remains the final human authority. Each
item records explicit booleans for evidence-span validity, claim support,
decision-support usefulness, material redundancy, and unsupported-derived
status where eligible, plus concise rationale. OOD safety remains undefined
unless the locked run contains an eligible OOD assignment decision; P7 does
not fabricate an OOD population.

The scorer receives annotations only through its existing explicit
`--annotations` path. Deterministic baselines do not inherit model annotations.
Every unavailable population is reported as null with a zero denominator.

## 8. Scoring, comparison, and failure analysis

Score all seven locked runs against the same private gold commitment. Each
score must reproduce the 13 frozen metric records with exact numerator,
denominator, uncertainty method/seed, threshold, status, and provenance.
Generate:

- one deterministic Markdown report per run;
- a machine-readable comparison artifact with all metric records and run
  digests;
- a public suite-scoped result summary containing only aggregate metrics,
  denominators, uncertainty, provenance digests, and limitations;
- a failure analysis listing false positives, false negatives, label
  confusions, ranking misses, unsupported or unhelpful items, undefined
  populations, and every missed threshold without exposing private rationales
  or source bytes.

No result is described as scientific validity, novelty, discovery, proof, or
confirmation. The report states that labels and item-quality judgments are
human adjudications and that the suite is a bounded 12-paper benchmark.

## 9. Verification strategy

Before real runs, tests must prove:

- exact execution-manifest validation and digest binding;
- all six baseline formulas on fictional packets, including exact expected
  labels, scores, ranks, and random sequence;
- complete, gold-blind model response validation and deterministic adaptation;
- overwrite refusal, attempt retention, resume behavior, atomic lock, and
  tamper detection;
- refusal to score before a valid complete lock;
- annotation eligibility and exact metric-population boundaries;
- deterministic comparison and failure-analysis rendering;
- no tracked private paths, source bytes, gold, raw responses, or unsupported
  public performance language.

After implementation, run the fictional end-to-end workflow, full tests,
maintained checks, public-tree and hardening audits, compileall, installed-wheel
smoke on Python 3.10–3.12, Vigil, and a clean-worktree check. Only then prepare
the real sources and begin the irreversible gold-blind run sequence.

## 10. Acceptance boundary

P7 is complete only when:

1. the pre-run amendment was committed before any real output or score;
2. the same prepared artifact feeds the model and all six baselines;
3. all response/run artifacts and their provenance lock before gold access;
4. lock verification passes independently after permission sealing;
5. all seven scores reproduce with exact denominators and uncertainty;
6. required eligible human annotations are complete and explicit;
7. comparison and failure analysis include every undefined population and
   missed threshold without retuning;
8. public result fixtures contain no private bytes, paths, labels, rationales,
   or overbroad claims;
9. full repository, wheel, Vigil, and public-tree verification passes; and
10. the roadmap records P7 evidence with exactly P8-T1 next.

P7 remains incomplete if model provenance is overstated, a baseline is omitted,
gold is opened before lock, any output is overwritten, a metric population is
imputed, a missed threshold is hidden, or Rafael's human authority is replaced
by an automated judgment.
