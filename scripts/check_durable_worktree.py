#!/usr/bin/env python3
"""Reject authoritative worktrees located in purgeable temporary storage."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from athanasor.session.durability import assert_durable_worktree


def _git_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError("not inside a Git worktree")
    return Path(result.stdout.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="Repository root; defaults to the current Git root")
    args = parser.parse_args(argv)

    try:
        root = assert_durable_worktree(args.root or _git_root())
    except RuntimeError as exc:
        print(f"durable-worktree check failed: {exc}")
        return 1

    print(f"durable-worktree check passed: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

