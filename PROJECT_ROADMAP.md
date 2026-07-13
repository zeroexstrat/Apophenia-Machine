# Azoth v0.2.0 Portfolio Roadmap and Session Handoff

**Authority:** canonical project plan and human-readable session handoff

**Target:** `v0.2.0` portfolio release

**Public position:** A local, human-gated research-operations pipeline that converts technical documents into schema-validated evidence records, ranks candidate connections, and preserves an auditable review trail.
**Last reconciled:** 2026-07-13 after P8 public-narrative implementation and committed-state acceptance at implementation commit `b4f6f1a2e388188afb10dd0d18e5c1990a647ec2`

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
| P3-T1 | Wheel resources and `azoth init` | High | P2-T1 | completed | Fresh wheel operates outside repository on Python 3.10-3.12 |
| P4-T1 | Clean public Git lineage | Ultra | P3-T1 | completion record; valid only with repository-ID/head-bound external attestation | No reachable public pilot objects or private paths; remote CI green |
| P5-T1 | Frozen benchmark protocol and gold-label packet | Ultra | P4-T1 | completed | 12 exact sources, 66 Rafael-authoritative labels, public digest commitment, frozen prompt/metrics, and all audits pass |
| P6-T1 | Benchmark CLI, scorer, report, and synthetic fixtures | High | P5-T1 | completed | Generation and scoring are isolated; deterministic fictional fetch, prepare, run, score, and report artifacts reproduce |
| P7-T1 | Locked benchmark runs and adjudication | Ultra | P6-T1 | completed | Seven sealed runs, explicit Rafael annotations, 91 aggregate metric records, reproducible failure analysis, and honest threshold publication |
| P8-T1 | Public README and rejection/reframe case study | High + Ultra review | P7-T1 | completed | Exact locked metrics, runnable demo, source-backed rejection/reframe case, and executable claim audit pass |
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
| Task | P8-T1 — Public README and rejection/reframe case study |
| Date | 2026-07-13 |
| Effort | High + Ultra review |
| Branch | `codex/p8-public-narrative` |
| Starting SHA | `ea9ed167c743ee8c25eb65804828a9ebf481aec0` |
| Implementation SHA | `b4f6f1a2e388188afb10dd0d18e5c1990a647ec2` before this non-self-referential completion-evidence update |
| Goal | Make the public engineering evidence runnable and exact while preserving suite, human-authority, prior-art, and provider-identity limits |
| Status | complete; README, case study, fictional demo, and executable narrative audit agree with the locked P7 evidence |
| Demo proof | Fresh Python 3.12 environment ingested one newly authored fictional note as one `ingested_only` mathematics record with the intended title, then passed all seven Vigil gates without a model |
| Metric proof | All 13 model metric rows reproduce exact values, numerators, denominators, uncertainty bounds, and threshold outcomes from `locked-comparison.json`; macro-F1, workload reduction, and usefulness misses plus both undefined populations remain visible |
| Case proof | Sanitized narrative preserves `pending_review` candidate -> primary-source contradiction -> human `rejected` decision -> proposed comparison/replication reframe; no private runtime record or completed-experiment claim is published |
| Claim-audit proof | `scripts/check_public_narrative.py` binds README rows to the locked comparison and rejects missing suite scope, provider limitation, human authority, direct prior-art URLs, terminal rejection, reframe wording, and prohibited completion language |
| Verification | 655 tests; 24 focused narrative tests; 17 no-argument maintained checks; public benchmark, narrative, public-tree, hardening, compileall, and diff checks; isolated Python 3.12 demo; and all seven Vigil gates pass |
| Next task | P9-T1 — `v0.2.0`, GitHub metadata, website case study, and deployment |

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
| 2026-07-11 | P3-T1 | isolated feature worktree, Python 3.12 | compileall, full pytest, all existing `scripts/check_*.py` behavioral checks, public-tree audit, hardening audit, `git diff --check`, Vigil verify, and Vigil close | PASS at `949b89164e5902a42ce490393cd06b38d6fa84d2`: 214 tests, all behavioral checks, both audits, and all seven gates pass; tracked worktree remains clean |
| 2026-07-11 | P3-T1 | one built wheel installed into temporary environments outside the clone | `scripts/check_wheel_install.py --wheel <wheel> --python 3.10 --python 3.11 --python 3.12` | PASS: all seven package resources present; each interpreter initializes a workspace, imports no checkout path, ingests a synthetic text record, validates it, writes auto-checkpoint state under the workspace, and passes Vigil start/verify |
| 2026-07-11 | P4-T1 | sealed private archive | sealed verifier before rehearsal | PASS: 523 manifest entries; 11 refs; 1,191 unreachable objects; zero credential findings; source and restored semantic counts both 57 PDFs / 57 library / 54 exhaustion / 57 registry |
| 2026-07-11 | P4-T1 | old public GitHub repository and private mirror | repository-ID check, `git ls-remote`, PR-ref fetch, direct-ref comparison | PASS: repository ID `1269879110`, public `main` `6b1e488a`, retained PR head `31f43596`, and all 8 direct refs agree between remote and mirror; no mutation performed |
| 2026-07-11 | P4-T1 | private policy derivation | old commits union old reachable objects minus exact P2/P3/P4 tree objects | PASS: 888 old reachable objects, 61 old commits, 187 approved tree objects, 807 forbidden objects, 3 private text markers; files remain mode `0600` outside Git |
| 2026-07-11 | P4-T1 | disposable three-commit candidate | reconstruction proof and expected-tip/policy-bound full reachable audit | PASS: exact trees `af8d8efb`, `522f9289`, `109a3e21`; 3 commits, one `main`, 190 reachable objects, zero findings; policy counts/digests bound in JSON evidence |
| 2026-07-11 | P4-T1 | disposable candidate and no-local independent clone | full pytest/check/public/hardening/compile/validate/Vigil/wheel bundle | PASS on both: 358 tests; all maintained checks; seven Vigil gates; one wheel operates outside the clone on Python 3.10, 3.11, and 3.12; final audits and Git status clean |
| 2026-07-11 | P4-T1 | rehearsal procedure corrections | wheel build and remote-removal postconditions | Initial Vigil verify correctly rejected setuptools `build/` drift; targeted cleanup restored PASS. Independent `git fsck` correctly rejected a broken `origin/HEAD`; deleting the stale symbolic ref restored strict PASS. Both corrections are now in the canonical plan. |
| 2026-07-11 | P4-T1 | GitHub preserve-and-replace transaction | repository-ID-bound REST archive, fresh repository creation, direct main-only push, metadata restoration | PASS: old ID `1269879110` is private with 3 branches, 4 tags, and PR #1 head preserved; new public canonical ID `1297840056` advertises only `HEAD` and `refs/heads/main`; rollback was not invoked |
| 2026-07-11 | P4-T1 | first hosted candidate run `29172001060` at `08807693` | exact run/log inspection and local Python 3.10 reproduction | FAIL isolated to unconditional `tomllib` import in one test; Python 3.10 lacks the stdlib module although installed `tomli` is available; no product/runtime failure |
| 2026-07-11 | P4-T1 | Python 3.10 compatibility fix | `tomllib`/`tomli` fallback, focused reproduction, full suites, exact candidate rebuild | PASS: focused 5/5 and full 358/358 under Python 3.10; full 358/358 under Python 3.12; candidate `4a9f317b` passes complete local bundle and strict public-clone audit |
| 2026-07-11 | P4-T1 | GitHub candidate run `29172280966` | hardening matrix on public SHA `4a9f317b4f73a36b4a8a70c06f037d98ee8b1643` | PASS: completed successfully with 3/3 jobs on Python 3.10, 3.11, and 3.12; run URL `https://github.com/zeroexstrat/Apophenia-Machine/actions/runs/29172280966` |
| 2026-07-12 | P5-T1 | private source boundary and public manifest | exact-version, rights, retrieval-chain, SHA-256, permission, and 4/4/4 balance checks | PASS: 12 sources, 12 retrieval records, 66 canonical pairs, zero private files tracked |
| 2026-07-12 | P5-T1 | blinded human adjudication | 70 presentations, four repeated anchors, raw-source evidence fidelity, reconciliation, and private atomic freeze | PASS: 70/70 complete; all repeats agree exactly; 153/153 committed evidence spans match source text; 66 gold pairs validate under Rafael authority |
| 2026-07-12 | P5-T1 | frozen public/private protocol | exact gold and blinded-schema commitment equality, private-topology rejection, public-only and public-plus-private benchmark audits, public-tree audit, full suite, compileall, and Vigil | P5 completion reopened after final review found the unbound schema; replacement verification must supersede this row before P6 begins |
| 2026-07-12 | P5-T1 replacement closeout | exact gold and blinded-schema commitment equality, fail-closed schema and packet validation, private-topology rejection, public-only and public-plus-private benchmark audits, 15 maintained checks, public-tree and hardening audits, full suite, compileall, Python 3.10-3.12 installed-wheel smoke, and Vigil | PASS at `c4a54bfef15dd90485fb2729294ba69e1e438645`: 518 tests; both benchmark modes; all maintained checks; all three wheel interpreters; all seven gates; no benchmark run or performance claim |
| 2026-07-12 | P5-T1 second independent review | rationale-only tracked-data rejection plus canonical paper, pair, packet, and citation identity enforcement | P5 completion reopened: the current tree was clean, but the fail-closed claims exceeded two enforcement paths; replacement verification must supersede this row before P6 begins |
| 2026-07-12 | P5-T1 definitive replacement closeout | exact gold and full blinded-schema commitment equality; canonical paper, pair, packet, and citation validation; rationale-only and private-topology rejection; both benchmark modes; 15 maintained checks; public-tree and hardening audits; full suite; compileall; Python 3.10-3.12 installed-wheel smoke; Vigil | PASS at `87874c013a498965906514368008cef9eba122f5`: 522 tests; both benchmark modes; all maintained checks; all three wheel interpreters; all seven gates; no benchmark run or performance claim |
| 2026-07-12 | P6-T1 | isolated benchmark CLI, exact-source fetch, blinded preparation, deterministic fallback/import runs, full frozen scorer, provenance report, fictional fixtures, and fail-closed review corrections | PASS at `59b29935428cd9e48426c8c167d03e954bd5b716`: 589 tests and 71 focused P6/wheel tests; public benchmark, CLI, public-tree, hardening, compileall, diff, Python 3.10-3.12 wheel, and seven Vigil gates pass; no real benchmark run or performance claim |
| 2026-07-13 | P7-T1 recovery | full parent transcripts, surviving installed wheel, sealed private runs, remote branch, and private bundle | PASS: recovered runtime matches the installed wheel byte-for-byte; 256 focused benchmark tests passed before checkpoint; remote `codex/p7-locked-benchmark-recovered` and verified complete bundle both anchor the recovered tree |
| 2026-07-13 | P7-T1 locked evaluation | unchanged P5 gold commitment, seven-run lock, Rafael annotation packet, Python 3.12 score/report/comparison/failure workflow | PASS: 66 claims, 132 spans, and 66 items validate complete; seven runs and 91 metrics compare; three model thresholds missed and two populations remain undefined; all outputs reproduce byte-for-byte |
| 2026-07-13 | P7-T1 final acceptance | tracked aggregate privacy audit, full suite, public-plus-private protocol audit, maintained checks, hardening, compileall, cross-version wheel smoke, and Vigil | PASS at `8480937dcf2d2f190ca7a962dd0bae8abca7b703`: 631 tests; zero private markers in public results; Python 3.10-3.12 wheels; all seven gates |
| 2026-07-13 | P8-T1 narrative contract | RED/GREEN public-claim audit against the locked comparison and mutation cases | PASS: initial missing-module and missing-live-case failures observed; final 24/24 narrative tests cover 13 exact metric rows, scope, authority, provider provenance, source URLs, rejection order, reframe language, and CLI outcomes |
| 2026-07-13 | P8-T1 isolated reader workflow | exact README demo in a fresh tracked-tree copy and Python 3.12 virtual environment | PASS: one fictional note becomes one `ingested_only` mathematics registry row with the intended title; status and all seven Vigil gates pass without model access |
| 2026-07-13 | P8-T1 final acceptance | full suite, 17 no-argument maintained checks, public benchmark and narrative audits, public-tree, hardening, compileall, diff, and committed-state Vigil | PASS at `b4f6f1a2e388188afb10dd0d18e5c1990a647ec2`: 655 tests; all exact P7 rows and misses visible; no private runtime artifact; all seven gates |

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
| D-015 | 2026-07-11 | Keep immutable contracts in `athanasor.resources` and mutable state in initialized workspaces | Package-resource resolution is installer-portable and prevents runtime writes or editable-layout assumptions in `site-packages` |
| D-016 | 2026-07-11 | Preserve the old GitHub repository privately and create a new canonical public repository | Retained pull-request refs cannot be independently purged in place; replacement removes the contaminated namespace while preserving recovery evidence |
| D-017 | 2026-07-11 | Bind every public-lineage audit to an exact tip and private policy digests | A clean result is meaningful only for the intended state and the same exclusion policy across rehearsal, cutover, and final clone |
| D-018 | 2026-07-11 | Treat hosted Python 3.10 collection as a release gate and use the installed `tomli` fallback | Local 3.12 success did not exercise the Python 3.10 stdlib boundary; the compatibility import is the smallest source-level fix |
| D-019 | 2026-07-12 | Freeze P5 before benchmark tooling and retain Rafael as final label authority | Prevents source, label, prompt, rubric, metric, or threshold changes after observing P6/P7 outputs and preserves a genuine human adjudication boundary |
| D-020 | 2026-07-12 | Give generation-side benchmark commands no gold API and confine explicit gold access to post-lock scoring | Makes the P5 blinded boundary enforceable in command signatures and artifact validators rather than relying on operator convention |
| D-021 | 2026-07-13 | Reserve temporary paths for disposable verification and require authoritative sessions to use durable storage | P7's sole temporary Git branch was purged; fail-closed path checks, an early remote checkpoint, and a verified private bundle prevent recurrence |
| D-022 | 2026-07-13 | Reproduce P7 score artifacts under the lock's Python 3.12 runtime | Cross-version floating-point last-bit differences changed canonical bytes under Python 3.11 even though metric interpretations were unchanged; runtime parity is required for byte identity |
| D-023 | 2026-07-13 | Bind the public narrative to committed evidence with an executable audit | A readable README can still drift; rendering all 13 model rows from the locked comparison and testing scope/provenance language makes public-claim review reproducible |
| D-024 | 2026-07-13 | Publish the looped-transformer event as a rejection-to-reframe case, not a discovery claim | Direct primary sources invalidate the candidate's absence premise; preserving the rejected decision while proposing a controlled replication demonstrates the human gate honestly |

