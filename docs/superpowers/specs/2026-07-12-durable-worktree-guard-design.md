# Durable Worktree Guard Design

## Incident

P7's only Git branch lived in `/private/tmp`. macOS purged that temporary clone before the branch was pushed or bundled. The benchmark artifacts survived elsewhere, but the Git objects did not.

## Decision

Authoritative Azoth sessions fail closed when the repository root resolves beneath a known temporary-storage root. `/incipere` performs this check before initializing Git or reading project state. Temporary directories remain valid only for disposable clone, wheel, and clean-install verification that does not invoke `/incipere`.

The guard is a small package function with an explicit temporary-root input for deterministic tests, plus a standalone check script for operators and automation. Path comparison uses resolved paths so macOS aliases such as `/tmp` and `/private/tmp` cannot bypass it.

Recovery durability has two independent anchors: the feature branch is pushed to `origin`, and a verified private Git bundle is stored under the existing mode-`0700` P7 archive. The active clone lives under `~/Desktop`, never under a temporary root.

## Failure behavior

The guard reports the resolved repository root, the matched temporary root, and the required remediation. There is no bypass flag on `/incipere`; verification jobs do not need to begin an authoritative session.

## Verification

- A durable Desktop-style path passes.
- `/tmp`, `/private/tmp`, `/var/tmp`, and the platform temporary root fail.
- Symlink-resolved aliases fail.
- `/incipere` checks durability before it can initialize a repository.
- The standalone script returns nonzero for a temporary root.
- Existing session and full test suites remain green.

