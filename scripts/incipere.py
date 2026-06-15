#!/usr/bin/env python3
"""Entry point for the `/incipere` session skill."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from athanasor.session.commands import run_incipere


def main() -> int:
    return run_incipere(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())

