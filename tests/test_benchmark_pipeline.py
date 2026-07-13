from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from athanasor.benchmark.artifacts import (
    BenchmarkArtifactError,
    artifact_digest,
    validate_prepared,
)
from athanasor.benchmark.pipeline import (
    FetchResponse,
    build_blinded_packets,
    fetch_sources,
    import_run,
    prepare_benchmark,
    run_fallback,
)
from athanasor.benchmark.protocol import FORBIDDEN_GOLD_FIELDS, load_mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = REPO_ROOT / "benchmarks" / "operations-decision-support-v1"
SYNTHETIC_ROOT = BENCHMARK_ROOT / "synthetic"


def synthetic_manifest() -> dict[str, object]:
    payload = load_mapping(SYNTHETIC_ROOT / "sources.yaml")
    for source in payload["sources"]:
        source["download_url"] = f"https://example.invalid/{source['paper_id']}"
        source["canonical_url"] = source["download_url"]
        source["publication_date"] = "2026-01-01"
        source["access_date"] = "2026-07-12"
        source["license_evidence_url"] = "https://example.invalid/synthetic-license"
    return payload


def synthetic_responses(manifest: dict[str, object]) -> dict[str, FetchResponse]:
    responses: dict[str, FetchResponse] = {}
    for source in manifest["sources"]:  # type: ignore[index]
        url = source["download_url"]
        responses[url] = FetchResponse(
            body=source["source_text"].encode("utf-8"),
            requested_url=url,
            redirect_chain=(url,),
            final_url=url,
            media_type="application/pdf",
        )
    return responses


def visible_extractor(body: bytes, source: dict[str, object]) -> dict[str, object]:
    text = body.decode("utf-8")
    return {
        "abstract": text,
        "extracted_record": {"visible_field": "source_text", "visible_text": text},
        "claims": list(source["claims"]),
        "methods": [f"Synthetic method for {source['stable_identifier']}"],
        "caveats": ["Synthetic fixture only."],
        "tags": ["synthetic", str(source["lane"])],
        "explicit_citations": [],
    }


