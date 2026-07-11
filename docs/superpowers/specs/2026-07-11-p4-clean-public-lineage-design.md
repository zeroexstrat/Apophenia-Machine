# P4-T1 Clean Public Git Lineage Design

**Task:** P4-T1 — Clean public Git lineage

**Effort:** Ultra

**Authority:** `PROJECT_ROADMAP.md` remains canonical. This document resolves P4-T1 implementation and cutover details only.

**Approved approach:** preserve the contaminated GitHub repository privately, replace the public repository, and publish a short reconstructed P2-to-P3 lineage from sanitized tree snapshots.

## 1. Goal and scope

P4-T1 replaces the publicly reachable pilot lineage with a new repository whose complete reachable object graph contains only the verified, data-independent product. The new public repository keeps the canonical name `zeroexstrat/Apophenia-Machine` and exposes only a clean `main` branch at cutover. The contaminated repository is retained under a private archival name in addition to the sealed local P1 archive.

P4-T1 includes:

- re-verifying the sealed P1 private archive before destructive work;
- recording exact local and GitHub ref/object state;
- reconstructing a short public lineage in a disposable repository;
- auditing every reachable path, blob, commit, tag, and ref in that repository;
- proving the reconstructed repository and its wheel work independently;
- preserving the current GitHub repository privately under a non-public archival name;
- creating a fresh public repository at the canonical name;
- pushing only the verified clean `main` lineage;
- verifying GitHub-visible refs, an independent clone, and hosted CI.

P4-T1 does not change product behavior, scientific semantics, schemas, benchmark design, public claims, or release version. P5 and later roadmap tasks remain out of scope.

## 2. Observed starting state

The following state was observed on 2026-07-11 and must be refreshed immediately before cutover:

- sanitized source worktree: branch `codex/p4-clean-public-lineage`, descended from verified P3 closeout `19379ffafd7e967081ffc9e9c9678b6926cdcc0b`;
- public repository: `zeroexstrat/Apophenia-Machine`, repository ID `1269879110`, public, owner-administered;
- public `main`: `6b1e488ad6e65eb65fdf7e4678f8806ae4614a36`;
- remote feature branches: `codex/p1-private-pilot` at `ec7293fd614dc5ebc15be4f518eebe0d03c34235` and `codex/phase0-project-control` at `ee67ead081e538d85ce0924a2fb9e3b14ce644f6`;
- retained pull-request ref: `refs/pull/1/head` at `31f4359683ed5905d5e7940cf1ebde5a41ef6ebd`;
- public tags: annotated `v0.1.0`, `v0.1.1`, `v0.1.2`, and `v0.1.3`;
- no stars, forks, issues, open pull requests, releases, Actions secrets, Actions variables, environments, hooks, Pages site, branch protection, or repository topics;
- latest public hardening run `29143042707` failed at the contaminated P3 predecessor baseline;
- sealed archive: `<private-archive>/pilot-v0.1.3-20260711`.

The sealed verifier currently passes with 523 manifest entries, 11 bundle refs, 1,191 unreachable objects, zero credential findings, and restored counts of 57 PDFs, 57 library records, 54 exhaustion records, and 57 registry rows.

## 3. Alternatives considered

### 3.1 Preserve privately and replace publicly — selected

Rename the current GitHub repository to an archival name, change its visibility to private, create a new public repository using the canonical name, and push only the clean reconstructed lineage.

This is selected because GitHub pull-request refs are not ordinary push-delete refs. Repository replacement makes the old PR ref unreachable from the public namespace while retaining the original remote privately for recovery and audit.

### 3.2 Rewrite the existing repository in place — rejected

Force-update `main` and delete branches/tags in the existing repository, then request GitHub support to purge retained pull-request refs.

This cannot independently satisfy P4 acceptance because the purge is outside the operator's control and its completion time is uncertain.

### 3.3 Delete and recreate the existing repository — rejected

Delete the current repository and create a replacement under the same name.

This removes the retained refs but discards an additional recoverable remote copy. The selected approach achieves the same public boundary while preserving more evidence.

## 4. Clean lineage model

