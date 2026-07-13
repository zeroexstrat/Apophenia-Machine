# Durable Worktree Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development and superpowers:verification-before-completion. Execute inline; do not delegate this incident recovery.

**Goal:** Prevent an authoritative Azoth session from starting in purgeable temporary storage and preserve recovered P7 Git history independently.

**Architecture:** Put path classification and fail-closed validation in `athanasor/session/durability.py`. Call it at the start of `/incipere`, expose it through `scripts/check_durable_worktree.py`, and document the durable-clone plus remote-and-bundle operating rule.

**Tech Stack:** Python 3.10+, pathlib, pytest, Git.

## Global Constraints

- `/private/tmp`, `/tmp`, `/var/tmp`, and the platform temporary directory are verification-only.
- `/incipere` has no temporary-path bypass.
- Resolve aliases before comparing paths.
- Keep private bundle paths and benchmark artifacts out of public Git.

### Task 1: Guard contract

**Files:** Create `tests/test_session_durability.py`; create `athanasor/session/durability.py`.

- [ ] Write tests proving durable paths pass and temporary or symlinked paths fail with actionable diagnostics.
- [ ] Run the tests and confirm failure because the module is absent.
- [ ] Implement `temporary_root_for(path, roots=None)` and `assert_durable_worktree(path, roots=None)`.
- [ ] Run the focused tests and confirm they pass.

### Task 2: Session and CLI integration

**Files:** Modify `athanasor/session/commands.py`; create `scripts/check_durable_worktree.py`; modify `tests/test_session_commands.py`.

- [ ] Write a failing test proving `/incipere` checks durability before Git initialization.
- [ ] Call `assert_durable_worktree(ROOT)` before `ensure_git_worktree(ROOT)`.
- [ ] Add a standalone script returning exit code 1 with the same diagnostic.
- [ ] Run session tests and the standalone durable-path check.

### Task 3: Operating policy and persistence

**Files:** Modify `AGENTS.md` and `USER_GUIDE.md`; create a private bundle outside the repository.

- [ ] Document temporary paths as disposable verification surfaces only.
- [ ] Require an early remote checkpoint and a verified private bundle for long-running milestone work.
- [ ] Push the branch, create the bundle with mode `0600`, run `git bundle verify`, and compare the remote SHA.
- [ ] Run the full test and audit gates before claiming recovery complete.

