#!/usr/bin/env python3
"""Entry point for the `/concludere` session skill."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from athanasor.session.commands import run_concludere


def main() -> int:
    return run_concludere(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())