The public history will be reconstructed from sanitized tree snapshots, not rewritten from contaminated ancestors.

The lineage contains three conceptual commits:

1. **Sanitized public baseline:** exact tracked tree at the verified P2 closeout `b7d2f44a8d114dee8195e6cd63a19675f883e38f`, committed as a new root.
2. **Wheel resources and workspace initialization:** exact tracked tree at the verified P3 closeout `19379ffafd7e967081ffc9e9c9678b6926cdcc0b`, committed as the child of the clean P2 root.
3. **P4 public-lineage closeout:** the P3 tree plus the approved P4 spec, implementation plan, roadmap evidence, and any narrowly scoped cutover tooling required by the final plan.

Commit authorship may retain the original project author identity, but commit and committer timestamps will be generated during reconstruction. Original SHAs may appear as documentary evidence in `PROJECT_ROADMAP.md`; they are text, not reachable Git objects.

No merge commits, old tags, feature branches, replace refs, notes refs, pull refs, or Codex refs are imported. The reconstructed repository must have exactly one local branch, `main`, before publication.

## 5. Components and data flow

### 5.1 Preservation boundary

The local sealed P1 archive is read-only. Its manifest verifier runs before rehearsal and again before remote cutover. The existing GitHub repository becomes a second private archival copy; it is never treated as the source for the clean lineage.

### 5.2 Snapshot exporter

The exporter rejects source replace refs, grafts, alternates, shallow/promisor state, partial-clone configuration, and symlinked internal Git storage before reading a snapshot. Every object read uses `--no-replace-objects`. It materializes each approved source commit with `git archive` into a fresh temporary directory, excluding source `.git` metadata by construction. Each stage is committed in a newly initialized repository, preserving only the intended tracked tree.

The reconstruction must be deterministic at the tree level: the materialized P2 and P3 commits must have exactly the same root tree IDs as their corresponding source commits. A direct recursive path/mode/blob-content comparison is also required as human-readable evidence; comparing filenames alone is insufficient.

### 5.3 Reachability auditor

The auditor inspects the complete reachable graph from all refs in the reconstructed repository. It must fail on:

- any ref other than `refs/heads/main` and the symbolic `HEAD`;
- any Git LFS pointer or submodule entry not explicitly expected;
- any `.pdf` path or PDF-signature blob;
- runtime directories or pilot-derived paths outside approved synthetic examples;
- known private absolute paths, usernames, archive paths, or PII-derived runtime identifiers;
- any contaminated-only object IDs derived by subtracting the approved clean snapshot objects from the old public reachable graph, plus every old public commit ID;
- credentials or high-confidence secret patterns;
- malformed Git objects or connectivity errors.

The auditor freezes the initial refname-to-object map and symbolic `HEAD`, traverses only those frozen object IDs, and rejects any concurrent ref or `HEAD` change. Its evidence binds the audited `main` tip and tree plus counts and SHA-256 fingerprints of both private policy inputs. The existing public-tree and hardening audits remain mandatory but do not replace full reachable-object inspection.

### 5.4 Verification runner

The verification runner operates only on the disposable reconstructed repository or a clone of it. It runs:

- `git fsck --full` and ref inventory checks;
- complete pytest suite;
- every maintained `scripts/check_*.py` behavioral check;
- public-tree and hardening audits;
- compileall and `git diff --check`;
- Vigil `start`, `verify`, and `close` with expected clean state;
- one wheel built from the reconstructed tree and installed outside the clone on Python 3.10, 3.11, and 3.12;
- workspace initialization, synthetic ingest, validation, checkpoint, and Vigil smoke operations from each installed wheel.

Generated state from Vigil close must either remain ignored or be committed deliberately before the final tree is approved. A dirty verification checkout is a failure.

### 5.5 GitHub cutover controller

The cutover is an explicit transaction with recorded preconditions:

