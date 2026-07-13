from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest
import yaml

from athanasor.benchmark.protocol import LANES, load_mapping, validate_blinded_packet
from tests.benchmark_fixtures import (
    run_check,
    write_frozen_bundle,
    write_valid_public_bundle,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_ROOT = (
    REPO_ROOT / "benchmarks" / "operations-decision-support-v1" / "synthetic"
)


def test_public_audit_passes_without_private_gold(tmp_path: Path) -> None:
    root = write_valid_public_bundle(tmp_path)
    result = run_check("--benchmark-root", str(root), "--repo-root", str(tmp_path))
    assert result.returncode == 0
    assert "PASS mode=public" in result.stdout
    assert result.stderr == ""


def test_public_audit_accepts_live_pending_bundle() -> None:
    repo = Path(__file__).resolve().parents[1]
    root = repo / "benchmarks" / "operations-decision-support-v1"
    result = run_check("--benchmark-root", str(root), "--repo-root", str(repo))
    assert result.returncode == 0
    assert "PASS mode=public" in result.stdout


def test_private_audit_passes_with_exact_public_commitment(tmp_path: Path) -> None:
    root, gold, source_dir, repo = write_frozen_bundle(tmp_path)
    result = run_check(
        "--benchmark-root",
        str(root),
        "--private-gold",
        str(gold),
        "--source-dir",
        str(source_dir),
        "--repo-root",
        str(repo),
    )
    assert result.returncode == 0
    assert "PASS mode=public+private" in result.stdout


def test_private_audit_rejects_commitment_mismatch(tmp_path: Path) -> None:
    root, gold, source_dir, repo = write_frozen_bundle(tmp_path)
    payload = json.loads(gold.read_text(encoding="utf-8"))
    payload["gold_pairs"][0]["label"] = 3
    gold.write_text(json.dumps(payload), encoding="utf-8")
    result = run_check(
        "--benchmark-root",
        str(root),
        "--private-gold",
        str(gold),
        "--source-dir",
        str(source_dir),
        "--repo-root",
        str(repo),
    )
    assert result.returncode == 1
    assert "digest does not match" in result.stdout


def test_private_audit_requires_exact_commitment_object(tmp_path: Path) -> None:
    root, gold, source_dir, repo = write_frozen_bundle(tmp_path)
    freeze_path = root / "freeze-manifest.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    freeze["private_gold_commitment"]["freeze_time"] = "2026-01-01T00:00:00Z"
    freeze_path.write_text(json.dumps(freeze), encoding="utf-8")
    result = run_check(
        "--benchmark-root",
        str(root),
        "--private-gold",
        str(gold),
        "--source-dir",
        str(source_dir),
        "--repo-root",
        str(repo),
    )
    assert result.returncode == 1
    assert "digest does not match" in result.stdout


@pytest.mark.parametrize("provided", ["private-gold", "source-dir"])
def test_private_inputs_must_be_paired(tmp_path: Path, provided: str) -> None:
    root = write_valid_public_bundle(tmp_path)
    private = tmp_path.parent / f"{tmp_path.name}-outside"
    private.mkdir()
    arguments = ["--benchmark-root", str(root), "--repo-root", str(tmp_path)]
    arguments.extend([f"--{provided}", str(private)])
    result = run_check(*arguments)
    assert result.returncode == 2
    assert "must be provided together" in result.stdout


@pytest.mark.parametrize("private_option", ["--private-gold", "--source-dir"])
def test_private_inputs_must_be_outside_repository(
    tmp_path: Path, private_option: str
) -> None:
    root, gold, source_dir, repo = write_frozen_bundle(tmp_path)
    unsafe = repo / ("gold.json" if private_option == "--private-gold" else "sources")
    arguments = [
        "--benchmark-root",
        str(root),
        "--private-gold",
        str(gold),
        "--source-dir",
        str(source_dir),
        "--repo-root",
        str(repo),
    ]
    arguments[arguments.index(private_option) + 1] = str(unsafe)
    result = run_check(*arguments)
    assert result.returncode == 2
    assert "outside the repository" in result.stdout


def test_unreadable_input_returns_exit_two(tmp_path: Path) -> None:
    missing = tmp_path / "missing-benchmark"
    result = run_check(
        "--benchmark-root", str(missing), "--repo-root", str(tmp_path)
    )
    assert result.returncode == 2
    assert "Benchmark protocol audit: ERROR:" in result.stdout


def test_validation_findings_are_sorted_and_deterministic(tmp_path: Path) -> None:
    root = write_valid_public_bundle(tmp_path)
    sources_path = root / "sources.yaml"
    sources = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
    del sources["sources"][0]["title"]
    del sources["sources"][1]["authors"]
    sources_path.write_text(yaml.safe_dump(sources, sort_keys=False), encoding="utf-8")

    arguments = ("--benchmark-root", str(root), "--repo-root", str(tmp_path))
    first = run_check(*arguments)
    second = run_check(*arguments)
    assert first.returncode == second.returncode == 1
    assert first.stdout == second.stdout
    diagnostics = [line for line in first.stdout.splitlines() if line.startswith("- ")]
    assert diagnostics == sorted(diagnostics)


def test_synthetic_sources_are_six_new_fictional_records_balanced_by_lane() -> None:
    payload = load_mapping(SYNTHETIC_ROOT / "sources.yaml")
    sources = payload["sources"]
    assert payload["provenance"] == "newly_authored_fictional_synthetic_sources"
    assert len(sources) == 6
    assert len({source["paper_id"] for source in sources}) == 6
    assert Counter(source["lane"] for source in sources) == Counter(
        {lane: 2 for lane in LANES}
    )
    for source in sources:
        assert source["synthetic"] is True
        for field in ("title", "paper_id", "stable_identifier", "hash_provenance"):
            assert "synthetic" in source[field].casefold()
        assert all("synthetic" in claim.casefold() for claim in source["claims"])
        assert all("synthetic" in evidence.casefold() for evidence in source["evidence"])
        assert source["sha256"] == hashlib.sha256(
            source["source_text"].encode("utf-8")
        ).hexdigest()


def test_synthetic_blinded_packet_contains_only_generation_visible_fields() -> None:
    packet = load_mapping(SYNTHETIC_ROOT / "blinded-packet.json")
    schema = load_mapping(
        REPO_ROOT
        / "benchmarks"
        / "operations-decision-support-v1"
        / "blinded-packet-schema.yaml"
    )
    assert validate_blinded_packet(packet) == []
    assert set(packet) == set(schema["required_top_level_fields"])
    assert set(packet).issubset(schema["allowed_fields"]["packet"])
    assert packet["status"] == "pending_review"
    assert len(packet["sources"]) == 2
    source_allowed = set(schema["allowed_fields"]["source_identity"])
    source_allowed.update(schema["allowed_fields"]["bibliographic_metadata"])
    source_allowed.update(schema["allowed_fields"]["source_record"])
    assert all(set(source).issubset(source_allowed) for source in packet["sources"])

    statuses: list[str] = []

    def collect_statuses(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "status":
                    statuses.append(child)
                collect_statuses(child)
        elif isinstance(value, list):
            for child in value:
                collect_statuses(child)

    collect_statuses(packet)
    assert statuses == ["pending_review"]