def recursive_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(recursive_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(recursive_keys(child))
    return keys


def test_fetch_verifies_all_bytes_before_accepting_destination(tmp_path: Path) -> None:
    manifest = synthetic_manifest()
    destination = tmp_path / "external-sources"
    responses = synthetic_responses(manifest)
    result = fetch_sources(manifest, destination, fetcher=responses.__getitem__)
    assert result["source_count"] == 6
    assert len(list(destination.glob("*.pdf"))) == 6
    assert len(list(destination.glob("*.retrieval.json"))) == 6
    for path in destination.glob("*.retrieval.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record["byte_count"] > 0
        assert record["redirect_chain"] == [record["requested_url"]]


def test_fetch_rejects_hash_drift_without_partial_destination(tmp_path: Path) -> None:
    manifest = synthetic_manifest()
    manifest["sources"][2]["sha256"] = "0" * 64  # type: ignore[index]
    destination = tmp_path / "external-sources"
    with pytest.raises(BenchmarkArtifactError, match="sha256 mismatch"):
        fetch_sources(
            manifest,
            destination,
            fetcher=synthetic_responses(synthetic_manifest()).__getitem__,
        )
    assert not destination.exists()


def test_fetch_rejects_non_https_redirects(tmp_path: Path) -> None:
    manifest = synthetic_manifest()
    responses = synthetic_responses(manifest)
    first = manifest["sources"][0]  # type: ignore[index]
    responses[first["download_url"]] = FetchResponse(
        body=first["source_text"].encode("utf-8"),
        requested_url=first["download_url"],
        redirect_chain=(first["download_url"], "http://example.invalid/unsafe"),
        final_url="http://example.invalid/unsafe",
        media_type="application/pdf",
    )
    with pytest.raises(BenchmarkArtifactError, match="HTTPS"):
        fetch_sources(manifest, tmp_path / "sources", fetcher=responses.__getitem__)


def test_fetch_rejects_frozen_redirect_chain_drift(tmp_path: Path) -> None:
    manifest = synthetic_manifest()
    responses = synthetic_responses(manifest)
    first = manifest["sources"][0]  # type: ignore[index]
    expected_url = first["download_url"]
    first["retrieval"] = {
        "method": "https_get",
        "redirect_policy": "record_exact_chain",
        "redirect_chain": [expected_url],
        "final_url": expected_url,
    }
    drifted = "https://example.invalid/drifted"
    responses[expected_url] = FetchResponse(
        body=first["source_text"].encode("utf-8"),
        requested_url=expected_url,
        redirect_chain=(expected_url, drifted),
        final_url=drifted,
        media_type="application/pdf",
    )
    with pytest.raises(BenchmarkArtifactError, match="frozen redirect chain"):
        fetch_sources(manifest, tmp_path / "sources", fetcher=responses.__getitem__)


def test_build_blinded_packets_produces_15_canonical_pairs() -> None:
    records = []
    for source in synthetic_manifest()["sources"]:  # type: ignore[index]
        records.append({**source, **visible_extractor(source["source_text"].encode(), source)})
    packets = build_blinded_packets(records)
    assert len(packets) == 15
    assert len({packet["pair_id"] for packet in packets}) == 15
    assert [packet["pair_id"] for packet in packets] == sorted(
        packet["pair_id"] for packet in packets
    )


def test_prepare_builds_all_15_pairs_without_gold(tmp_path: Path) -> None:
    manifest = synthetic_manifest()
    source_root = tmp_path / "sources"
    fetch_sources(manifest, source_root, fetcher=synthetic_responses(manifest).__getitem__)
    destination = tmp_path / "prepared.json"
    prepared = prepare_benchmark(
        BENCHMARK_ROOT,
        manifest,
        source_root,
        destination,
        extractor=visible_extractor,
    )
    assert destination.exists()
    assert len(prepared["packets"]) == 15
    assert validate_prepared(prepared) == []
    assert not recursive_keys(prepared) & set(FORBIDDEN_GOLD_FIELDS)


def test_prepare_fails_atomically_when_one_packet_is_invalid(tmp_path: Path) -> None:
    manifest = synthetic_manifest()
    source_root = tmp_path / "sources"
    fetch_sources(manifest, source_root, fetcher=synthetic_responses(manifest).__getitem__)
    destination = tmp_path / "prepared.json"
    calls = 0

    def invalid_extractor(body: bytes, source: dict[str, object]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        record = visible_extractor(body, source)
        if calls == 2:
            record["gold_label"] = 3
        return record

    with pytest.raises(BenchmarkArtifactError, match="gold_label"):
        prepare_benchmark(
            BENCHMARK_ROOT,
            manifest,
            source_root,
            destination,
            extractor=invalid_extractor,
        )
    assert not destination.exists()


def test_prepare_refuses_overwrite_without_force(tmp_path: Path) -> None:
    manifest = synthetic_manifest()
    source_root = tmp_path / "sources"
    fetch_sources(manifest, source_root, fetcher=synthetic_responses(manifest).__getitem__)
    destination = tmp_path / "prepared.json"
    prepare_benchmark(
        BENCHMARK_ROOT, manifest, source_root, destination, extractor=visible_extractor
    )
    with pytest.raises(BenchmarkArtifactError, match="already exists"):
        prepare_benchmark(
            BENCHMARK_ROOT, manifest, source_root, destination, extractor=visible_extractor
        )


def test_prepare_detects_source_byte_drift(tmp_path: Path) -> None:
    manifest = synthetic_manifest()
    source_root = tmp_path / "sources"
    fetch_sources(manifest, source_root, fetcher=synthetic_responses(manifest).__getitem__)
    first = manifest["sources"][0]  # type: ignore[index]
    (source_root / f"{first['paper_id']}.pdf").write_bytes(b"changed")
    with pytest.raises(BenchmarkArtifactError, match="sha256 mismatch"):
        prepare_benchmark(
            BENCHMARK_ROOT,
            deepcopy(manifest),
            source_root,
            tmp_path / "prepared.json",
            extractor=visible_extractor,
        )


def prepared_fixture(tmp_path: Path) -> dict[str, object]:
    manifest = synthetic_manifest()
    source_root = tmp_path / "sources"
    fetch_sources(manifest, source_root, fetcher=synthetic_responses(manifest).__getitem__)
    return prepare_benchmark(
        BENCHMARK_ROOT,
        manifest,
        source_root,
        tmp_path / "prepared.json",
        extractor=visible_extractor,
    )


def imported_responses(prepared: dict[str, object]) -> dict[str, object]:
    results = [
        {
            "pair_id": packet["pair_id"],
            "paper_a_id": packet["paper_a_id"],
            "paper_b_id": packet["paper_b_id"],
            "predicted_label": index % 4,
            "candidate": index % 4 >= 2,
            "score": index / max(1, len(prepared["packets"]) - 1),
            "rank_a": 1,
            "rank_b": 1,
            "items": [],
            "status": "pending_review",
        }
        for index, packet in enumerate(prepared["packets"])
    ]
    by_paper: dict[str, list[tuple[float, dict[str, object], str]]] = {}
    for row in results:
        by_paper.setdefault(row["paper_a_id"], []).append((row["score"], row, "rank_a"))
        by_paper.setdefault(row["paper_b_id"], []).append((row["score"], row, "rank_b"))
    for rows in by_paper.values():
        for rank, (_score, row, field) in enumerate(sorted(rows, key=lambda value: -value[0]), start=1):
            row[field] = rank
    return {
        "schema_version": 1,
        "artifact_type": "azoth_benchmark_responses",
        "benchmark_id": prepared["benchmark_id"],
        "prepared_sha256": artifact_digest(prepared),
        "backend": {"name": "external_test_backend", "version": "synthetic-v1"},
        "results": results,
    }


def test_fallback_run_is_byte_reproducible(tmp_path: Path) -> None:
    prepared = prepared_fixture(tmp_path)
    first = run_fallback(prepared, seed=5607)
    second = run_fallback(deepcopy(prepared), seed=5607)
    assert json.dumps(first, sort_keys=True, separators=(",", ":")) == json.dumps(
        second, sort_keys=True, separators=(",", ":")
    )
    assert len(first["results"]) == 15


def test_fallback_run_has_complete_pair_coverage_and_no_gold(tmp_path: Path) -> None:
    prepared = prepared_fixture(tmp_path)
    result = run_fallback(prepared)
    assert [row["pair_id"] for row in result["results"]] == sorted(
        packet["pair_id"] for packet in prepared["packets"]
    )
    assert not recursive_keys(result) & set(FORBIDDEN_GOLD_FIELDS)
    assert all(row["status"] == "pending_review" for row in result["results"])


def test_fallback_run_ranks_each_paper_without_ties(tmp_path: Path) -> None:
    result = run_fallback(prepared_fixture(tmp_path))
    by_paper: dict[str, list[int]] = {}
    for row in result["results"]:
        by_paper.setdefault(row["paper_a_id"], []).append(row["rank_a"])
        by_paper.setdefault(row["paper_b_id"], []).append(row["rank_b"])
    for ranks in by_paper.values():
        assert sorted(ranks) == list(range(1, len(ranks) + 1))


def test_import_run_accepts_complete_valid_responses(tmp_path: Path) -> None:
    prepared = prepared_fixture(tmp_path)
    result = import_run(prepared, imported_responses(prepared))
    assert result["backend"]["name"] == "external_test_backend"
    assert len(result["results"]) == 15


def test_import_run_rejects_partial_or_extra_pair_results(tmp_path: Path) -> None:
    prepared = prepared_fixture(tmp_path)
    responses = imported_responses(prepared)
    responses["results"].pop()
    with pytest.raises(BenchmarkArtifactError, match="exact pair coverage"):
        import_run(prepared, responses)


def test_import_run_rejects_gold_fields_recursively(tmp_path: Path) -> None:
    prepared = prepared_fixture(tmp_path)
    responses = imported_responses(prepared)
    responses["results"][0]["nested"] = {"gold_label": 3}
    with pytest.raises(BenchmarkArtifactError, match="gold_label"):
        import_run(prepared, responses)


def test_import_run_rejects_prepared_digest_mismatch(tmp_path: Path) -> None:
    prepared = prepared_fixture(tmp_path)
    responses = imported_responses(prepared)
    responses["prepared_sha256"] = "0" * 64
    with pytest.raises(BenchmarkArtifactError, match="prepared_sha256"):
        import_run(prepared, responses)
