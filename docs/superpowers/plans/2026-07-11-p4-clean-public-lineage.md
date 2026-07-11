# P4-T1 Clean Public Git Lineage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the contaminated public GitHub lineage with a three-commit, independently verified clean lineage while retaining the original repository privately and proving the final public `main` with hosted CI.

**Architecture:** Add two narrow maintenance tools: one reconstructs exact tree snapshots into a new Git repository, and one audits every reachable ref, commit tree, path, and blob. Rehearse the complete lineage and verification bundle locally, then preserve-and-replace the GitHub repository under repository-ID and exact-SHA preconditions. Use a candidate P4 tip for the first hosted-CI proof, amend that same third commit with cutover evidence, force-update under an exact lease, and require the amended final SHA to pass CI again.

**Tech Stack:** Python 3.10+, Git plumbing commands, pytest, `uv`, GitHub CLI/API, existing Azoth Vigil/public-tree/hardening checks.

## Global Constraints

- `PROJECT_ROADMAP.md` is canonical; P4-T1 is the only task ID in this session.
- The sealed P1 archive is read-only and must pass before and after cutover.
- The old GitHub repository ID is `1269879110`; no destructive action may target a repository whose ID differs.
- The old public `main` lease begins at `6b1e488ad6e65eb65fdf7e4678f8806ae4614a36` and must be refreshed immediately before cutover.
- The clean lineage has exactly three commits: sanitized P2 root, P3 wheel/workspace child, and one P4 tip.
- The P2 and P3 reconstructed commits must exactly match source tree IDs from `b7d2f44a8d114dee8195e6cd63a19675f883e38f` and `19379ffafd7e967081ffc9e9c9678b6926cdcc0b`.
- The public repository exposes only `refs/heads/main`; no tags, feature branches, pull refs, notes, replace refs, or Codex refs.
- Never print tokens, secret values, the sealed archive's absolute path, or private path-pattern payloads.
- P4 changes Git lineage and evidence only; product behavior, schemas, benchmark design, scientific semantics, and version stay unchanged.
- Every remote mutation stops on its first failed postcondition and follows the rollback procedure in the approved spec.
- Source and candidate object reads must reject rewritten/incomplete Git state and use `--no-replace-objects`.
- The build CLI must bind the approved P2/P3 commit and tree IDs, exact three messages, and P2-to-P3-to-P4 ancestry before destination mutation.
- Every lineage-auditor invocation must pass the exact expected tip, both private policy files, and a unique absent JSON-output path; every stage compares the resulting policy counts/digests to the rehearsal baseline.

## File map

- Create `scripts/check_public_lineage.py`: complete reachable-ref/tree/blob audit with JSON evidence output.
- Create `tests/test_public_lineage.py`: isolated Git-repository tests for every rejection and acceptance boundary.
- Create `scripts/reconstruct_public_lineage.py`: exact snapshot reconstruction and final-tip amendment.
- Create `tests/test_reconstruct_public_lineage.py`: tree-parity, ancestry isolation, refusal, and amendment tests.
- Modify `docs/superpowers/specs/2026-07-11-p4-clean-public-lineage-design.md`: replace the impossible all-old-object rule with the contaminated-only object-set rule.
- Create `docs/superpowers/plans/2026-07-11-p4-clean-public-lineage.md`: this implementation plan.
- Modify `PROJECT_ROADMAP.md`: P4 active state, rehearsal/cutover evidence, completed-session ledger, and P5 handoff.

---

### Task 1: Reachable public-lineage auditor

**Files:**
- Create: `scripts/check_public_lineage.py`
- Create: `tests/test_public_lineage.py`

**Interfaces:**
- Consumes: a Git repository path, expected `main` tip, optional newline-delimited forbidden object IDs, optional newline-delimited forbidden byte strings.
- Produces: `audit_repository(repo: Path, forbidden_objects: set[str], forbidden_text: tuple[bytes, ...]) -> AuditReport` and a CLI that exits `0` only for a clean lineage and optionally writes JSON.

- [ ] **Step 1: Write isolated failing tests for accepted history and ref boundaries**

Create repository helpers and these tests in `tests/test_public_lineage.py`:

