#!/usr/bin/env python3
"""Optional end-to-end smoke test for CLI + schema validation."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from athanasor.scripts.validate import validate_file
PYTHON = sys.executable


def _write_pdf(path: Path, body: str) -> None:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        lines = [""]

    safe_lines = [
        line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        for line in lines
    ]
    text_ops: list[str] = []
    for line in safe_lines:
        text_ops.append("0 -14 Td")
        text_ops.append(f"({line}) Tj")

    content = "\n".join(["/F1 11 Tf", "72 760 Td", *text_ops, "ET", ""] )
    content_stream = f"BT\n{content}"
    stream_len = len(content_stream.encode("utf-8"))

    pdf = f"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>
endobj
4 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
5 0 obj
<< /Length {stream_len} >>
stream
{content_stream}
endstream
endobj
xref
0 6
0000000000 65535 f 
0000000010 00000 n 
0000000079 00000 n 
0000000175 00000 n 
0000000301 00000 n 
0000000380 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
500
%%EOF
"""
    path.write_bytes(pdf.encode("utf-8"))


def _run_cmd(workdir: Path, args: list[str], env: dict[str, str]) -> list[Any]:
    proc = subprocess.run(
        [PYTHON, "-m", "athanasor.cli", *args],
        cwd=str(workdir),
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.stderr.strip() and not _stderr_is_allowed(proc.stderr):
        raise RuntimeError(
            "Command emitted stderr.\n"
            f"command: {' '.join(['python -m athanasor.cli', *args])}\n"
            f"stderr: {proc.stderr.strip()}"
        )
    if proc.returncode != 0:
        raise RuntimeError(
            "Command failed.\n"
            f"command: {' '.join(['python -m athanasor.cli', *args])}\n"
            f"status: {proc.returncode}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )

    try:
        return json.loads((proc.stdout or "").strip() or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Expected JSON output, got:\n{proc.stdout}") from exc


def _stderr_is_allowed(raw_stderr: str) -> bool:
    allowed_patterns = [
        r"^Warning: You are sending unauthenticated requests to the HF Hub\.",
        r"^\s*BertModel LOAD REPORT",
        r"^Key\s+\|\s+Status",
        r"^[- ]+UNEXPECTED:",
        r"^Notes:",
        r"^\s*\d+%\|",
        r"FutureWarning:",
    ]

    for line in raw_stderr.splitlines():
        line = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
        if not line:
            continue
        if not any(re.search(pattern, line) for pattern in allowed_patterns):
            return False
    return True


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                out.append(payload)
    return out


def _validate(path: Path, schema: Path) -> None:
    ok, errors, _ = validate_file(path, schema_path=schema, fix=False)
    if not ok:
        detail = "\n  - ".join(errors)
        raise RuntimeError(f"Schema validation failed for {path}\n  - {detail}")


def _int_in_range(value: object, min_value: int = 1, max_value: int = 5) -> int:
    try:
        as_int = int(value)
    except (TypeError, ValueError):
        raise RuntimeError(f"Expected integer confidence-like value, got {value!r}")
    if not (min_value <= as_int <= max_value):
        raise RuntimeError(f"Confidence out of range [1, 5]: {as_int}")
    return as_int


def _build_smoke_project(root: Path) -> None:
    # Copy runtime package and schema contracts so CLI modules can resolve imports.
    if (root / "athanasor").exists():
        shutil.rmtree(root / "athanasor")
    shutil.copytree(ROOT / "athanasor", root / "athanasor")

    for filename in [
        "SCHEMA.yaml",
        "EXHAUST_SCHEMA.yaml",
        "CONNECT_SCHEMA.yaml",
        "DETECT_SCHEMA.yaml",
    ]:
        shutil.copy(ROOT / filename, root / filename)

    # Keep fixtures inside the project root used by this smoke run.
    (root / "nigredo" / "inbox").mkdir(parents=True, exist_ok=True)
    (root / "nigredo" / "unclassified").mkdir(parents=True, exist_ok=True)
    (root / "albedo" / "library").mkdir(parents=True, exist_ok=True)
    (root / "albedo" / "exhaust").mkdir(parents=True, exist_ok=True)
    (root / "citrinitas" / "within_domain").mkdir(parents=True, exist_ok=True)
    (root / "citrinitas" / "cross_domain").mkdir(parents=True, exist_ok=True)
    (root / "rubedo" / "hypotheses").mkdir(parents=True, exist_ok=True)
    (root / "rubedo" / "drafts").mkdir(parents=True, exist_ok=True)

    # Use permissive similarities and a single-domain setup for deterministic smoke data.
    config = {
        "llm": {
            "base_url": "http://localhost:11434/v1",
            "model": "llama3.1:70b",
            "api_key": "ollama",
            "temperature": 0.3,
            "max_tokens": 4096,
        },
        "embeddings": {
            "model": "all-MiniLM-L6-v2",
            "store_path": "athanasor/embeddings.store",
            "similarity_threshold": 0.0,
            "redundancy_threshold": 0.0,
        },
        "paths": {
            "project_root": str(root),
            "nigredo": "nigredo",
            "albedo": "albedo",
            "citrinitas": "citrinitas",
            "rubedo": "rubedo",
            "athanasor": "athanasor",
        },
        "domains": ["unclassified", "physics", "ML", "philosophy", "neuroscience", "mathematics"],
        "exhaustion": {
            "depth_multipliers": {"1": 2, "2": 4, "3": 6, "4": 8, "5": 12},
            "batch_size": 2,
            "redundancy_stop_threshold": 3,
            "speculative_stop_count": 5,
        },
    }
    with open(root / "azoth.config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f)


def _assert_expected_connections(outputs: list[dict[str, Any]], confidence_min: int = 1) -> None:
    if not outputs:
        raise RuntimeError("No connection outputs were produced.")
    for item in outputs:
        _int_in_range(item.get("confidence"), min_value=confidence_min)
        _int_in_range(item.get("confidence_raw"), min_value=confidence_min)


def _assert_connection_report(project_root: Path) -> None:
    report_dir = project_root / "citrinitas" / "reports"
    if not report_dir.exists():
        raise RuntimeError("No connection reports directory was generated.")
    reports = sorted(report_dir.glob("connect_report_*.yaml"))
    if not reports:
        raise RuntimeError("No connection synthesis report generated.")

    if not reports[-1].exists():
        raise RuntimeError("Latest connection synthesis report missing on disk.")


def _assert_expected_hypotheses(outputs: list[dict[str, Any]]) -> None:
    if not outputs:
        raise RuntimeError("No hypotheses were produced.")
    for item in outputs:
        if not isinstance(item.get("gaps"), list) or not item["gaps"]:
            raise RuntimeError(f"Hypothesis missing gaps: {item.get('cluster_id')}")
        for gap in item["gaps"]:
            _int_in_range(gap.get("confidence"))
            _int_in_range(gap.get("feasibility"))


def run_smoke(project_root: Path) -> None:
    env = os.environ.copy()
    env["AZOTH_PROJECT_ROOT"] = str(project_root)
    env.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    env.setdefault("HF_HUB_VERBOSITY", "error")
    env.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    env.setdefault("TRANSFORMERS_VERBOSITY", "error")
    env.setdefault("PYTHONWARNINGS", "ignore")
    shared_text = (
        "This paper presents a minimal synthetic test fixture.\\n"
        "We present a simple pairwise relationship for deterministic extraction.\\n"
        "This paper studies structured data flow for a small synthetic benchmark.\\n"
    )

    inbox = project_root / "nigredo" / "inbox"
    for idx in range(3):
        _write_pdf(
            inbox / f"smoke_case_{idx + 1}.pdf",
            f"{shared_text}\\nPaper: smoke_case_{idx + 1}\\n",
        )

    ingest_outputs = _run_cmd(
        project_root,
        ["ingest", str(inbox), "--no-llm", "--json"],
        env=env,
    )
    if len(ingest_outputs) != 3:
        raise RuntimeError(f"Expected 3 ingested records, got {len(ingest_outputs)}")
    paper_ids = [str(entry["paper_id"]) for entry in ingest_outputs if isinstance(entry, dict)]
    if len(paper_ids) != 3:
        raise RuntimeError("Could not extract paper IDs from ingest output.")
    entries = _read_jsonl(project_root / "albedo" / "registry.jsonl")
    if len(entries) != 3:
        raise RuntimeError(f"Expected 3 registry entries after ingest, got {len(entries)}")
    if any(str(entry.get("status")) != "ingested_only" for entry in entries):
        raise RuntimeError("Found unexpected registry status during post-ingest phase.")
    if {entry.get("paper_id") for entry in entries} != set(paper_ids):
        raise RuntimeError("Registry does not contain expected ingested paper IDs.")

    exhaust_outputs = _run_cmd(
        project_root,
        ["awaken", "unclassified", "--no-llm", "--depth", "1", "--count", "3", "--json"],
        env=env,
    )
    if len(exhaust_outputs) != 3:
        raise RuntimeError(f"Expected 3 exhaustion outputs, got {len(exhaust_outputs)}")
    entries = _read_jsonl(project_root / "albedo" / "registry.jsonl")
    if any(str(entry.get("status")) != "exhausted" for entry in entries):
        raise RuntimeError("Found non-exhausted status after awaken phase.")
    for entry in entries:
        library_path = entry.get("paths", {}).get("library")
        exhaust_path = entry.get("paths", {}).get("exhaust")
        if not library_path:
            raise RuntimeError(f"Registry entry missing library path: {entry.get('paper_id')}")
        if not exhaust_path:
            raise RuntimeError(f"Registry entry missing exhaust path: {entry.get('paper_id')}")
        if not (project_root / library_path).exists():
            raise RuntimeError(f"Missing library artifact: {library_path}")
        if not (project_root / exhaust_path).exists():
            raise RuntimeError(f"Missing exhaust artifact: {exhaust_path}")

    connect_outputs = _run_cmd(
        project_root,
        ["connect", "--within", "unclassified", "--no-llm", "--json"],
        env=env,
    )
    _assert_expected_connections(connect_outputs, confidence_min=3)
    _assert_connection_report(project_root)

    detect_outputs = _run_cmd(
        project_root,
        ["detect", "--domain", "unclassified", "--no-llm", "--json"],
        env=env,
    )
    _assert_expected_hypotheses(detect_outputs)

    draft_outputs = _run_cmd(project_root, ["draft", "--top", "1", "--no-llm", "--json"], env=env)
    if len(draft_outputs) < 1:
        raise RuntimeError("Expected at least one draft output.")

    for paper_id in paper_ids:
        library_file = project_root / "albedo" / "library" / f"{paper_id}.yaml"
        _validate(library_file, ROOT / "SCHEMA.yaml")
        exhaust_file = project_root / "albedo" / "exhaust" / f"{paper_id}_exhaust.yaml"
        _validate(exhaust_file, ROOT / "EXHAUST_SCHEMA.yaml")

    for record in connect_outputs:
        _validate(Path(record["file"]), ROOT / "CONNECT_SCHEMA.yaml")

    for record in detect_outputs:
        cluster_id = str(record.get("cluster_id", "")).strip()
        if not cluster_id:
            raise RuntimeError("Detect output missing cluster_id.")
        _validate(
            project_root / "rubedo" / "hypotheses" / f"{cluster_id}.yaml",
            ROOT / "DETECT_SCHEMA.yaml",
        )

    for draft_path in draft_outputs:
        draft_file = project_root / str(draft_path)
        if not draft_file.exists():
            raise RuntimeError(f"Missing draft file: {draft_path}")

    for entry in _read_jsonl(project_root / "albedo" / "registry.jsonl"):
        if not entry.get("connected"):
            raise RuntimeError("Expected all entries marked connected after connect.")
        if not entry.get("detected"):
            raise RuntimeError("Expected all entries marked detected after detect.")
        if not entry.get("drafted"):
            raise RuntimeError("Expected all entries marked drafted after draft.")

    print("Pipeline smoke check passed.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a deterministic azoth pipeline smoke test.")
    parser.add_argument(
        "--workdir",
        type=Path,
        default=None,
        help="Optional explicit temporary project root (created and cleaned by default).",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep temporary workdir for inspection on success/failure.",
    )
    args = parser.parse_args()

    if args.workdir is not None:
        project_root = args.workdir.resolve()
        if project_root.exists() and any(project_root.iterdir()):
            raise RuntimeError(f"workdir must be empty: {project_root}")
        project_root.mkdir(parents=True, exist_ok=True)
        cleanup = False
    else:
        cleanup = True
        project_root = Path(tempfile.mkdtemp(prefix="azoth-smoke-"))

    try:
        _build_smoke_project(project_root)
        run_smoke(project_root)
    except Exception as exc:
        raise SystemExit(f"Hardening smoke check failed: {exc}") from exc
    finally:
        if cleanup:
            shutil.rmtree(project_root, ignore_errors=True)
        elif args.keep:
            print(f"Kept workspace at {project_root}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
