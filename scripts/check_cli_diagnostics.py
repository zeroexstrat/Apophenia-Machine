#!/usr/bin/env python3
"""Regression check that CLI smoke failures include subprocess diagnostics."""

from __future__ import annotations

import contextlib
import importlib.util
import io
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECK_CLI_PATH = ROOT / "scripts" / "check_cli.py"


def _load_check_cli():
    spec = importlib.util.spec_from_file_location("check_cli_under_test", CHECK_CLI_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {CHECK_CLI_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = _load_check_cli()
    original_run = module._run

    def fake_run(argv, *, expect_json=False):
        return (
            1,
            "",
            "Traceback (most recent call last):\n"
            "  File \"athanasor/skills/exhaust.py\", line 537\n"
            "SyntaxError: f-string expression part cannot include a backslash\n",
        )

    module._run = fake_run
    try:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            rc = module.main()
    finally:
        module._run = original_run

    output = stream.getvalue()
    if rc != 1:
        print(f"[fail] expected check_cli main to fail, got rc={rc}")
        return 1
    if "SyntaxError: f-string expression part cannot include a backslash" not in output:
        print("[fail] subprocess stderr was not shown in failure diagnostics")
        print(output)
        return 1
    if "python -m athanasor.cli --help" not in output:
        print("[fail] failed command was not shown in failure diagnostics")
        print(output)
        return 1
    print("[ok] CLI smoke failures include command and stderr diagnostics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