```python
def test_clean_main_only_repository_passes(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"README.md": b"synthetic only\n"})
    report = audit_repository(repo, forbidden_objects=set(), forbidden_text=())
    assert report.findings == ()
    assert report.refs == ("refs/heads/main",)
    assert report.commit_count == 1


def test_extra_branch_and_tag_fail(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"README.md": b"ok\n"})
    git(repo, "branch", "legacy")
    git(repo, "tag", "v0.1.3")
    report = audit_repository(repo, forbidden_objects=set(), forbidden_text=())
    assert any("unexpected ref: refs/heads/legacy" in item for item in report.findings)
    assert any("unexpected ref: refs/tags/v0.1.3" in item for item in report.findings)
```

- [ ] **Step 2: Run the focused tests and verify import failure**

Run: `python3 -m pytest tests/test_public_lineage.py -q`

Expected: FAIL because `scripts.check_public_lineage` does not exist.

- [ ] **Step 3: Add failing content, object, and historical-tree tests**

Add tests that commit each defect, then replace it in a later commit to prove the auditor checks history rather than only `HEAD`:

```python
def test_historical_pdf_private_path_lfs_gitlink_and_secret_fail(tmp_path: Path) -> None:
    private_path = b"/" + b"Users/example/private.pdf"
    repo = make_repo(
        tmp_path,
        {
            "removed.bin": b"%PDF-1.7\nprivate pilot\n",
            "removed.txt": private_path,
        },
    )
    commit_files(repo, {"removed.bin": None, "removed.txt": None, "safe.txt": b"safe\n"})
    token = b"ghp_" + (b"A" * 36)
    lfs = b"version https://git-lfs.github.com/spec/v1\noid sha256:" + (b"0" * 64) + b"\nsize 1\n"
    commit_files(repo, {"token.txt": token, "asset.dat": lfs})

    nested = make_repo(tmp_path / "nested-parent", {"nested.txt": b"safe\n"})
    git(repo, "-c", "protocol.file.allow=always", "submodule", "add", str(nested), "vendor/nested")
    git(repo, "commit", "-m", "add gitlink")

    report = audit_repository(repo, forbidden_objects=set(), forbidden_text=())
    assert any("PDF signature" in item and "removed.bin" in item for item in report.findings)
    assert any("absolute user path" in item and "removed.txt" in item for item in report.findings)
    assert any("LFS pointer" in item and "asset.dat" in item for item in report.findings)
    assert any("gitlink" in item and "vendor/nested" in item for item in report.findings)
    assert any("credential pattern" in item and "token.txt" in item for item in report.findings)


def test_forbidden_object_and_text_fail(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"safe.txt": b"private-marker\n"})
    blob = git(repo, "rev-parse", "HEAD:safe.txt").stdout.strip()
    report = audit_repository(
        repo,
        forbidden_objects={blob},
        forbidden_text=(b"private-marker",),
    )
    assert any(f"forbidden reachable object: {blob}" in item for item in report.findings)
    assert any("forbidden text" in item for item in report.findings)
```

Use a temporary second repository to create the gitlink object; do not depend on network access.

- [ ] **Step 4: Implement the minimal audit model and Git plumbing**

Implement:

```python
@dataclass(frozen=True)
class AuditReport:
    repo: str
    refs: tuple[str, ...]
    commit_count: int
    reachable_object_count: int
    findings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "repo": self.repo,
            "refs": list(self.refs),
            "commit_count": self.commit_count,
            "reachable_object_count": self.reachable_object_count,
            "findings": list(self.findings),
        }
```

Use these exact function signatures:

- `run_git(repo: Path, *args: str, input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]`
- `list_refs(repo: Path) -> tuple[str, ...]`
- `reachable_objects(repo: Path) -> set[str]`
- `commit_tree_entries(repo: Path, commit: str) -> dict[str, tuple[str, str, str]]`
- `read_blob(repo: Path, object_id: str) -> bytes`
- `audit_repository(repo: Path, forbidden_objects: set[str] | None = None, forbidden_text: tuple[bytes, ...] = ()) -> AuditReport`

Audit requirements:

- allow exactly `refs/heads/main` from `git for-each-ref`;
- enumerate every commit with `git rev-list --all`;
- enumerate each commit tree with `git ls-tree -r -z --full-tree` so removed historical paths remain visible;
- reuse `scripts.check_public_tree.audit_paths` per historical tree;
- reject mode `160000`, LFS pointer prefix, `.pdf` paths, `%PDF-` blob signatures, private/user path patterns, pilot/runtime identifiers, supplied forbidden text, and high-confidence token/private-key patterns;
- intersect the reachable-object set with the supplied contaminated-only object set;
- include commit, path, and object ID in content findings;
- run `git fsck --full --strict` and report failure;
- never decode arbitrary blobs as required text; operate on bytes.

- [ ] **Step 5: Implement the CLI and JSON evidence output**

Support:

```text
python3 scripts/check_public_lineage.py \
  --repo PATH \
  --expected-tip OBJECT_ID \
  [--forbidden-object-file PATH] \
  [--forbidden-text-file PATH] \
  [--json-output PATH]
```

The CLI prints `Public lineage audit: PASS` plus counts on success. JSON evidence records the expected/main tip, main tree, and count/digest of each private policy input. It prints every finding and exits `1` on audit failure. Missing/malformed input files and non-Git paths exit `2` without a traceback.

- [ ] **Step 6: Run focused tests and live-tree regression tests**

Run:

```bash
python3 -m pytest tests/test_public_lineage.py tests/test_public_tree.py -q
python3 scripts/check_public_tree.py
git diff --check
```

Expected: all tests PASS; public tree audit PASS; no whitespace errors.

- [ ] **Step 7: Commit the auditor**

```bash
git add scripts/check_public_lineage.py tests/test_public_lineage.py
git commit -m "feat: audit complete public Git lineage"
```

---

### Task 2: Exact clean-lineage reconstructor

**Files:**
- Create: `scripts/reconstruct_public_lineage.py`
- Create: `tests/test_reconstruct_public_lineage.py`

**Interfaces:**
- Consumes: a clean source Git repository, an absent/empty destination path, and ordered `Snapshot(ref, message)` values.
- Produces: `build_lineage(...) -> tuple[CommitProof, ...]`, `amend_tip(...) -> CommitProof`, and JSON proof containing source ref/tree and reconstructed commit/tree IDs.

- [ ] **Step 1: Write the failing three-snapshot parity test**

```python
def test_builds_three_commit_lineage_with_exact_tree_parity(tmp_path: Path) -> None:
    source, refs = make_source_history(tmp_path)
    destination = tmp_path / "clean"
    proofs = build_lineage(
        source,
        destination,
        (
            Snapshot(refs["p2"], "Sanitized public baseline"),
            Snapshot(refs["p3"], "Wheel resources and workspace initialization"),
            Snapshot(refs["p4"], "Clean public Git lineage"),
        ),
    )
    assert len(proofs) == 3
    assert git(destination, "rev-list", "--count", "main").stdout.strip() == "3"
    assert [proof.source_tree for proof in proofs] == [proof.clean_tree for proof in proofs]
    assert git(destination, "for-each-ref", "--format=%(refname)").stdout.splitlines() == ["refs/heads/main"]
```

- [ ] **Step 2: Run the test and verify import failure**

Run: `python3 -m pytest tests/test_reconstruct_public_lineage.py -q`

Expected: FAIL because `scripts.reconstruct_public_lineage` does not exist.

- [ ] **Step 3: Add failing safety and amendment tests**

Cover:

- destination already contains a file;
- source has uncommitted tracked or untracked changes;
- source ref does not resolve to a commit;
- source snapshot contains an unsafe archive member path;
- executable mode and symlink survive with identical tree ID;
- unrelated source ancestors/refs do not appear in destination;
- `amend_tip` preserves the first two commit IDs, changes only the third commit, and exactly matches the updated source tree.

The amendment assertion is:

```python
before = git(destination, "rev-list", "--reverse", "main").stdout.splitlines()
proof = amend_tip(source, destination, Snapshot(updated_ref, "Clean public Git lineage"))
after = git(destination, "rev-list", "--reverse", "main").stdout.splitlines()
assert after[:2] == before[:2]
assert after[2] != before[2]
assert proof.source_tree == proof.clean_tree
```

- [ ] **Step 4: Implement snapshot extraction and exact commits**

Implement:

