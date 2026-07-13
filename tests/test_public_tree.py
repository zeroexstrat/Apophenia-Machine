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


def test_audit_rejects_real_gold_and_source_archives() -> None:
    blobs = {
        "benchmarks/operations-decision-support-v1/gold.json": b'{"gold_pairs":[{"label":3}]}',
        "benchmarks/operations-decision-support-v1/source.txt": b"third-party paper body",
        "benchmarks/operations-decision-support-v1/source.zip": b"PK\x03\x04",
    }

    findings = audit_paths(sorted(blobs), blobs.__getitem__)

    assert any("benchmark gold material" in item for item in findings)
    assert any("benchmark source text" in item for item in findings)
    assert any("benchmark source archive" in item for item in findings)


def test_audit_rejects_gold_keys_outside_synthetic_fixtures() -> None:
    blobs = {
        "benchmarks/operations-decision-support-v1/annotations.yaml": (
            b"gold_label: 3\ngold_rationale: leaked\n"
        ),
    }

    findings = audit_paths(sorted(blobs), blobs.__getitem__)

    assert any("benchmark gold material" in item for item in findings)


def test_audit_rejects_private_packet_keys_outside_synthetic_fixtures() -> None:
    blobs = {
        "benchmarks/operations-decision-support-v1/annotations.yaml": (
            b"label: 3\nrationale: leaked\nevidence_spans: []\n"
        ),
    }

    findings = audit_paths(sorted(blobs), blobs.__getitem__)

    assert any("benchmark gold material" in item for item in findings)


def test_audit_rejects_rationale_only_outside_selection_log() -> None:
    path = "benchmarks/operations-decision-support-v1/annotations.json"
    blobs = {path: b'{"rationale":"private"}'}

    findings = audit_paths([path], blobs.__getitem__)

    assert any("benchmark gold material" in item for item in findings)


def test_audit_allows_synthetic_fixture_and_freeze_digest() -> None:
    blobs = {
        "benchmarks/operations-decision-support-v1/synthetic/blinded-packet.json": (
            b'{"status":"pending_review"}'
        ),
        "benchmarks/operations-decision-support-v1/freeze-manifest.json": (
            b'{"private_gold_sha256":"' + b"0" * 64 + b'"}'
        ),
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


def test_hardening_workflow_runs_public_benchmark_audit() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "hardening.yml").read_text(
        encoding="utf-8"
    )
    assert "Verify frozen benchmark protocol" in workflow
    assert (
        "python3 scripts/check_benchmark_protocol.py --benchmark-root "
        "benchmarks/operations-decision-support-v1 --repo-root ."
    ) in workflow
