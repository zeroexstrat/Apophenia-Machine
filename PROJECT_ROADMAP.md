# Azoth v0.2.0 Portfolio Roadmap and Session Handoff

**Authority:** canonical project plan and human-readable session handoff

**Target:** `v0.2.0` portfolio release

**Public position:** A local, human-gated research-operations pipeline that converts technical documents into schema-validated evidence records, ranks candidate connections, and preserves an auditable review trail.
**Last reconciled:** 2026-07-11 after verified P2 implementation commit `0b2599567271ff9f5d1a02a36c98f71745c0602d`

## 1. Reading order and authority

1. `AGENTS.md` defines repository operating constraints.
2. This file defines program intent, decisions, progress, and the next task.
3. Schemas define machine artifact contracts.
4. `athanasor/lapis/state.json` is generated machine state, not narrative authority.
5. `athanasor/lapis/memory.jsonl` is ignored crash-recovery telemetry.
6. `HANDOFF.md`, `athanasor/lapis/codex.md`, and files under `docs/history/` are pointers or historical records only.

If live Git, Incipere, Vigil, or test evidence conflicts with this file, stop, record the conflict, and reconcile it explicitly. Never silently inherit stale counts or claims.

## 2. Stable program contract

- The public release demonstrates junior software-engineering and operations-research capability through independently reproducible evidence.
- `5.6 Sol` is the only generative model used. High versus Ultra is task allocation, not a benchmark variable.
- Use **High** for bounded TDD implementation, packaging, fixtures, documentation, metadata, and website work.
- Use **Ultra** for irreversible history changes, authority semantics, benchmark design and interpretation, security review, and public claims.
- Every generated research artifact remains `pending_review` until a named human records a decision.
- Scientific validity and novelty remain human judgments.
- Rafael supplies final benchmark labels.
- Release target is `v0.2.0`; reserve `v1.0.0` for external-user validation.
- Release license is Apache-2.0.
- Public claims must be suite-scoped and reproducible from committed result fixtures.
- Public history contains no third-party PDFs, private pilot artifacts, absolute local paths, or PII-derived runtime identifiers.
- One session handles one task ID at one effort level.

## 3. Final success criteria

- Public Git history is sanitized and independently cloned without retained pilot data.
- Clean-clone and wheel-installed workflows pass on Python 3.10, 3.11, and 3.12.
- `azoth init <directory>` produces a usable workspace without writing into `site-packages`.
- Structural gate names match their executable guarantees.
- A frozen 12-paper operations-decision-support benchmark is human-adjudicated and reproducible.
- Every published metric includes numerator, denominator, provenance, and uncertainty where applicable.
- The looped-transformer case study shows candidate, prior-art rejection, and valid reframe without contradictory states.
- README, GitHub release, package metadata, homepage, technical case study, resume, and essays agree.
- This roadmap ends each session with evidence and exactly one next goal.

## 4. Verified starting baseline

### Git and release

- Branch at takeover: `main`
- Starting SHA: `6b1e488ad6e65eb65fdf7e4678f8806ae4614a36`
- Tag: `v0.1.3`
- Public CI run `29143042707`: failed with 95 passed and 1 failed.
- The failure is `test_live_repo_passes_all_gates`; it relies on ignored local pilot artifacts absent from a clean checkout.
- Built `0.1.3` wheels omit the root schemas, default configuration, and gate definition resources required by core commands.

### Operator workspace versus public checkout

| Measure | Operator workspace | Clean/tracked checkout |
|---|---:|---:|
| Registry rows | 57 | 57 |
| Library records | 57 | 19 |
| Exhaustion records | 54 | 19 |
| Connections visible locally | 91 | 76 |
| Hypotheses visible locally | 5 | 2 |

The operator workspace is richer because ignored local files exist. Local green tests do not prove a clean public checkout is healthy.

### Known release risks at the starting SHA

