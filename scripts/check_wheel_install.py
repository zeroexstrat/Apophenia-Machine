#!/usr/bin/env python3
"""Prove an Azoth wheel operates outside its source checkout."""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_WHEEL_RESOURCES = (
    "athanasor/resources/SCHEMA.yaml",
    "athanasor/resources/EXHAUST_SCHEMA.yaml",
    "athanasor/resources/RETRIEVAL_SCHEMA.yaml",
    "athanasor/resources/CONNECT_SCHEMA.yaml",
    "athanasor/resources/DETECT_SCHEMA.yaml",
    "athanasor/resources/azoth.config.yaml",
    "athanasor/resources/vigil/gates.yaml",
)


class SmokeFailure(RuntimeError):
    """One installed-wheel acceptance check failed."""


def resolve_wheel(pattern: str) -> Path:
    matches = sorted(Path(path).resolve() for path in glob.glob(pattern))
    if len(matches) != 1:
        raise SmokeFailure(
            f"Expected exactly one wheel for {pattern!r}; found {len(matches)}"
        )
    return matches[0]


def inspect_wheel(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    return [name for name in REQUIRED_WHEEL_RESOURCES if name not in names]


def _clean_environment() -> dict[str, str]:
    env = os.environ.copy()
    for name in (
        "PYTHONPATH",
        "VIRTUAL_ENV",
        "AZOTH_PROJECT_ROOT",
        "AZOTH_SKIP_VIGIL",
        "AZOTH_AUTO_CHECKPOINT",
    ):
        env.pop(name, None)
    env["PYTHONNOUSERSITE"] = "1"
    env["UV_PYTHON_DOWNLOADS"] = "automatic"
    return env


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        rendered = " ".join(command)
        output = (result.stdout + result.stderr).strip()
        raise SmokeFailure(
            f"Command failed with exit {result.returncode}: {rendered}\n{output or 'no output'}"
        )
    return result


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run_version(
    wheel: Path,
    python_version: str,
    *,
    keep_temp: bool = False,
) -> Path | None:
    uv = shutil.which("uv")
    if not uv:
        raise SmokeFailure("uv is required for multi-interpreter wheel smoke checks")

    temp_path = Path(tempfile.mkdtemp(prefix=f"azoth-wheel-py{python_version.replace('.', '')}-"))
    env = _clean_environment()
    try:
        venv = temp_path / "venv"
        outside = temp_path / "outside"
        workspace = temp_path / "workspace"
        outside.mkdir()

        _run([uv, "venv", "--python", python_version, str(venv)], cwd=outside, env=env)
        python = _venv_python(venv)
        _run(
            [uv, "pip", "install", "--python", str(python), str(wheel)],
            cwd=outside,
            env=env,
        )

        probe = _run(
            [
                str(python),
                "-c",
                (
                    "import athanasor,json,pathlib,sys;"
                    "print(json.dumps({'package':str(pathlib.Path(athanasor.__file__).resolve()),"
                    "'path':[str(pathlib.Path(p).resolve()) for p in sys.path if p]}))"
                ),
            ],
            cwd=outside,
            env=env,
        )
        payload = json.loads(probe.stdout)
        repo = REPO_ROOT.resolve()
        package_path = Path(payload["package"])
        if package_path.is_relative_to(repo):
            raise SmokeFailure(f"Python {python_version} imported Azoth from checkout: {package_path}")
        if any(Path(item).is_relative_to(repo) for item in payload["path"]):
            raise SmokeFailure(f"Python {python_version} sys.path contains checkout: {payload['path']}")

        _run([str(python), "-m", "athanasor.cli", "init", str(workspace)], cwd=outside, env=env)
        document = workspace / "nigredo" / "inbox" / "wheel-smoke.txt"
        document.write_text(
            "Wheel Resource Smoke Test\n\nAbstract\nA bounded synthetic claim verifies installed resource resolution.\n",
            encoding="utf-8",
        )
        _run([str(python), "-m", "athanasor.cli", "status"], cwd=workspace, env=env)
        _run(
            [str(python), "-m", "athanasor.cli", "ingest", str(document), "--no-llm"],
            cwd=workspace,
            env=env,
        )
        _run(
            [str(python), "-m", "athanasor.cli", "validate", "--all"],
            cwd=workspace,
            env=env,
        )
        for mode in ("start", "verify"):
            _run(
                [str(python), "-m", "athanasor.vigil.verify", mode],
                cwd=workspace,
                env=env,
            )

        if not list((workspace / "albedo" / "library").glob("*.yaml")):
            raise SmokeFailure(f"Python {python_version} ingest produced no library record")
        if not list((workspace / "athanasor" / "vigil" / "reports").glob("vigil_verify_*.json")):
            raise SmokeFailure(f"Python {python_version} Vigil wrote no workspace report")
        if not (workspace / "athanasor" / "lapis" / "memory.jsonl").is_file():
            raise SmokeFailure(f"Python {python_version} auto-checkpoint wrote no workspace memory")

        print(f"[PASS] Python {python_version}: {workspace}")
        return temp_path if keep_temp else None
    finally:
        if not keep_temp:
            shutil.rmtree(temp_path, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, help="Exact wheel path or a quoted glob matching one wheel")
    parser.add_argument("--python", action="append", dest="versions", required=True, help="Python version; repeatable")
    parser.add_argument("--keep-temp", action="store_true", help="Retain isolated environments for inspection")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        wheel = resolve_wheel(args.wheel)
        missing = inspect_wheel(wheel)
        if missing:
            raise SmokeFailure("Wheel is missing resources: " + ", ".join(missing))
        retained = [
            path
            for version in args.versions
            if (path := run_version(wheel, version, keep_temp=args.keep_temp)) is not None
        ]
    except (OSError, SmokeFailure, zipfile.BadZipFile) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    for path in retained:
        print(f"Retained: {path}")
    print(f"Installed-wheel smoke passed for {len(args.versions)} interpreter(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