```python
@dataclass(frozen=True)
class Snapshot:
    ref: str
    message: str


@dataclass(frozen=True)
class CommitProof:
    source_ref: str
    source_commit: str
    source_tree: str
    clean_commit: str
    clean_tree: str
```

Use these exact function signatures:

- `materialize_snapshot(source: Path, destination: Path, ref: str) -> tuple[str, str]`
- `commit_snapshot(source: Path, destination: Path, snapshot: Snapshot, *, amend: bool = False) -> CommitProof`
- `build_lineage(source: Path, destination: Path, snapshots: Sequence[Snapshot]) -> tuple[CommitProof, ...]`
- `amend_tip(source: Path, destination: Path, snapshot: Snapshot) -> CommitProof`

Implementation constraints:

- require a clean source index/worktree via `git status --porcelain=v1 --untracked-files=all`;
- require an absent or empty destination and initialize with `git init -b main`;
- copy source `user.name` and `user.email` into destination without reading global state later;
- generate `git archive --format=tar <resolved-commit>` from the trusted source;
- validate every archive name is relative and contains no `..` traversal before extraction;
- clear destination content without following symlinks and never remove `.git`;
- `git add -A`, commit with the supplied message, and compare exact root tree IDs;
- after each build/amend, require one branch named `main`, expected commit count, clean status, and `git fsck --full --strict`.

- [ ] **Step 5: Implement build/amend CLI modes and proof JSON**

Support:

```text
python3 scripts/reconstruct_public_lineage.py build \
  --source PATH --destination PATH \
  --expected-first-commit P2_COMMIT --expected-first-tree P2_TREE \
  --expected-second-commit P3_COMMIT --expected-second-tree P3_TREE \
  --snapshot REF::MESSAGE --snapshot REF::MESSAGE --snapshot REF::MESSAGE \
  --json-output PATH

python3 scripts/reconstruct_public_lineage.py amend \
  --source PATH --destination PATH \
  --snapshot REF::MESSAGE \
  --expected-tip CANDIDATE_TIP \
  --expected-first-tree P2_TREE --expected-second-tree P3_TREE \
  --expected-source-commit SOURCE_P4_COMMIT \
  --expected-source-tree SOURCE_P4_TREE \
  --json-output PATH
```

Reject malformed snapshot arguments and a build count other than exactly three for P4 CLI use, while keeping `build_lineage` independently testable.

- [ ] **Step 6: Run focused tests, auditors, and compile check**

```bash
python3 -m pytest tests/test_reconstruct_public_lineage.py tests/test_public_lineage.py -q
python3 -m compileall scripts/check_public_lineage.py scripts/reconstruct_public_lineage.py
python3 scripts/check_public_tree.py
git diff --check
```

Expected: all PASS.

- [ ] **Step 7: Commit the reconstructor**

```bash
git add scripts/reconstruct_public_lineage.py tests/test_reconstruct_public_lineage.py
git commit -m "feat: reconstruct sanitized public lineage"
```

---

### Task 3: Full local rehearsal

**Files:**
- Create outside Git: temporary ref, forbidden-object, forbidden-text, metadata, proof, audit, test, and wheel reports.

**Interfaces:**
- Consumes: sealed archive path in shell variable `P1_ARCHIVE`, current source repo, old public GitHub refs.
- Produces: a disposable three-commit candidate repository and complete private rehearsal evidence; no remote mutation.

- [ ] **Step 1: Re-run the sealed archive verifier in the project environment**

Run the archive's `verify_archive.py` with the project virtualenv Python and the archive path supplied as an argument. Save stdout under a private temporary evidence directory, not the repository.

Expected JSON: `status: PASS`, 523 manifest entries, 11 bundle refs, 1,191 unreachable objects, zero credential findings, and 57/57/54 restored corpus counts.

- [ ] **Step 2: Capture a fresh old-remote mirror and exact preconditions**

Create a temporary mirror from `https://github.com/zeroexstrat/Apophenia-Machine.git`, explicitly fetch `+refs/pull/*:refs/pull/*`, and save:

```bash
git -C "$MIRROR" ls-remote origin | sort > "$EVIDENCE/old.lsremote"
gh api repos/zeroexstrat/Apophenia-Machine
gh run list --repo zeroexstrat/Apophenia-Machine --limit 20 --json databaseId,headSha,status,conclusion,url
```

