#!/usr/bin/env python3
"""Backward-compatible entry point for artifact validation."""

from __future__ import annotations

import sys
from pathlib import Path
from runpy import run_path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    target = repo_root / "athanasor" / "scripts" / "validate.py"
    try:
        run_path(str(target), run_name="__main__")
    except SystemExit as exc:
        return int(exc.code if isinstance(exc.code, int) else 0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
