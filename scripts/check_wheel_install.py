#!/usr/bin/env python3
"""Prove Azoth wheel and source artifacts operate outside the checkout."""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

import yaml


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
FROZEN_METRICS = (
    "macro_f1",
    "unsafe_ood_assignment",
    "claim_precision",
    "reference_recall",
    "candidate_recall",
    "workload_reduction",
    "precision_at_5",
    "ndcg_at_10",
    "evidence_support",
    "supported_items",
    "useful_items",
    "redundancy",
    "unsupported_derived_items",
)


class SmokeFailure(RuntimeError):
    """One installed-wheel acceptance check failed."""


def resolve_artifact(pattern: str, *, label: str = "artifact") -> Path:
    matches = sorted(Path(path).resolve() for path in glob.glob(pattern))
    if len(matches) != 1:
        raise SmokeFailure(
            f"Expected exactly one {label} for {pattern!r}; found {len(matches)}"
        )
    return matches[0]


def resolve_wheel(pattern: str) -> Path:
    """Backward-compatible wheel-specific artifact resolver."""
    return resolve_artifact(pattern, label="wheel")


def inspect_wheel(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    return [name for name in REQUIRED_WHEEL_RESOURCES if name not in names]


def inspect_sdist(sdist: Path) -> list[str]:
    with tarfile.open(sdist, "r:gz") as archive:
        names = {
            name.split("/", 1)[1]
            for name in archive.getnames()
            if "/" in name
        }
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


def _pair_identifier(first: str, second: str) -> str:
    encoded = json.dumps(
        sorted((first, second)), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"pair_{hashlib.sha256(encoded).hexdigest()[:16]}"


def run_version(
    artifact: Path,
    python_version: str,
    *,
    expected_version: str,
    keep_temp: bool = False,
) -> Path | None:
    uv = shutil.which("uv")
    if not uv:
        raise SmokeFailure("uv is required for multi-interpreter artifact smoke checks")

    kind = "wheel" if artifact.suffix == ".whl" else "sdist"
    temp_path = Path(
        tempfile.mkdtemp(
            prefix=f"azoth-{kind}-py{python_version.replace('.', '')}-"
        )
    )
    env = _clean_environment()
    try:
        venv = temp_path / "venv"
        outside = temp_path / "outside"
        workspace = temp_path / "workspace"
        outside.mkdir()

        _run([uv, "venv", "--python", python_version, str(venv)], cwd=outside, env=env)
        python = _venv_python(venv)
        _run(
            [uv, "pip", "install", "--python", str(python), str(artifact)],
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

        version_probe = _run(
            [
                str(python),
                "-c",
                "import importlib.metadata; print(importlib.metadata.version('azoth'))",
            ],
            cwd=outside,
            env=env,
        )
        installed_version = version_probe.stdout.strip()
        if installed_version != expected_version:
            raise SmokeFailure(
                f"Python {python_version} installed version {installed_version!r}, "
                f"expected {expected_version!r}"
            )

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
        _run(
            [str(python), "-m", "athanasor.cli", "benchmark", "--help"],
            cwd=outside,
            env=env,
        )
        benchmark_root = outside / "benchmark"
        shutil.copytree(
            REPO_ROOT / "benchmarks" / "operations-decision-support-v1",
            benchmark_root,
        )
        notice = "SYNTHETIC CONTRACT TEST — NOT A PERFORMANCE CLAIM"
        lock_root = outside / "p7-lock"
        runs_root = lock_root / "runs"
        runs_root.mkdir(parents=True)
        prepared_path = lock_root / "prepared.json"
        paper_ids = [f"paper_{index:016x}" for index in range(1, 7)]
        packets = []
        for first_index, first in enumerate(paper_ids):
            for second in paper_ids[first_index + 1 :]:
                pair = _pair_identifier(first, second)
                packets.append(
                    {
                        "schema_version": 1,
                        "benchmark_id": "operations-decision-support-v1",
                        "packet_id": f"packet_{pair.split('_', 1)[1]}",
                        "pair_id": pair,
                        "paper_a_id": first,
                        "paper_b_id": second,
                        "sources": [
                            {
                                "paper_id": first,
                                "claims": [f"Synthetic installed-wheel claim {first}."],
                                "tags": ["synthetic"],
                            },
                            {
                                "paper_id": second,
                                "claims": [f"Synthetic installed-wheel claim {second}."],
                                "tags": ["synthetic"],
                            },
                        ],
                        "status": "pending_review",
                    }
                )
        execution_manifest_path = benchmark_root / "execution-manifest.yaml"
        execution_manifest = yaml.safe_load(execution_manifest_path.read_text(encoding="utf-8"))
        public_contracts = execution_manifest["public_contracts"]
        prepared = {
            "schema_version": 1,
            "artifact_type": "azoth_benchmark_prepared",
            "benchmark_id": "operations-decision-support-v1",
            "synthetic": True,
            "notice": notice,
            "provenance": {
                "source_manifest_sha256": "1" * 64,
                "frozen_source_manifest_sha256": public_contracts["source_manifest_sha256"],
                "protocol_sha256": public_contracts["protocol_sha256"],
                "prompt_sha256": public_contracts["prompt_sha256"],
                "blinded_schema_sha256": public_contracts["blinded_schema_sha256"],
                "freeze_manifest_sha256": public_contracts["freeze_manifest_sha256"],
            },
            "packets": packets,
            "status": "prepared",
        }
        prepared_path.write_text(
            json.dumps(prepared, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        _run(
            [
                str(python),
                "-m",
                "athanasor.cli",
                "benchmark",
                "validate",
                "--benchmark-root",
                str(benchmark_root),
                "--artifact",
                str(prepared_path),
            ],
            cwd=outside,
            env=env,
        )
        run_path = outside / "p6-run.json"
        _run(
            [
                str(python),
                "-m",
                "athanasor.cli",
                "benchmark",
                "run",
                "--prepared",
                str(prepared_path),
                "--output",
                str(run_path),
            ],
            cwd=outside,
            env=env,
        )
        run_ids = [row["run_id"] for row in execution_manifest["runs"]]
        baseline_ids = run_ids[1:]
        run_paths: dict[str, Path] = {}
        for run_id in baseline_ids:
            baseline_path = runs_root / f"{run_id}.json"
            _run(
                [
                    str(python),
                    "-m",
                    "athanasor.cli",
                    "benchmark",
                    "baseline",
                    "--prepared",
                    str(prepared_path),
                    "--execution-manifest",
                    str(execution_manifest_path),
                    "--run-id",
                    run_id,
                    "--output",
                    str(baseline_path),
                    "--repo-root",
                    str(workspace),
                ],
                cwd=outside,
                env=env,
            )
            run_paths[run_id] = baseline_path

        responses_root = outside / "model-responses"
        responses_root.mkdir()
        for packet in packets:
            first, second = packet["sources"]
            response = {
                "pair_id": packet["pair_id"],
                "paper_a_id": packet["paper_a_id"],
                "paper_b_id": packet["paper_b_id"],
                "predicted_label": 2,
                "structural_relation": {
                    "assessment": "Synthetic installed-wheel structural assessment.",
                    "shared_structure": "Both fictional records expose a bounded decision.",
                    "transferable_implication": "Compare the fictional decision rules.",
                    "evidence": [
                        {
                            "paper_id": first["paper_id"],
                            "visible_field": "claims",
                            "excerpt_or_paraphrase": first["claims"][0],
                        },
                        {
                            "paper_id": second["paper_id"],
                            "visible_field": "claims",
                            "excerpt_or_paraphrase": second["claims"][0],
                        },
                    ],
                    "caveats": ["Synthetic installed-wheel contract only."],
                },
                "status": "pending_review",
            }
            (responses_root / f"{packet['pair_id']}.json").write_text(
                json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
        provenance_path = outside / "model-provenance.json"
        provenance_path.write_text(
            json.dumps(
                {
                    "client": "installed-wheel-smoke",
                    "execution_surface": "isolated wheel test",
                    "task_id": f"wheel-smoke-py{python_version}",
                    "declared_backend_label": "5.6 Sol",
                    "provider_model_identity": None,
                    "provider_model_identity_verified": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        model_run_path = runs_root / "model_5_6_sol.json"
        _run(
            [
                str(python),
                "-m",
                "athanasor.cli",
                "benchmark",
                "adapt",
                "--prepared",
                str(prepared_path),
                "--execution-manifest",
                str(execution_manifest_path),
                "--responses-dir",
                str(responses_root),
                "--provenance",
                str(provenance_path),
                "--output",
                str(model_run_path),
                "--repo-root",
                str(workspace),
            ],
            cwd=outside,
            env=env,
        )
        run_paths["model_5_6_sol"] = model_run_path

        implementation_sha = "a" * 40
        lock_path = lock_root / "lock-manifest.json"
        lock_command = [
            str(python),
            "-m",
            "athanasor.cli",
            "benchmark",
            "lock",
            "--benchmark-root",
            str(benchmark_root),
            "--prepared",
            str(prepared_path),
            "--execution-manifest",
            str(execution_manifest_path),
        ]
        for run_id in run_ids:
            lock_command.extend(["--run", f"{run_id}={run_paths[run_id]}"])
        lock_command.extend(
            [
                "--output",
                str(lock_path),
                "--repo-root",
                str(workspace),
                "--implementation-git-sha",
                implementation_sha,
            ]
        )
        _run(lock_command, cwd=outside, env=env)

        evaluation_root = outside / "evaluation"
        evaluation_root.mkdir()
        annotations_path = evaluation_root / "annotations.json"
        _run(
            [
                str(python),
                "-m",
                "athanasor.cli",
                "benchmark",
                "annotations",
                "--benchmark-root",
                str(benchmark_root),
                "--run",
                str(model_run_path),
                "--lock",
                str(lock_path),
                "--output",
                str(annotations_path),
                "--repo-root",
                str(workspace),
                "--expected-git-sha",
                implementation_sha,
            ],
            cwd=outside,
            env=env,
        )
        annotations = json.loads(annotations_path.read_text(encoding="utf-8"))
        for field in ("claims", "evidence_spans", "items"):
            for row in annotations[field]:
                if field == "items":
                    row.update({"supported": True, "useful": True, "redundant": False})
                else:
                    row["supported"] = True
                row["rationale"] = "Synthetic installed-wheel annotation."
        annotations["status"] = "completed"
        annotations_path.write_text(
            json.dumps(annotations, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

        model_run = json.loads(model_run_path.read_text(encoding="utf-8"))
        gold = {
            "schema_version": 1,
            "artifact_type": "azoth_synthetic_gold",
            "benchmark_id": "operations-decision-support-v1",
            "synthetic": True,
            "notice": notice,
            "gold_pairs": [
                {
                    "pair_id": row["pair_id"],
                    "paper_a_id": row["paper_a_id"],
                    "paper_b_id": row["paper_b_id"],
                    "label": index % 4,
                }
                for index, row in enumerate(model_run["results"])
            ],
            "freeze": {"freeze_time": "2026-07-12T00:00:00Z"},
        }
        gold_path = evaluation_root / "gold.json"
        gold_path.write_text(
            json.dumps(gold, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        committed_gold = {
            "benchmark_id": gold["benchmark_id"],
            "artifact_type": gold["artifact_type"],
            "synthetic": True,
            "gold_pairs": sorted(gold["gold_pairs"], key=lambda row: row["pair_id"]),
            "freeze_time": gold["freeze"]["freeze_time"],
        }
        commitment = {
            "algorithm": "sha256-canonical-json-v1",
            "private_gold_sha256": hashlib.sha256(
                json.dumps(committed_gold, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "schema_version": 1,
            "freeze_time": gold["freeze"]["freeze_time"],
        }
        (benchmark_root / "synthetic" / "gold-commitment.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "artifact_type": "azoth_synthetic_gold_commitment",
                    "benchmark_id": "operations-decision-support-v1",
                    "synthetic": True,
                    "notice": notice,
                    "commitment": commitment,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

        score_paths: dict[str, Path] = {}
        for run_id in run_ids:
            score_path = evaluation_root / f"{run_id}-score.json"
            score_command = [
                str(python),
                "-m",
                "athanasor.cli",
                "benchmark",
                "score",
                "--benchmark-root",
                str(benchmark_root),
                "--run",
                str(run_paths[run_id]),
                "--gold",
                str(gold_path),
                "--output",
                str(score_path),
                "--repo-root",
                str(workspace),
                "--lock",
                str(lock_path),
                "--execution-manifest",
                str(execution_manifest_path),
                "--expected-git-sha",
                implementation_sha,
            ]
            if run_id == "model_5_6_sol":
                score_command.extend(["--annotations", str(annotations_path)])
            _run(score_command, cwd=outside, env=env)
            score_paths[run_id] = score_path

        report_path = evaluation_root / "model-report.md"
        _run(
            [
                str(python),
                "-m",
                "athanasor.cli",
                "benchmark",
                "report",
                "--score",
                str(score_paths["model_5_6_sol"]),
                "--output",
                str(report_path),
            ],
            cwd=outside,
            env=env,
        )
        if notice not in report_path.read_text(encoding="utf-8"):
            raise SmokeFailure(f"Python {python_version} benchmark report omitted synthetic notice")

        comparison_path = evaluation_root / "comparison.json"
        failure_path = evaluation_root / "failure.json"
        summary_path = evaluation_root / "public-summary.md"
        compare_command = [
            str(python),
            "-m",
            "athanasor.cli",
            "benchmark",
            "compare",
            "--lock",
            str(lock_path),
            "--output",
            str(comparison_path),
            "--repo-root",
            str(workspace),
        ]
        for run_id in run_ids:
            compare_command.extend(["--score", f"{run_id}={score_paths[run_id]}"])
            compare_command.extend(["--run", f"{run_id}={run_paths[run_id]}"])
        compare_command.extend(
            [
                "--gold",
                str(gold_path),
                "--annotations",
                str(annotations_path),
                "--failure-output",
                str(failure_path),
                "--public-summary-output",
                str(summary_path),
            ]
        )
        _run(compare_command, cwd=outside, env=env)
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

        print(f"[PASS] {artifact.name} on Python {python_version}: {workspace}")
        return temp_path if keep_temp else None
    finally:
        if not keep_temp:
            shutil.rmtree(temp_path, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, help="Exact wheel path or a quoted glob matching one wheel")
    parser.add_argument("--sdist", required=True, help="Exact sdist path or a quoted glob matching one source archive")
    parser.add_argument("--expected-version", required=True, help="Installed distribution version required from both artifacts")
    parser.add_argument("--python", action="append", dest="versions", required=True, help="Python version; repeatable")
    parser.add_argument("--keep-temp", action="store_true", help="Retain isolated environments for inspection")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        wheel = resolve_artifact(args.wheel, label="wheel")
        sdist = resolve_artifact(args.sdist, label="sdist")
        missing = inspect_wheel(wheel) + inspect_sdist(sdist)
        if missing:
            raise SmokeFailure(
                "Release artifact is missing resources: "
                + ", ".join(sorted(set(missing)))
            )
        retained: list[Path] = []
        for artifact in (wheel, sdist):
            for version in args.versions:
                path = run_version(
                    artifact,
                    version,
                    expected_version=args.expected_version,
                    keep_temp=args.keep_temp,
                )
                if path is not None:
                    retained.append(path)
    except (OSError, SmokeFailure, tarfile.TarError, zipfile.BadZipFile) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    for path in retained:
        print(f"Retained: {path}")
    print(
        "Installed-artifact smoke passed for "
        f"{2 * len(args.versions)} artifact/interpreter pair(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