## 10. Completed-session ledger

| Date | Task | Outcome | Implementation SHA | Verification | Push |
|---|---|---|---|---|---|
| — | — | No takeover task completed yet | — | — | — |
| 2026-07-11 | P0-T1 | Canonical handoff and transactional session controls implemented; project-level Corpus and Caput Mortuum gaps remain open | `d92aa9f1678f9d3988ee4551fbe4b2ab71821284` | 20 session tests and 14 check scripts pass; independent review clean; known live-corpus test remains red | implementation SHA verified on `origin/codex/phase0-project-control` |
| 2026-07-11 | P1-T1 | Complete private pilot, PR-aware bundle, raw Git object store, relative manifest, and independent restorations verified; inherited registry defects preserved honestly | `10f4b461f892d12f4580a9baa4f06d2f08bdb72e` | 523 manifest hashes; 495-file source parity; 57/57/54; 11 refs; two clone/fsck paths; 1,191 raw unreachable objects; independent ACCEPT | archive source-ref SHA verified on `origin/codex/p1-private-pilot` before closeout |
| 2026-07-11 | P1-T1 correction | Supersedes the prior row's SHA interpretation: `10f4b461` is the immutable archive source-ref; `9d29d5a` is the P1 implementation commit that records acceptance and the P2 handoff | `9d29d5a83949326faefed8cf4f843e77795dab32` | sealed verifier PASS; 9 tooling tests plus 4 subtests; 115 data-independent tests pass; inherited live-corpus test and two Vigil gates remain explicitly red | implementation SHA verified on `origin/codex/p1-private-pilot`; final closeout push follows this row |
| 2026-07-11 | P2-T1 | Pilot/runtime evidence removed from the tracked product; structural gates made exact; no-LLM synthesis boundaries corrected; atomic agent imports, rejection persistence, synthetic examples, and Apache-2.0 metadata added | `0b2599567271ff9f5d1a02a36c98f71745c0602d` | independent clean clone installs; 183 tests, 15 check scripts, public/hardening audits, compileall, and Vigil pass; tracked runtime/PDF/path counts are zero | not pushed; user did not request push |
| 2026-07-11 | P3-T1 | Wheel-resident contracts, workspace discovery, conflict-safe `azoth init`, installed helper/Vigil execution, and cross-version artifact smoke verification implemented | `949b89164e5902a42ce490393cd06b38d6fa84d2` | 214 tests, all behavioral checks, public/hardening audits, seven gates, and isolated installed-wheel init/ingest/validate/Vigil on Python 3.10-3.12 pass | not pushed; user did not request push |
| 2026-07-11 | P4-T1 completion record | Contaminated GitHub repository preserved privately; new canonical repository exposes a three-commit clean lineage; exact candidate locally and remotely verified | candidate `4a9f317b4f73a36b4a8a70c06f037d98ee8b1643`; final amended SHA is intentionally external to its own commit | sealed archive PASS; 807-object exclusion audit; 358-test local suites; strict public clone; candidate CI run `29172280966` green 3/3 | authoritative only after the exact final `main` SHA, matching successful Actions run, fresh-clone proof, and archive/remote rechecks are recorded in the private closeout |
| 2026-07-12 | P5-T1 provisional closeout superseded | Final review found that the blinded schema was not digested and the packet validator accepted private topology; completion withdrawn pending the corrected full verification | `4c12454b25bdbf36e559c255594a1f53720c5ecc` | Gold commitment remained exact, but generation blinding was not fail-closed; do not begin P6 from this row | not pushed |
| 2026-07-12 | P5-T1 final closeout | Bound the exact blinded-generation schema into the public freeze and replaced blacklist-only checking with fail-closed schema, topology, identity, type, status, and unknown-field validation | `c4a54bfef15dd90485fb2729294ba69e1e438645` | 518 tests; both benchmark audit modes; 15 maintained checks; public-tree, hardening, compileall, wheel smoke, and seven Vigil gates pass | not pushed; user did not request push |
| 2026-07-12 | P5-T1 second closeout superseded | Second independent review found rationale-only public-tree and canonical identity gaps; completion withdrawn pending the corrected full verification | `6143380eee5c2c9d654d0d2bdb0b4740b6aaf33a` | Existing tracked state remained clean, but two fail-closed claims were broader than enforcement; do not begin P6 from this row | not pushed |
| 2026-07-12 | P5-T1 definitive final closeout | Added canonical source, pair, packet, and citation contracts; bound their updated schema digest; and made rationale-only tracking fail closed except for the exact public selection log | `87874c013a498965906514368008cef9eba122f5` | 522 tests; both benchmark modes; 15 maintained checks; public-tree, hardening, compileall, wheel smoke, and seven Vigil gates pass | not pushed; user did not request push |
| 2026-07-12 | P6-T1 | Added the isolated six-command benchmark workflow, deterministic canonical artifacts, complete frozen-metric scorer, provenance-first report, fictional end-to-end fixtures, and fail-closed pair, rank, metric, annotation, path, and commitment validation | `59b29935428cd9e48426c8c167d03e954bd5b716` | 589 tests; 71 focused P6/wheel tests; maintained CLI and benchmark checks; public-tree, hardening, compileall, three installed-wheel interpreters, and seven Vigil gates pass; no real benchmark result exists | not pushed; user did not request push |
| 2026-07-13 | P7-T1 | Recovered and durably anchored the lost temporary branch; sealed seven gold-blind runs; incorporated Rafael's explicit review; published aggregate-only results and honest misses; added fail-closed temporary-worktree guards | `8480937dcf2d2f190ca7a962dd0bae8abca7b703` | 631 tests; 16 maintained checks; public/private benchmark and result privacy audits; byte-identical Python 3.12 reproduction; Python 3.10-3.12 wheel smoke; seven Vigil gates | pushed checkpoint branch; final closeout push follows this row |
| 2026-07-13 | P8-T1 | Published a five-minute local workflow, all 13 exact model metrics with misses and undefined populations, an honest primary-source rejection/reframe case, and an executable claim-drift audit | `b4f6f1a2e388188afb10dd0d18e5c1990a647ec2` | 655 tests; 24 focused narrative tests; 17 maintained checks; clean isolated Python 3.12 demo; public/narrative/hardening/compile/diff checks; seven Vigil gates | not pushed; user did not request push |

## 11. Next-session handoff

**Next task:** P9-T1 — `v0.2.0`, GitHub metadata, website case study, and deployment.

**Effort:** High + Ultra audit.

**Why next:** P8 now supplies a runnable repository entry point, exact evidence table, and audited rejection case. P9 can release that verified tree and align the hosted repository and portfolio surfaces without inventing new performance claims.

**First inspection:** verify the P8 branch's final committed SHA and clean-clone checks, inventory the single version source and package/release metadata, then locate the exact personal-site repository and deployed Cloudflare surface before changing any public endpoint.

**Acceptance:** one-source `v0.2.0` wheel and sdist install independently; remote CI binds the exact release SHA; GitHub description, topics, badge, changelog, and release agree; the recruiter-facing site case and at most one resume bullet use only P8-audited claims; desktop/mobile links and production Cloudflare deployment verify.

**Risk:** release and deployment are irreversible public mutations across repository and website surfaces. Require exact repository/site identity, clean artifact proofs, remote CI, production verification, and a final cross-surface claim scan before publication.

**Inherited open gap:** P8 is locally committed but not pushed or released. Its benchmark remains one 12-paper suite and does not establish external validity, novelty, or provider model identity; P9 must preserve those limits verbatim across every hosted surface.
