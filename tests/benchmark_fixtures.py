from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from athanasor.benchmark.freeze import gold_commitment
from athanasor.benchmark.protocol import (
    BLINDED_ALLOWED_FIELDS,
    BLINDED_FORBIDDEN_FIELDS,
    BLINDED_IDENTITY_CONTRACT,
    BLINDED_REQUIRED_EXPLICIT_CITATION_FIELDS,
    BLINDED_REQUIRED_SOURCE_FIELDS,
    BLINDED_REQUIRED_TOP_LEVEL_FIELDS,
    EXPECTED_P5_METRIC_CONTRACTS,
    LANES,
    paper_id,
)
from athanasor.benchmark.protocol import canonical_digest, canonical_json_bytes


def synthetic_source_bytes(stable_identifier: str, exact_version: str) -> bytes:
    return f"Synthetic source for {stable_identifier} at {exact_version}.\n".encode("utf-8")


def source_manifest_fixture() -> dict[str, Any]:
    sources = []
    for lane_index, lane in enumerate(LANES):
        for item_index in range(4):
            stable = f"doi:10.0000/synthetic.{lane_index}.{item_index}"
            version = "v1"
            source_bytes = synthetic_source_bytes(stable, version)
            download_url = f"https://example.invalid/download/{lane_index}/{item_index}"
            redirect_chain = [
                download_url,
                f"https://redirect.example.invalid/{lane_index}/{item_index}/first",
                f"https://redirect.example.invalid/{lane_index}/{item_index}/second",
                f"https://cdn.example.invalid/{lane_index}/{item_index}/source.pdf",
            ]
            sources.append(
                {
                    "paper_id": paper_id(stable, version),
                    "title": f"Synthetic decision paper {lane_index}-{item_index}",
                    "authors": ["Synthetic Author"],
                    "lane": lane,
                    "stable_identifier": stable,
                    "exact_version": version,
                    "publication_date": "2026-01-01",
                    "canonical_url": f"https://example.invalid/source/{lane_index}/{item_index}",
                    "download_url": download_url,
                    "access_date": "2026-07-11",
                    "sha256": hashlib.sha256(source_bytes).hexdigest(),
                    "license": "synthetic-test-only",
                    "license_evidence_url": "https://example.invalid/license",
                    "redistribution_status": "fetch_only",
                    "retrieval": {
                        "method": "https_get",
                        "redirect_policy": "record_exact_chain",
                        "redirect_chain": redirect_chain,
                        "final_url": redirect_chain[-1],
                    },
                    "source_text_quality": "born_digital_synthetic",
                }
            )
    return {
        "schema_version": 1,
        "benchmark_id": "operations-decision-support-v1",
        "sources": sources,
    }