Save the direct mirror inventory deterministically as tab-delimited object/ref rows:

```bash
git -C "$MIRROR" for-each-ref --format='%(objectname)%09%(refname)' \
  | sort > "$EVIDENCE/mirror.direct"
```

Require repository ID `1269879110`, public visibility, old `main` at the refreshed expected SHA, and retained `refs/pull/1/head`. Abort if any expected ref moved without reconciliation.

- [ ] **Step 3: Derive contaminated-only objects without publishing the set**

In the temporary mirror, collect every old reachable object and every old commit. Collect approved objects from the three exact source trees only; never run `rev-list` from a source commit because that would admit contaminated ancestry. Use:

```bash
cut -f1 "$EVIDENCE/mirror.direct" | sort -u > "$EVIDENCE/old.tips"
git -C "$MIRROR" --no-replace-objects rev-list --objects \
  --no-object-names --stdin < "$EVIDENCE/old.tips" | sort -u \
  > "$EVIDENCE/old.objects"
git -C "$MIRROR" --no-replace-objects rev-list --stdin \
  < "$EVIDENCE/old.tips" | sort -u > "$EVIDENCE/old.commits"

for tree in "$P2_TREE" "$P3_TREE" "$P4_TREE"; do
  git -C "$SOURCE" --no-replace-objects rev-list --objects \
    --no-object-names "$tree"
done | sort -u > "$EVIDENCE/approved.objects"

comm -23 "$EVIDENCE/old.objects" "$EVIDENCE/approved.objects" \
  > "$EVIDENCE/old-minus-approved.objects"
sort -u "$EVIDENCE/old.commits" "$EVIDENCE/old-minus-approved.objects" \
  > "$EVIDENCE/forbidden.objects"
```

The resulting forbidden set is:

```text
all old commits UNION (all old reachable objects MINUS approved snapshot objects)
```

Generate the private-text file from local environment values without echoing it, then `chmod 0600` both policy files. Keep both files outside Git. Record only counts and SHA-256 digests publicly, and require the auditor's policy counts/digests to remain identical in every candidate, clone, amended-tip, and final audit.

- [ ] **Step 4: Build and audit the disposable three-commit lineage**

Run the reconstructor with:

- P2: `b7d2f44a8d114dee8195e6cd63a19675f883e38f` — `Sanitized public baseline`
- P3: `19379ffafd7e967081ffc9e9c9678b6926cdcc0b` — `Wheel resources and workspace initialization`
- P4: current clean source `HEAD` — `Clean public Git lineage`

Pass all four approved P2/P3 commit/tree identity flags to the build CLI. Then run `scripts/check_public_lineage.py` with `--expected-tip`, both private forbidden files, and `--json-output`. Require three commits, exact P2/P3/P4 tree parity, one `main` ref, no findings, matching policy counts/digests, and clean status.

- [ ] **Step 5: Run the complete verification bundle inside the disposable repository**

Run, saving command/status summaries privately:

```bash
python3 athanasor/vigil/verify.py start
uv run python -m pytest -q
for check in \
  scripts/check_cli.py \
  scripts/check_cli_diagnostics.py \
  scripts/check_connect_pruning.py \
  scripts/check_connect_reanalysis.py \
  scripts/check_domain_classifier.py \
  scripts/check_draft_artifacts.py \
  scripts/check_exhaust_llm_budget.py \
  scripts/check_human_gate_contract.py \
  scripts/check_llm_providers.py \
  scripts/check_negative_paths.py \
  scripts/check_ouroboros.py \
  scripts/check_pipeline_smoke.py \
  scripts/check_public_tree.py \
  scripts/check_rubedo_review_path.py \
  scripts/check_semantic_pipeline.py; do
  uv run python "$check"
done
uv run python scripts/hardening_audit.py --project-root .
uv run python -m compileall athanasor scripts
uv run python scripts/validate.py --all
git diff --check
git status --porcelain=v1
uv build --wheel --out-dir "$EVIDENCE/dist"
WHEEL="$(find "$EVIDENCE/dist" -maxdepth 1 -name 'azoth-*.whl' -print -quit)"
test -n "$WHEEL"
python3 scripts/check_wheel_install.py --wheel "$WHEEL" \
  --python 3.10 --python 3.11 --python 3.12
git clean -ffdx -- build azoth.egg-info
python3 athanasor/vigil/verify.py verify
python3 athanasor/vigil/verify.py close
```