- The old public history retains 19 PDFs and contaminated pilot objects.
- Closed PR ref `refs/pull/1/head` retains old commit `31f4359`.
- The current public tree still includes pilot-derived artifacts and absolute local user paths.
- `athanasor/lapis/state.json` and `athanasor/lapis/codex.md` contain stale or contradictory state.
- `/concludere` uses `git add -A`, commits before Vigil close, and can leave close-state mutations uncommitted.
- No session-command tests protect staging or close behavior.

## 5. Ordered task ledger

| ID | Deliverable | Effort | Dependency | Status | Exit gate |
|---|---|---|---|---|---|
| P0-T1 | Canonical roadmap and safe session control | High | none | completed; inherited project gates open | Fresh session resumes from roadmap; close cannot stage unrelated files or leave tracked state dirty |
| P1-T1 | Verified private pilot and Git archive | Ultra | P0-T1 | completed | Archive restores independently and every hash passes |
| P2-T1 | Sanitized public baseline and honest structural gates | High + Ultra review | P1-T1 | completed | Clean checkout is data-independent and gate language matches code |
| P3-T1 | Wheel resources and `azoth init` | High | P2-T1 | pending | Fresh wheel operates outside repository on Python 3.10-3.12 |
| P4-T1 | Clean public Git lineage | Ultra | P3-T1 | pending | No reachable public pilot objects or private paths; remote CI green |
| P5-T1 | Frozen benchmark protocol and gold-label packet | Ultra | P4-T1 | pending | Sources, rubric, metrics, thresholds, and blinded boundary are frozen |
| P6-T1 | Benchmark CLI, scorer, report, and synthetic fixtures | High | P5-T1 | pending | Generation and scoring are isolated and deterministic scoring reproduces |
| P7-T1 | Locked benchmark runs and adjudication | Ultra | P6-T1 | pending | Metrics include provenance, denominators, uncertainty, and failure analysis |
| P8-T1 | Public README and rejection/reframe case study | High + Ultra review | P7-T1 | pending | Every claim is evidence-backed and suite-scoped |
| P9-T1 | `v0.2.0`, GitHub metadata, website case study, and deployment | High + Ultra audit | P8-T1 | pending | Release installs independently; site and repository agree |

## 6. Phase contracts

### P0 — Durable project control

- Archive the prior handoff and make this file canonical.
- Make root and Lapis handoff surfaces point here.
- Show roadmap active/next task in Incipere output.
- Replace implicit staging with repeatable explicit `--stage PATH` arguments.
- Reject pre-staged indexes, repository-external paths, traversal, and failed Vigil close.
- Run Vigil close before explicit staging and commit.
- Add isolated tests for session start, staging, refusal, rollback, and clean close.

### P1 — Private preservation

Create `<private-archive>/pilot-v0.1.3-20260711/` with mode `700`, all pilot/runtime data, a `git bundle --all`, ref metadata, and a relative SHA-256 manifest. Verify 57 PDFs, 57 library records, 54 exhaustion records, every hash, bundle restoration, and `git fsck --full` before destructive work.

### P2-P4 — Public product baseline and history

- Remove the pilot and mutable runtime state from the public product.
- Keep public examples under `examples/`; runtime workspaces remain ignored.
- Require schema-valid evidence-bearing claims, exact depth cursor agreement, valid confidence/trace fields, citation-visible checks with honest limits, and persistent rejected-candidate fingerprints.
- Make no-LLM connection processing emit retrieval candidates rather than substantive connections.
- Add `connect --from-file` and `detect --from-file`.
- Package resources, add `azoth init`, and prove wheel operation outside the clone.
- Export the sanitized tree into a new Git repository, force-update with an exact lease, delete `v0.1.x` tags, and purge retained GitHub references. If GitHub cannot purge them, replace the public repository and preserve the contaminated repository privately.

### P5-P7 — Evaluation

