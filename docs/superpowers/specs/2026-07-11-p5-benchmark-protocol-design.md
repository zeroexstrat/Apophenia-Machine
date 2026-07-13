# P5-T1 Frozen Benchmark Protocol and Gold-Label Packet Design

**Task:** P5-T1 — Frozen benchmark protocol and gold-label packet

**Effort:** Ultra

**Authority:** `PROJECT_ROADMAP.md` remains the canonical program plan. This
document resolves the P5 protocol, provenance, adjudication, blinding, and
freeze boundaries only.

**Approved approach:** Commit a public protocol and source package, keep the
frozen human gold packet private until P7 locks model outputs, and bind the two
surfaces with a canonical digest and freeze record.

## 1. Goal and scope

P5 freezes the evaluation question before benchmark tooling or model runs can
influence it. The deliverable is a balanced 12-paper operations-decision-
support benchmark with four exact sources in each lane:

1. operations and prescriptive decision support;
2. machine-learning and data-science planning;
3. human and organizational decision-making.

All 66 unordered paper pairs receive a final human relevance label from Rafael
on a 0-3 scale. Labels 2-3 are relevant. The protocol freezes sources, versions,
rubric, labels, metrics, thresholds, uncertainty treatment, prompts, and the
blinded-generation boundary before P6 implements the runner or scorer.

P5 includes source research, inclusion and exclusion decisions, provenance and
rights checks, lawful retrieval metadata, the adjudication packet, the public
freeze commitment, protocol validation requirements, and synthetic validation
fixtures needed to prove the contracts.

P5 does not implement benchmark generation, scoring, reporting, baselines, or
performance claims. Those remain P6-P7 work. It does not commit third-party
source bytes unless redistribution permission is explicit and independently
verified.

## 2. Benchmark construction model

The preliminary item families and research fields are recorded in:

- `azoth-p5-benchmark/outline.yaml`;
- `azoth-p5-benchmark/fields.yaml`.

Each item family is a selection slot, not a preselected paper. Candidate
research may replace a family only when the replacement improves coverage of a
missing decision mechanism without changing the 4/4/4 lane balance. The
selection review explicitly tests coverage of causal intervention, learning to
defer, endogenous feedback, robust uncertainty, institutional discretion, and
organizational data work.

Every selected source must have an exact identity and version, a stable lawful
access route, a recorded SHA-256 digest, retrieval instructions, an access date,
rights metadata, an extraction-quality assessment, and a documented category
fit. Public access does not imply redistribution permission.

The final selection must also avoid a degenerate pair graph. Before freeze, the
selection review checks anticipated cross-lane relations, hard-negative types,
direct citation leakage, hub concentration, and isolated-paper risk. These are
selection diagnostics only; they never become gold labels automatically.

## 3. Two-layer artifact architecture

### 3.1 Public protocol package

The public repository contains:

- the exact source manifest and lawful retrieval instructions;
- source hashes, versions, rights status, and drift policy;
- the final 4/4/4 lane assignment and inclusion/exclusion log;
- the 0-3 adjudication rubric with boundary examples;
- metric definitions, denominators, thresholds, and uncertainty rules;
- the blinded-generation packet schema and prompt contract;
- the canonical pair-list derivation rule;
- synthetic fixtures used to validate the contracts;
- a freeze manifest containing the private gold-packet digest and freeze time.

The public package contains no gold labels, gold rationales, adjudication notes,
or evidence spans before P7 locks generated outputs.

### 3.2 Private adjudication package

The private package contains:

- the canonical 66 unordered pair IDs;
- a seeded randomized presentation order;
- Rafael's 0-3 labels;
- optional confidence and adjudication notes;
- exact evidence spans supporting each final decision;
- repeated anchor pairs used to check intra-rater consistency;
- the rubric and source-manifest identities used during adjudication;
- a canonical content digest and freeze timestamp.

The private path and source bytes are never recorded in public Git. The public
freeze manifest records only the digest algorithm, digest, packet schema
version, pair count, label-authority identity, and freeze timestamp.

### 3.3 Later publication

P7 may publish the frozen gold packet only after generated outputs and run
manifests are sealed. Publication must reproduce the P5 digest exactly. A
different digest is a different benchmark version and cannot score the locked
run under the original P5 identity.

## 4. Canonical identities and hashing

Paper IDs derive from stable source identity and exact version, not local
filenames or extracted titles. Pair IDs derive from the lexicographically sorted
two-paper ID tuple. The canonical pair set is every two-combination of the 12
frozen paper IDs and must contain exactly 66 unique entries.

All freeze digests use SHA-256 over canonical UTF-8 JSON with sorted object keys,
no insignificant whitespace, and arrays in contract-defined order. The private
gold digest excludes filesystem paths and encryption or transport metadata. It
includes the benchmark version, source-manifest digest, rubric version, ordered
canonical pair records, final labels, adjudication evidence, and freeze time.

Changing any frozen source, hash, label, rubric, threshold, prompt, or gold
evidence requires a new benchmark version and a new freeze record. Corrections
are append-only; an old frozen identity is never silently overwritten.