Remove generated ignored build/runtime files, rerun the expected-tip/policy-bound lineage audit with JSON evidence, and require exact tree parity plus clean status. Any failure aborts P4 before remote mutation.

- [ ] **Step 6: Perform an independent local clone proof**

Clone the disposable repository into a second temporary path using `--no-local`, record the advertised refs, remove `origin`, and explicitly delete a broken `refs/remotes/origin/HEAD` symbolic ref if Git leaves one behind. Require `git fsck --full --strict` before the strict local-ref audit. Repeat ref inventory, complete lineage audit, full pytest, public/hardening checks, Vigil, and wheel matrix. Require no source or first-rehearsal path on Python import paths.

- [ ] **Step 7: Record rehearsal evidence and commit the P4 candidate source tree**

Update only the active-session and append-only ledger portions of `PROJECT_ROADMAP.md`:

- task P4-T1, effort Ultra, branch name, starting SHA;
- archive verification counts;
- remote repository ID/ref inventory;
- lineage proof tree IDs and audit counts;
- full local/independent-clone verification counts;
- status `in progress; local rehearsal passed; remote cutover pending`;
- exactly one next task remains P4-T1 until remote acceptance.

Run public-tree audit and `git diff --check`, then commit:

```bash
git add PROJECT_ROADMAP.md
git commit -m "docs: record P4 cutover rehearsal"
```

Rebuild the disposable candidate so its third tree exactly matches this source `HEAD`. Repeat the entire Step 5 bundle and Step 6 independent-clone proof on that rebuilt SHA, including Vigil, wheel matrix, expected-tip/policy-bound JSON audits, policy digest comparison, exact tree parity, and clean status. Record only that fully verified candidate SHA as the exact first-push value.

---

### Task 4: Preserve-and-replace GitHub cutover

**Files:**
- No tracked files during the transaction.
- Create private temporary metadata and transaction logs outside Git.

**Interfaces:**
- Consumes: fully verified candidate repository, refreshed old repository ID/refs, authenticated owner-admin GitHub session.
- Produces: private archival repository and fresh public canonical repository with candidate `main` only.

- [ ] **Step 1: Run the final no-mutation preflight**

Immediately before mutation, require:

- source and candidate worktrees clean;
- sealed archive verifier PASS again;
- expected-tip/policy-bound candidate lineage audit PASS again with fresh JSON evidence and matching policy counts/digests;
- `gh auth status` identifies `zeroexstrat` with repo/workflow authority;
- canonical repository ID remains `1269879110`;
- fresh `git ls-remote` exactly matches the recorded lease inventory;
- archival name `Apophenia-Machine-pilot-v0.1.3-archive` is unused;
- quarantine name `Apophenia-Machine-p4-failed-cutover` is unused;
- candidate has exactly three commits and one local `main` ref.

- [ ] **Step 2: Snapshot mutable GitHub metadata privately**

Save repository metadata, collaborators/invitations, deploy keys, hooks, rulesets, Actions permissions, secret/variable names, environments, Pages, protections, releases, topics, labels, milestones, wiki contents, security settings, issues/PR counts, and recent runs. Do not store secret values. Allowlist only the owner-admin collaborator, closed PR #1, and default labels observed at preflight. Require no non-owner collaborators, invitations, deploy keys, hooks, rulesets, secrets, variables, environments, Pages, protections, releases, topics, milestones, or wiki contents. Record Actions and merge/settings flags for restoration.

- [ ] **Step 3: Atomically archive the old repository name and visibility**

Use the GitHub repository update API to set both:

```json
{"name": "Apophenia-Machine-pilot-v0.1.3-archive", "private": true}
```

Target `zeroexstrat/Apophenia-Machine` only after checking repository ID `1269879110`. Verify by repository ID that the renamed repository exists, is private, and retains its original default branch and refs. If this postcondition fails, restore original name/visibility and stop.

Use one REST request, not GraphQL or split mutations:

```bash
test "$(gh api repos/zeroexstrat/Apophenia-Machine --jq .id)" = 1269879110
gh api --method PATCH repos/zeroexstrat/Apophenia-Machine \
  -f name=Apophenia-Machine-pilot-v0.1.3-archive -F private=true \
  > "$EVIDENCE/archive-patch.json"
gh api repositories/1269879110 > "$EVIDENCE/archive-post.json"
jq -e '.id == 1269879110 and .name == "Apophenia-Machine-pilot-v0.1.3-archive" and .private == true' \
  "$EVIDENCE/archive-post.json" >/dev/null
```

- [ ] **Step 4: Create and validate the empty canonical public repository**

Create `zeroexstrat/Apophenia-Machine` as public with no README, license, or `.gitignore`. Restore the recorded description and intentional settings. Record and require a new repository ID different from `1269879110`. Verify the old repository remains private under the archival name.

Create from the saved metadata without initialization content and bind the new ID:

```bash
jq '{name:"Apophenia-Machine", description, homepage, private:false,
     has_issues, has_projects, has_wiki, has_downloads, auto_init:false}' \
  "$EVIDENCE/old-repo-preflight.json" \
  | gh api --method POST user/repos --input - > "$EVIDENCE/new-repo.json"
NEW_ID="$(jq -er .id "$EVIDENCE/new-repo.json")"
test "$NEW_ID" != 1269879110
test "$(gh api repos/zeroexstrat/Apophenia-Machine --jq .id)" = "$NEW_ID"
```

After the archive patch, require the archival name to be occupied by old repository ID `1269879110` and the preflighted quarantine name to remain unused. If replacement setup fails, perform the no-delete rollback only in this order: verify the new repository ID; REST-patch it to the quarantine name and private visibility; verify its ID/name/private state; then REST-patch repository ID `1269879110` back to the canonical name and public visibility; verify its ID, metadata, and exact original refs. If quarantine fails, stop and do not attempt the old-name restore.

```bash
test "$(gh api repos/zeroexstrat/Apophenia-Machine --jq .id)" = "$NEW_ID"
gh api --method PATCH repos/zeroexstrat/Apophenia-Machine \
  -f name=Apophenia-Machine-p4-failed-cutover -F private=true \
  > "$EVIDENCE/quarantine-patch.json"
jq -e --argjson id "$NEW_ID" \
  '.id == $id and .name == "Apophenia-Machine-p4-failed-cutover" and .private == true' \
  < <(gh api "repositories/$NEW_ID") >/dev/null
gh api --method PATCH \
  repos/zeroexstrat/Apophenia-Machine-pilot-v0.1.3-archive \
  -f name=Apophenia-Machine -F private=false \
  > "$EVIDENCE/old-restore-patch.json"
jq -e '.id == 1269879110 and .name == "Apophenia-Machine" and .private == false' \
  < <(gh api repositories/1269879110) >/dev/null
cmp "$EVIDENCE/old.lsremote" \
  <(git ls-remote "$CANONICAL_URL" | sort)
```

- [ ] **Step 5: Push only candidate main**

Push `refs/heads/main:refs/heads/main` directly to the canonical public URL without adding a remote. Do not use `--mirror`, `--tags`, or push any source-worktree ref. Record the candidate SHA and verify advertised refs are exactly:

```bash
git -C "$CANDIDATE" push --no-follow-tags "$CANONICAL_URL" \
  refs/heads/main:refs/heads/main
```

```text
HEAD -> candidate SHA
refs/heads/main -> candidate SHA
```

Explicitly query `refs/tags/v0.1.*`, `refs/pull/1/head`, the old feature branches, notes, replace refs, and Codex refs; require all absent.

- [ ] **Step 6: Independently clone and audit the new public repository**

Clone from GitHub into a fresh temporary path with `--no-local`. Record advertised refs, remove `origin`, and explicitly delete a broken `refs/remotes/origin/HEAD` symbolic ref if present before `git fsck --full --strict` and the strict local-ref audit. Re-run the expected-tip/policy-bound JSON audit using the private forbidden sets, compare policy counts/digests, run the full pytest/check/audit/Vigil bundle and Python 3.10-3.12 wheel matrix. Confirm the public URL resolves to the new repository ID.

- [ ] **Step 7: Wait for candidate hosted CI**