- Six authored synthetic documents test deterministic correctness only.
- Twelve exact-version public papers cover operations research, ML/data-science planning, and human/organizational decision-making, four per category.
- Source downloads and raw runs remain ignored; manifests record URLs, hashes, versions, access and license status.
- Rafael adjudicates all 66 pairs from 0-3; relevance is 2-3.
- Generation receives blinded packets without gold labels.
- Add benchmark `validate`, `fetch`, `prepare`, fallback `run`, `score`, and `report` commands.
- Compare 5.6 Sol output with deterministic routing, all-pairs, shared-tag, hash-embedding, current-score, and fixed-seed random baselines.
- Pre-registered primary targets: macro-F1 >= 0.80; unsafe OOD assignment 0%; claim precision >= 0.90; reference recall >= 0.70; candidate recall >= 0.90; workload reduction >= 0.50; precision@5 >= 0.60; nDCG@10 >= 0.65; evidence support >= 0.90; supported items >= 0.85; useful items >= 0.60; redundancy <= 0.15; unsupported `derived` items <= 0.05.
- Missed targets are published honestly and never retuned against the frozen set.

### P8-P9 — Public release

- Rebuild the looped-transformer case as candidate -> primary-source prior art -> rejection -> comparison/replication reframe.
- Lead README with a five-minute demo, architecture, measured table, engineering decisions, rejection case, and limitations.
- Publish only exact benchmark claims; always state that validity and novelty remain human-reviewed.
- Release Apache-2.0 `v0.2.0` from one version source after clean wheel/sdist and remote CI checks.
- Add GitHub description, homepage, topics, CI badge, and changelog.
- Add a recruiter-facing technical case study to the personal site while preserving the reflective essay.
- Replace the homepage's unmeasured pilot wording, add at most one evidence-backed resume bullet, scan all HTML, verify desktop/mobile and links, publish to Cloudflare, and verify production.

## 7. Active session

| Field | Value |
|---|---|
| Task | P2-T1 — Sanitized public baseline and honest structural gates |
| Date | 2026-07-11 |
| Effort | High implementation with Ultra contract review |
| Branch | `codex/p2-public-baseline` |
| Starting SHA | `ec7293fd614dc5ebc15be4f518eebe0d03c34235` |
| Implementation SHA | `0b2599567271ff9f5d1a02a36c98f71745c0602d` |
| Push state | Not pushed; the user did not request a push |
| Goal | Replace the pilot-dependent tracked product surface with a data-independent baseline whose gate language matches executable behavior |
| Status | closed; P2 acceptance met, overall project remains in progress |
| Acceptance | Zero tracked PDFs/runtime artifacts/private paths; isolated fixtures; five bounded structural gates; retrieval-only no-LLM connect; atomic connection and hypothesis imports; durable rejection fingerprints; synthetic examples; installable Apache-2.0 metadata |
| Clean-clone proof | Python 3.12 editable install, 183 tests, public-tree audit, hardening audit, Vigil start, and clean Git status all pass at the implementation SHA |
| Private archive | `<private-archive>/pilot-v0.1.3-20260711` remained sealed and unmodified |
| Open gate | No P2 gate remains open; P3-T1 owns wheel resources and `azoth init` across Python 3.10-3.12 |

## 8. Verification ledger

Sections 8-10 are append-only after this control plane is adopted. Correct an earlier entry by appending a superseding row; do not silently rewrite recorded evidence or decisions.

