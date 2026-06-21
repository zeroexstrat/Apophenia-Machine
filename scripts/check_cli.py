#!/usr/bin/env python3
"""Small machine checks for stable CLI surface."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def _command_text(argv: list[str]) -> str:
    return " ".join(["python", "-m", "athanasor.cli", *argv])


def _record_diagnostic(
    diagnostics: list[tuple[list[str], int, str, str]],
    argv: list[str],
    rc: int,
    stdout: str,
    stderr: str,
) -> None:
    if rc != 0:
        diagnostics.append((argv, rc, stdout, stderr))


def _print_diagnostics(diagnostics: list[tuple[list[str], int, str, str]]) -> None:
    if not diagnostics:
        return

    print("\nCommand diagnostics:")
    seen: set[tuple[int, str, str]] = set()
    printed = 0
    for argv, rc, stdout, stderr in diagnostics:
        key = (rc, stdout, stderr)
        if key in seen:
            continue
        seen.add(key)
        printed += 1
        print(f"\n$ {_command_text(argv)}")
        print(f"exit code: {rc}")
        if stdout.strip():
            print("stdout:")
            print(stdout.rstrip())
        if stderr.strip():
            print("stderr:")
            print(stderr.rstrip())

    suppressed = len(diagnostics) - printed
    if suppressed:
        print(f"\nSuppressed {suppressed} duplicate failing command diagnostic(s).")


def _run(argv: list[str], *, expect_json: bool = False) -> tuple[int, str, str]:
    proc = subprocess.run(
        [PYTHON, "-m", "athanasor.cli", *argv],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    output = proc.stdout + proc.stderr
    if expect_json:
        try:
            json.loads(proc.stdout.strip() or "{}")
        except json.JSONDecodeError as exc:
            return 2, output, str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def _assert(condition: bool, label: str, failures: list[str]) -> None:
    if condition:
        print(f"[ok] {label}")
    else:
        failures.append(label)
        print(f"[fail] {label}")


def main() -> int:
    failures: list[str] = []
    diagnostics: list[tuple[list[str], int, str, str]] = []
    print("Running Azoth CLI smoke checks...")

    rc, out, err = _run(["--help"])
    _record_diagnostic(diagnostics, ["--help"], rc, out, err)
    _assert(rc == 0, "azoth --help exits 0", failures)
    help_text = out + err
    for token in [
        "ingest",
        "awaken",
        "exhaust",
        "status",
        "connect",
        "detect",
        "draft",
        "triage",
        "review",
        "experiment",
        "promote",
        "ouroboros",
        "validate",
        "migrate",
        "config",
    ]:
        _assert(token in help_text, f"command listed in --help: {token}", failures)

    help_outputs: dict[str, str] = {}
    for command in [
        "awaken",
        "status",
        "connect",
        "detect",
        "draft",
        "triage",
        "review",
        "experiment",
        "promote",
        "ouroboros",
        "config",
        "migrate",
    ]:
        rc, sub_out, sub_err = _run([command, "--help"])
        _record_diagnostic(diagnostics, [command, "--help"], rc, sub_out, sub_err)
        _assert(rc == 0, f"{command} --help works", failures)
        _assert(len(sub_out.strip()) > 0, f"{command} --help has output", failures)
        help_outputs[command] = sub_out

    _assert(
        "--reanalyze-depth-upgrades" in help_outputs.get("connect", ""),
        "connect --help lists depth-upgrade reanalysis flag",
        failures,
    )

    rc, status_out, status_err = _run(["status", "--json"])
    _record_diagnostic(diagnostics, ["status", "--json"], rc, status_out, status_err)
    _assert(rc == 0, "status --json runs", failures)
    if rc == 0:
        payload = json.loads(status_out or "{}")
        _assert(isinstance(payload, dict), "status --json returns JSON object", failures)
        _assert("status_counts" in payload, "status payload contains status_counts", failures)
        _assert("domain_counts" in payload, "status payload contains domain_counts", failures)

    rc, config_out, config_err = _run(["config", "--show"])
    _record_diagnostic(diagnostics, ["config", "--show"], rc, config_out, config_err)
    _assert(rc == 0, "config --show runs", failures)
    if rc == 0 and config_out.strip():
        payload = json.loads(config_out)
        _assert("llm" in payload, "config payload contains llm", failures)
        _assert("paths" in payload, "config payload contains paths", failures)

    if failures:
        print("\nFailed checks:")
        for item in failures:
            print(f" - {item}")
        _print_diagnostics(diagnostics)
        return 1

    print("\nAll CLI smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