def write_private_source_fixture(root: Path, payload: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for source in payload["sources"]:
        (root / f"{source['paper_id']}.pdf").write_bytes(
            synthetic_source_bytes(source["stable_identifier"], source["exact_version"])
        )
        (root / f"{source['paper_id']}.retrieval.json").write_text(
            json.dumps(
                {
                    "requested_url": source["download_url"],
                    "redirect_chain": source["retrieval"]["redirect_chain"],
                    "final_url": source["retrieval"]["final_url"],
                    "media_type": "application/pdf",
                    "access_date": source["access_date"],
                    "exact_version": source["exact_version"],
                    "license_evidence_url": source["license_evidence_url"],
                    "sha256": source["sha256"],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )


def protocol_fixture() -> dict[str, Any]:
    metrics = []
    for name, contract in EXPECTED_P5_METRIC_CONTRACTS.items():
        metric = {key: dict(value) if key == "threshold" else value for key, value in contract.items()}
        metrics.append({"name": name, **metric})
    return {
        "schema_version": 1,
        "benchmark_id": "operations-decision-support-v1",
        "rubric_version": "pair-relevance-v1",
        "rubric": {
            "scale": {0: "none", 1: "topical", 2: "structural", 3: "transferable"},
            "relevant_labels": [2, 3],
        },
        "adjudication": {
            "final_authority": "Rafael",
            "canonical_pair_count": 66,
            "presentation_seed": 5607,
            "repeated_anchor_count": 4,
        },
        "metrics": metrics,
        "no_retuning": True,
    }


def blinded_schema_fixture() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "benchmark_id": "operations-decision-support-v1",
        "artifact_type": "blinded_generation_packet_schema",
        "required_top_level_fields": list(BLINDED_REQUIRED_TOP_LEVEL_FIELDS),
        "required_source_fields": list(BLINDED_REQUIRED_SOURCE_FIELDS),
        "required_explicit_citation_fields": list(
            BLINDED_REQUIRED_EXPLICIT_CITATION_FIELDS
        ),
        "identity_contract": BLINDED_IDENTITY_CONTRACT,
        "allowed_fields": {
            group: list(fields) for group, fields in BLINDED_ALLOWED_FIELDS.items()
        },
        "forbidden_fields": sorted(BLINDED_FORBIDDEN_FIELDS),
        "status_contract": {
            "generation_input": "pending_review",
            "generation_output": "pending_review",
        },
        "unknown_fields": "reject",
    }


def completed_packet_fixture(*, inconsistent_anchor: bool = False) -> dict[str, Any]:
    from athanasor.benchmark.freeze import build_adjudication_packet

    packet = build_adjudication_packet(source_manifest_fixture(), protocol_fixture())
    seen: dict[str, int] = {}
    for presentation in packet["presentations"]:
        pair = presentation["pair_id"]
        seen[pair] = seen.get(pair, 0) + 1
        presentation["label"] = 2
        presentation["rationale"] = "Synthetic structural relation for contract testing."
        presentation["evidence_spans"] = [
            {"paper_role": "a", "text": "Synthetic evidence A."},
            {"paper_role": "b", "text": "Synthetic evidence B."},
        ]
        if inconsistent_anchor and pair in packet["anchor_pair_ids"] and seen[pair] == 2:
            presentation["label"] = 1
            break
    return packet


def reconciled_packet_fixture() -> dict[str, Any]:
    from athanasor.benchmark.freeze import reconcile_gold_packet

    return reconcile_gold_packet(
        completed_packet_fixture(), source_manifest_fixture(), protocol_fixture()
    )


def run_check(
    *arguments: str, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    root = Path(__file__).resolve().parents[1]
    return subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "check_benchmark_protocol.py"),
            *arguments,
        ],
        cwd=cwd or root,
        text=True,
        capture_output=True,
        check=False,
    )


def write_valid_public_bundle(root: Path) -> Path:
    benchmark = root / "benchmarks" / "operations-decision-support-v1"
    benchmark.mkdir(parents=True)
    sources = source_manifest_fixture()
    protocol = protocol_fixture()
    (benchmark / "sources.yaml").write_text(
        yaml.safe_dump(sources, sort_keys=False), encoding="utf-8"
    )
    (benchmark / "protocol.yaml").write_text(
        yaml.safe_dump(protocol, sort_keys=False), encoding="utf-8"
    )
    blinded_schema = blinded_schema_fixture()
    (benchmark / "blinded-packet-schema.yaml").write_text(
        yaml.safe_dump(blinded_schema, sort_keys=False), encoding="utf-8"
    )
    prompt_bytes = b"Synthetic frozen generation prompt.\n"
    (benchmark / "generation-prompt.md").write_bytes(prompt_bytes)
    (benchmark / "freeze-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "azoth_benchmark_freeze",
                "benchmark_id": "operations-decision-support-v1",
                "status": "frozen",
                "source_manifest_sha256": canonical_digest(sources),
                "protocol_sha256": canonical_digest(protocol),
                "prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
                "blinded_schema_sha256": canonical_digest(blinded_schema),
                "pair_count": 66,
                "label_authority": "Rafael",
                "private_gold_commitment": {
                    "algorithm": "sha256-canonical-json-v1",
                    "private_gold_sha256": "1" * 64,
                    "schema_version": 1,
                    "freeze_time": "2026-07-11T12:00:00Z",
                },
                "no_retuning": True,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return benchmark


def write_frozen_bundle(root: Path) -> tuple[Path, Path, Path, Path]:
    repo = root / "repo"
    benchmark = write_valid_public_bundle(repo)
    private = root / "private"
    private.mkdir()
    source_dir = private / "sources"
    write_private_source_fixture(source_dir, source_manifest_fixture())
    gold = private / "gold.json"
    packet = reconciled_packet_fixture()
    gold.write_bytes(canonical_json_bytes(packet))
    freeze = json.loads(
        (benchmark / "freeze-manifest.json").read_text(encoding="utf-8")
    )
    freeze["private_gold_commitment"] = gold_commitment(packet)
    (benchmark / "freeze-manifest.json").write_text(
        json.dumps(freeze, sort_keys=True), encoding="utf-8"
    )
    return benchmark, gold, source_dir, repo