| Timestamp | Task | Environment | Command/evidence | Result |
|---|---|---|---|---|
| 2026-07-11 | P0-T1 | operator workspace, Python system | `python3 scripts/incipere.py --json` | observed 57 registry, 57 library, 54 exhaust, 91 connections, 5 hypotheses |
| 2026-07-11 | P0-T1 | operator workspace | `python3 athanasor/vigil/verify.py start` | PASS 7 structural checks; reflects local ignored pilot |
| 2026-07-11 | P0-T1 | isolated tracked worktree, Python 3.12 | targeted `test_live_repo_passes_all_gates` | known baseline FAIL: registry points to untracked pilot artifacts; owned by P2-T1 |
| 2026-07-11 | P0-T1 | isolated tracked worktree, Python 3.12 | `pytest tests/test_session_commands.py -q` | PASS: 20/20, including staged-path escape, failed-close rollback, ignored-memory boundary, and roadmap authority regressions |
| 2026-07-11 | P0-T1 | isolated tracked worktree, Python 3.12 | `pytest -q` | 115 passed, 1 known baseline failure: `test_live_repo_passes_all_gates` |
| 2026-07-11 | P0-T1 | isolated tracked worktree, Python 3.12 | `pytest -q -k 'not test_live_repo_passes_all_gates'` | PASS: 115 passed, 1 deselected |
| 2026-07-11 | P0-T1 | isolated tracked worktree | 14 `scripts/check_*.py` checks | PASS: 14/14 |
| 2026-07-11 | P0-T1 | isolated tracked worktree | `scripts/hardening_audit.py` | expected baseline FAIL: missing clean-checkout pilot artifacts; P2-T1 owns remediation |
| 2026-07-11 | P0-T1 | isolated tracked worktree | compileall and `git diff --check` | PASS |
| 2026-07-11 | P0-T1 | independent read-only review, two passes | exploit reproductions and final diff review | PASS: no remaining actionable findings |
| 2026-07-11 | P0-T1 | clean implementation commit | `vigil verify` and `vigil close` | FAIL only Corpus and Caput Mortuum; no Git drift; machine state refreshed to tracked 19/19 artifacts; open gap retained |
| 2026-07-11 | P0-T1 | GitHub remote | `git ls-remote --heads origin refs/heads/codex/phase0-project-control` | implementation ref verified at `d92aa9f1678f9d3988ee4551fbe4b2ab71821284` |
| 2026-07-11 | P1-T1 | operator source and isolated branch | Git, disk, target, and payload inventory | source clean; target absent; 21 GiB free; exact selected payload 495 files / 72,337,431 bytes; core counts 57/57/54 |
| 2026-07-11 | P1-T1 | isolated tracked worktree | `python3 athanasor/vigil/verify.py start` | inherited FAIL only Corpus and Caput Mortuum; no Git drift; preservation proceeds without weakening gates or copying pilot data into public Git |
| 2026-07-11 | P1-T1 | two independent read-only audits | payload, ref, and restoration review | found remote PR ref absent locally and 1,191 unreachable objects; plain local `bundle --all` would be incomplete |
| 2026-07-11 | P1-T1 | private archive | permission, ACL, path, and manifest audit | PASS: parent/archive `0700`; no ACL grants, symlinks, or child group/other bits; 523/523 manifested files pass; manifest self-excludes exactly once |
| 2026-07-11 | P1-T1 | source versus private archive | independent content snapshot | PASS: 495 files, 72,337,431 bytes, 29 directories, and required empty directories match exactly |
| 2026-07-11 | P1-T1 | private archive | structured and semantic validation | PASS: 57 PDFs, 57 library, 54 exhaust, 57 unique registry rows with exact 54 exhausted / 3 ingested-only relationships; 201 JSON, 3 JSONL, 222 YAML, and both embedding artifacts parse |
| 2026-07-11 | P1-T1 | archive-only temporary repositories | sealed verifier, bundle, mirror clone, working clone, runtime overlay, and fsck | PASS: 11 declared refs including `refs/pull/1/head`; both clone modes and `git fsck --full`; repeated 57/57/54 |
| 2026-07-11 | P1-T1 | raw Git snapshot | independent object/ref restoration audit | PASS: exact 1,191 unreachable objects re-derived (6 commits, 283 blobs, 902 trees); both tree-valued Codex refs and PR commit present |
| 2026-07-11 | P1-T1 | runtime and raw Git object store | credential-focused scans | PASS: zero strong matches; no-size-cap independent scan covered all 836 blobs / 24,122,128 bytes |
| 2026-07-11 | P1-T1 | independent adversarial review | requirement-by-requirement artifact review | ACCEPT: no critical or artifact-integrity findings; one-off verifier documentation/coverage debt closed by independent checks |
| 2026-07-11 | P1-T1 | private archive verification tooling | `python -m pytest -q /tmp/test_azoth_p1_archive_tools.py`; sealed archive verifier | PASS: 9 tests plus 4 subtests; 523 entries; 11 bundle refs; 57/57/54 restored; 1,191 unreachable objects; zero credential findings |
| 2026-07-11 | P1-T1 | tracked feature branch | session tests, data-independent suite, and full suite | 20/20 session tests and 115/115 data-independent tests pass; full suite remains 115 pass / 1 inherited live-corpus failure owned by P2-T1 |
| 2026-07-11 | P1-T1 | clean implementation commit | `vigil verify` and `vigil close` | inherited FAIL only Corpus and Caput Mortuum; no Git-drift failure; machine state refreshed to the honest 19-library / 19-exhaust tracked checkout and retained for P2-T1 |
| 2026-07-11 | P1-T1 | GitHub remote | `git ls-remote --heads origin refs/heads/codex/p1-private-pilot` | implementation ref verified at `9d29d5a83949326faefed8cf4f843e77795dab32` before state-and-roadmap closeout |
| 2026-07-11 | P2-T1 | isolated feature worktree, Python 3.12 | full pytest, 15 `scripts/check_*.py` checks, hardening audit, compileall, and `git diff --check` | PASS: 182 tests before the final lockfile regression; all 15 checks and hardening pass |
| 2026-07-11 | P2-T1 | tracked index and focused contract suite | public-tree audit, direct tracked-path/path-pattern scans, and import/gate/rejection tests | PASS: zero tracked runtime/PDF paths, zero private absolute-path matches, and 82 focused contract tests |
| 2026-07-11 | P2-T1 | clean feature commit | `vigil start` and `vigil verify` | PASS: all seven checks, including all five bounded structural gates, on the empty public runtime baseline |
| 2026-07-11 | P2-T1 | independent no-local clone, Python 3.12 | `uv sync --extra dev`, full pytest, public-tree audit, hardening audit, Vigil start, and Git status | PASS at `0b2599567271ff9f5d1a02a36c98f71745c0602d`: install succeeds, 183 tests pass, both audits pass, Vigil passes, and generated `uv.lock` leaves Git clean |

