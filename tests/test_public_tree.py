"""Public checkout must remain independent of private operator runtime data."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.check_public_tree import audit_paths, audit_repository


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_audit_rejects_runtime_paths_private_content_and_pdfs() -> None:
    blobs = {
        "albedo/registry.jsonl": b"{}\n",
        "README.md": b"source: /Users/example/private.pdf\n",
        "paper.pdf": b"%PDF-1.7",
    }

    findings = audit_paths(sorted(blobs), blobs.__getitem__)

    assert any("tracked runtime artifact" in item for item in findings)
    assert any("absolute user path" in item for item in findings)
    assert any("tracked PDF" in item for item in findings)


def test_audit_rejects_pilot_identifiers_and_fallback_dumps() -> None:
    blobs = {
        "notes.md": b"candidate orcid0000000248120744_123456789",
        "snapshot.json": b'{"tags": ["ingested", "fallback"]}\n',
    }

    findings = audit_paths(sorted(blobs), blobs.__getitem__)

    assert any("pilot identifier" in item for item in findings)
    assert any("fallback runtime dump" in item for item in findings)


def test_audit_allows_code_schemas_and_synthetic_examples() -> None:
    blobs = {
        "athanasor/cli.py": b"print('ok')\n",
        "CONNECT_SCHEMA.yaml": b"schema_version: {type: integer}\n",
        "examples/synthetic-agent-input/connections.json": b"[]\n",
    }

    assert audit_paths(sorted(blobs), blobs.__getitem__) == []


def test_live_tracked_tree_passes_public_audit() -> None:
    assert audit_repository() == []


def test_generated_uv_lockfile_is_ignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "uv.lock"],
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0