1. refresh `git ls-remote` and GitHub metadata;
2. require every mutable remote ref to equal the recorded expected SHA;
3. require the sealed archive and disposable-repository verification reports to pass;
4. choose an unused archival repository name;
5. atomically rename the existing repository to that archival name and change it to private in one repository-update request;
6. verify the archived repository by ID, including both name and visibility;
7. create a new public `zeroexstrat/Apophenia-Machine` repository with no initialization content;
8. push the clean `main` branch without tags or auxiliary refs;
9. set and verify `main` as the default branch;
10. restore the intended description and repository settings from the recorded metadata snapshot.

The transaction stops on the first failed postcondition. It never force-pushes to an unverified ref and never deletes the sealed local archive.

### 5.6 Remote verification

After cutover, verification uses a fresh clone path and fresh remote queries. It must prove:

- the canonical public URL resolves to the new repository ID, not `1269879110`;
- only `HEAD` and `refs/heads/main` are advertised;
- no `refs/tags/v0.1.*`, feature branches, or `refs/pull/1/head` are visible;
- every reachable object passes the same lineage audit;
- the independent clone is clean and passes the complete local verification bundle;
- GitHub Actions runs the Python 3.10, 3.11, and 3.12 matrix on the new `main` SHA and every required job succeeds.

P4 remains incomplete while CI is queued, running, missing, or red.

## 6. Failure handling and rollback

### Before GitHub mutation

Any archive, snapshot, reachability, test, wheel, or Vigil failure aborts cutover. No remote state changes.

### After archival rename but before replacement creation

If the canonical replacement cannot be created, restore the archived repository's original name and public visibility, verify the original repository ID and refs, and stop with P4 incomplete.

### After replacement creation but before clean push

If the clean push or default-branch setup fails, rename the empty/incomplete replacement to a recorded private quarantine name after confirming its repository ID, then restore the archived repository's original name and visibility. The authenticated session does not need repository-deletion authority, and P4 never deletes a GitHub repository.

### After clean push

If independent verification or CI fails, keep the contaminated repository private. Fix only the reconstructed clean lineage, rerun all local verification, and update the new public `main` with an exact lease. Do not expose the archived repository merely to restore availability.

The archival repository may be deleted only by a separate future human decision after P4 acceptance and is not part of this task.

## 7. Security and authority boundaries

- The repository visibility change and canonical-name cutover require explicit human approval, supplied for this design on 2026-07-11.
- GitHub operations authenticate as `zeroexstrat`, who currently has admin permission.
- The cutover is a compensating transaction, not an atomic operation across two repositories; a brief canonical-name gap can exist between archival rename and replacement creation.
- Tokens and secret values must never appear in logs or reports.
- Remote mutations use repository IDs and exact ref SHAs as safety boundaries wherever GitHub supports them.
- The clean public repository contains product code and synthetic fixtures only. The sealed corpus, raw Git snapshot, archive manifest, and private archival remote remain private.
- P4 certifies Git lineage hygiene and reproducibility, not scientific validity, novelty, or benchmark performance.

## 8. Acceptance criteria

P4-T1 is complete only when all of the following are proved from current state:

1. The sealed local P1 archive passes its verifier immediately before cutover and is unchanged afterward.
2. The old GitHub repository exists under a recorded archival name, is private, and retains repository ID `1269879110`.
3. The canonical public repository has a new repository ID and exposes only clean `main`.
4. The public reachable graph contains no pilot objects, third-party PDFs, private paths, credentials, contaminated commits, old tags, feature branches, or retained pull-request refs.
5. The clean lineage contains the intended sanitized P2 baseline, P3 wheel/workspace change, and P4 closeout, with tree-level source parity proved for P2 and P3.
6. A clean independent clone passes Git integrity, the full local test/check/audit bundle, Vigil, and wheel-installed smoke verification on Python 3.10, 3.11, and 3.12.
7. GitHub Actions completes successfully for the public `main` SHA across Python 3.10, 3.11, and 3.12.
8. `PROJECT_ROADMAP.md` records the old/new repository IDs, old refs, candidate public SHA/run, verification results, rollback status, and exactly one next task: P5-T1. The amended final SHA/run cannot self-reference from inside that commit; they are recorded in private evidence and the final session handoff/report.
9. The P4 working tree and independent clone are clean at closeout.

If any item is missing, indirect, or unverified, P4 remains in progress.