## 9. Decision log

| ID | Date | Decision | Rationale |
|---|---|---|---|
| D-001 | 2026-07-11 | Use evidence-first portfolio strategy | Measured validity is the missing OR signal and constrains public claims |
| D-002 | 2026-07-11 | Make `PROJECT_ROADMAP.md` canonical | Prevent competing stale handoff surfaces |
| D-003 | 2026-07-11 | Replace the public pilot; preserve it privately | Low-fidelity artifacts dominate current public evidence |
| D-004 | 2026-07-11 | Authorize clean history rewrite and repository replacement fallback | Old PDFs, paths, and PR refs remain public otherwise |
| D-005 | 2026-07-11 | Support wheel installation through `azoth init` | Public package must work independently of editable clone layout |
| D-006 | 2026-07-11 | Use a 12-paper operations-decision-support benchmark | Directly supports the target analyst role with bounded 66-pair adjudication |
| D-007 | 2026-07-11 | Rafael provides final gold labels | Preserves a genuine human authority boundary |
| D-008 | 2026-07-11 | Use only 5.6 Sol for generative work; do not compare effort levels | Model consistency without turning reasoning effort into a marketing variable |
| D-009 | 2026-07-11 | Release under Apache-2.0 | Permissive employer-friendly reuse with explicit patent terms |
| D-010 | 2026-07-11 | Publish technical case study alongside reflective essay | Preserve voice while giving recruiters a direct engineering surface |
| D-011 | 2026-07-11 | Treat the independent Phase 0 review as a merge gate | Review reproduced memory-path and staging-allowlist escapes before commit |
| D-012 | 2026-07-11 | Close P0 while retaining inherited project-gate failures as an explicit open gap | P0 control-plane acceptance is met; fabricating private artifacts or weakening the gate test would violate the approved P1-P2 order |
| D-013 | 2026-07-11 | Preserve Git with both a PR-ref-aware `--all` bundle and a raw Git-directory snapshot | A normal local bundle omits remote `refs/pull/1/head`, six unreachable commits, 283 blobs, 902 trees, and two tree-valued Codex refs even though bundle verification can still pass |
| D-014 | 2026-07-11 | Seal the accepted P1 archive and record verifier proof gaps externally instead of rewriting it in place | Every artifact-integrity requirement is independently proven; changing sealed files would invalidate the manifest, while reusable archival tooling is outside the P1 deliverable |