## 5. Adjudication contract

Rafael is the sole final label authority. Each pair is rated:

- `0` — no meaningful structural relationship for the benchmark;
- `1` — topical or lexical overlap without an actionable structural relation;
- `2` — meaningful shared mechanism, method, or decision structure;
- `3` — strong structural relation with a concrete transferable implication.

The written rubric must distinguish 1 from 2 using positive and hard-negative
examples. Direct citation is evidence of an explicit relation but does not force
a high label. Shared authorship, venue, vocabulary, dataset, or broad topic does
not establish relevance by itself.

Adjudication uses a seeded randomized order with lane labels and candidate-
selection notes hidden. A bounded set of anchor pairs is repeated without
revealing the repetition. Any inconsistent anchor is reconciled before freeze,
and the final rationale records the governing boundary rule. There is no
automated override of Rafael's decision.

## 6. Blinded generation boundary

Generation packets may contain exact source-derived records, paper IDs, source
metadata required to interpret the evidence, and the pair or candidate scope
being processed. They must not contain:

- gold labels or relevance classes;
- gold rationales or evidence spans;
- adjudication confidence or notes;
- pair-degree or positive-edge diagnostics;
- target thresholds or benchmark acceptance status;
- inclusion/exclusion reasoning that reveals expected relations;
- scorer outputs or prior benchmark results.

P6 may develop deterministic scoring code against synthetic fixtures only. The
real private gold packet is unavailable to generation and ordinary development
commands. P7 introduces an explicit score-time input after output locking; no
implicit path discovery or environment fallback may expose gold data.

## 7. Metrics and uncertainty freeze

P5 freezes the roadmap's primary targets and exact calculation contracts before
implementation. Every metric definition states its population, numerator,
denominator, averaging rule, undefined-case behavior, and confidence or
uncertainty treatment where applicable.

Primary thresholds remain:

- macro-F1 at least 0.80;
- unsafe out-of-domain assignment exactly 0%;
- claim precision at least 0.90;
- reference recall at least 0.70;
- candidate recall at least 0.90;
- workload reduction at least 0.50;
- precision@5 at least 0.60;
- nDCG@10 at least 0.65;
- evidence support at least 0.90;
- supported items at least 0.85;
- useful items at least 0.60;
- redundancy at most 0.15;
- unsupported `derived` items at most 0.05.

P5 must map each threshold to a future P6-P7 artifact and identify metrics that
cannot be estimated from the 66 pair labels alone. Missing targets are reported
honestly; neither thresholds nor sources may be retuned after outputs are
observed.

## 8. Validation and failure behavior

Protocol validation fails closed when any of the following occurs:

- source count or lane balance differs from 12 and 4/4/4;
- a source lacks exact version, stable identity, lawful route, hash, rights
  status, or extraction-quality metadata;
- a source hash or redirect chain drifts without an explicit version change;
- pair derivation is incomplete, duplicated, self-paired, or non-canonical;
- any label is outside 0-3 or any pair lacks final human adjudication;
- the private gold digest differs from the public freeze commitment;
- gold-only fields appear in a blinded packet or public pre-P7 artifact;
- a metric omits its denominator, averaging rule, or undefined-case behavior;
- a frozen field changes without a new benchmark version;
- source bytes are staged without confirmed redistribution authority.

Validation emits field-addressed errors and performs no partial freeze. A
failed freeze leaves the previous committed manifest and private packet
unchanged.

## 9. Verification strategy

P5 acceptance requires tests or reproducible checks for:

- deterministic source and freeze manifests;
- exact 12-source and 4/4/4 balance checks;
- complete, unique, canonical 66-pair generation;
- stable paper and pair identities;
- lawful retrieval and checksum verification without committing restricted
  source bytes;
- source-version and redirect drift detection;
- rubric schema and 0-3 boundary examples;
- seeded adjudication ordering and anchor-pair insertion;
- private gold-packet canonicalization and stable digesting;
- public/private artifact separation;
- explicit blinded-packet leakage rejection;
- metric-contract completeness;
- append-only replacement of a frozen benchmark identity;
- clean Git status and all seven Vigil gates.

Synthetic documents and labels may verify these contracts. Synthetic evidence
never supports a scientific or performance claim.

## 10. Acceptance boundary

P5-T1 is complete only when:

1. exactly 12 exact-version public sources are selected at 4/4/4 lane balance;
2. source provenance, rights, retrieval, hashes, and drift policy are complete;
3. the public protocol, rubric, metrics, thresholds, prompts, and blinding
   contract are frozen;
4. Rafael has completed and reconciled all 66 private pair labels;
5. the private packet's canonical digest is committed in the public freeze
   manifest without exposing gold material;
6. protocol validation and synthetic contract tests pass;
7. the public branch contains no third-party source bytes without verified
   redistribution permission and no private paths or gold leakage;
8. Vigil passes and the roadmap records P5 evidence with exactly one next task,
   P6-T1.

If Rafael's labels are incomplete, a source version or rights status is
uncertain, or the private/public digest boundary is not independently verified,
P5 remains in progress. P6 implementation does not begin.