Locate the hardening push run whose `headSha` equals the candidate SHA. Use condition-based polling, not fixed sleeps, until completed. Require all Python 3.10, 3.11, and 3.12 jobs successful. Save the run ID and URL for the roadmap. If queued/running, P4 remains in progress; if red, keep the old repository private, fix only the clean candidate lineage, verify locally, and update under an exact lease.

---

### Task 5: Amend P4 evidence, exact-lease final push, and completion audit

**Files:**
- Modify: `PROJECT_ROADMAP.md`
- Amend: third commit in the disposable clean repository; first two commits remain immutable.

**Interfaces:**
- Consumes: candidate CI URL/results, new/old repository IDs, independent-clone evidence, candidate public SHA.
- Produces: final three-commit public lineage, final green CI, completed P4 ledger, and P5 handoff.

- [ ] **Step 1: Write the completed P4 roadmap evidence in the source worktree**

Append evidence rows and replace active-session/handoff state with:

- P4-T1 completed, effort Ultra;
- old repository ID/name/private visibility;
- new repository ID/canonical public name;
- old remote SHA inventory and candidate cutover SHA;
- exact P2/P3 source and clean tree IDs;
- archive, forbidden-set, lineage-audit, full-suite, wheel-matrix, independent-clone counts;
- candidate hosted-CI run ID/URL and 3/3 successful jobs;
- rollback not invoked, or exact rollback/fix history if it was;
- exactly one next task: `P5-T1 — Frozen benchmark protocol and gold-label packet`.

Do not claim scientific or benchmark success. Run public-tree audit, roadmap parser/session tests, and `git diff --check`, then commit the source roadmap update. This source commit is an assembly input; its contaminated ancestry is never pushed.

- [ ] **Step 2: Amend only the third clean commit**

Use `reconstruct_public_lineage.py amend` with the updated source `HEAD`. Require:

- clean commits 1 and 2 unchanged;
- exactly three commits total;
- third tree exactly equals updated source `HEAD^{tree}`;
- third commit SHA changes from candidate SHA;
- expected-tip/policy-bound lineage audit PASS with fresh JSON evidence and matching policy counts/digests;
- complete local verification bundle and clean status PASS.

- [ ] **Step 3: Force-update public main under the candidate exact lease**

Recheck the canonical repository ID and current remote `main`, require nonempty candidate/final SHAs, then push only:

```bash
git -C "$CANDIDATE" push --no-follow-tags \
  --force-with-lease="refs/heads/main:$CANDIDATE_SHA" \
  "$CANONICAL_URL" refs/heads/main:refs/heads/main
```

Abort without retry if the lease fails. Verify public `main` equals the amended SHA and still advertises no other refs.

- [ ] **Step 4: Require final hosted CI on the amended SHA**

Locate the push run whose `headSha` equals the amended final SHA and poll to completion. Require all three Python jobs successful. The roadmap contains the candidate proof run because a commit cannot contain the URL of the run created by its own push; this final run is the authoritative external proof for the amended public tip and must be reported in the session handoff/final response.

- [ ] **Step 5: Run the final independent public-clone audit**

From a new clone after final CI:

- prove new canonical repository ID;
- prove only `HEAD` and `refs/heads/main` advertised;
- prove old tags/branches/pull ref absent;
- prove exactly three commits and P2/P3 tree parity;
- run expected-tip/policy-bound lineage audit with private forbidden sets, fresh JSON evidence, and matching policy counts/digests;
- run `git fsck --full --strict`;
- run full test/check/public/hardening/Vigil bundle;
- build one wheel and pass installed operation on Python 3.10, 3.11, and 3.12;
- require clean status.

- [ ] **Step 6: Reverify preservation and source cleanliness**

Run the sealed archive verifier again and require the same manifest/ref/corpus counts and zero credential findings. Verify old repository ID `1269879110` remains private at the archival name. Verify the source P4 worktree is clean; generated local evidence remains outside Git.

- [ ] **Step 7: Completion review and goal close**

Check every acceptance item in the P4 spec against current remote/local evidence. P4 is not complete if any remote ref is uncertain, any final CI job is missing/red, any audit is indirect, or either working tree is dirty. When all items are proved, record final public SHA, new repository ID, candidate and final CI URLs in the completion report and mark the active goal complete.