## 10. Completed-session ledger

| Date | Task | Outcome | Implementation SHA | Verification | Push |
|---|---|---|---|---|---|
| — | — | No takeover task completed yet | — | — | — |
| 2026-07-11 | P0-T1 | Canonical handoff and transactional session controls implemented; project-level Corpus and Caput Mortuum gaps remain open | `d92aa9f1678f9d3988ee4551fbe4b2ab71821284` | 20 session tests and 14 check scripts pass; independent review clean; known live-corpus test remains red | implementation SHA verified on `origin/codex/phase0-project-control` |
| 2026-07-11 | P1-T1 | Complete private pilot, PR-aware bundle, raw Git object store, relative manifest, and independent restorations verified; inherited registry defects preserved honestly | `10f4b461f892d12f4580a9baa4f06d2f08bdb72e` | 523 manifest hashes; 495-file source parity; 57/57/54; 11 refs; two clone/fsck paths; 1,191 raw unreachable objects; independent ACCEPT | archive source-ref SHA verified on `origin/codex/p1-private-pilot` before closeout |
| 2026-07-11 | P1-T1 correction | Supersedes the prior row's SHA interpretation: `10f4b461` is the immutable archive source-ref; `9d29d5a` is the P1 implementation commit that records acceptance and the P2 handoff | `9d29d5a83949326faefed8cf4f843e77795dab32` | sealed verifier PASS; 9 tooling tests plus 4 subtests; 115 data-independent tests pass; inherited live-corpus test and two Vigil gates remain explicitly red | implementation SHA verified on `origin/codex/p1-private-pilot`; final closeout push follows this row |
| 2026-07-11 | P2-T1 | Pilot/runtime evidence removed from the tracked product; structural gates made exact; no-LLM synthesis boundaries corrected; atomic agent imports, rejection persistence, synthetic examples, and Apache-2.0 metadata added | `0b2599567271ff9f5d1a02a36c98f71745c0602d` | independent clean clone installs; 183 tests, 15 check scripts, public/hardening audits, compileall, and Vigil pass; tracked runtime/PDF/path counts are zero | not pushed; user did not request push |

## 11. Next-session handoff

**Next task:** P3-T1 — Package wheel resources and implement `azoth init`.

**Effort:** High.

**Why next:** the tracked checkout is now data-independent and installs cleanly, but built wheels still need embedded schemas, defaults, and gate resources plus an explicit workspace initializer.

**First inspection:** read the P3 contract, inventory every repository-root resource opened by installed code, build a wheel, install it into a temporary environment outside the clone, and capture the exact failures before changing packaging.

**Acceptance:** a fresh wheel installed outside the repository works on Python 3.10, 3.11, and 3.12; schemas, default configuration, and Vigil definitions resolve from package resources; `azoth init <directory>` creates a usable empty workspace without writing into `site-packages`.

**Risk:** keep package resources immutable and separate from initialized runtime state. Do not begin the public-history rewrite, delete tags/PR refs, or force-update `main`; those operations remain P4-T1 only.

**Inherited open gap:** editable installs still benefit from repository-root resources, so clean-clone success does not prove wheel independence. P3 must test from an installed artifact in a directory with no repository checkout on `sys.path`.
