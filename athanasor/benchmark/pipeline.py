from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Callable, Sequence

from athanasor.benchmark.artifacts import (
    PREPARED_TYPE,
    RUN_TYPE,
    SYNTHETIC_NOTICE,
    BenchmarkArtifactError,
    atomic_write_json,
    artifact_digest,
    validate_prepared,
    validate_run,
)
from athanasor.benchmark.protocol import (
    BENCHMARK_ID,
    FORBIDDEN_GOLD_FIELDS,
    canonical_digest,
    load_mapping,
    pair_id,
    paper_id,
    validate_blinded_packet,
    validate_public_bundle,
)


@dataclass(frozen=True)
class FetchResponse:
    body: bytes
    requested_url: str
    redirect_chain: Sequence[str]
    final_url: str
    media_type: str


class _RecordingRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, chain: list[str]) -> None:
        super().__init__()
        self.chain = chain

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        resolved = urllib.parse.urljoin(req.full_url, newurl)
        self.chain.append(resolved)
        return super().redirect_request(req, fp, code, msg, headers, resolved)


def fetch_https(url: str) -> FetchResponse:
    _require_https(url, "requested URL")
    chain = [url]
    opener = urllib.request.build_opener(_RecordingRedirectHandler(chain))
    request = urllib.request.Request(url, headers={"User-Agent": "Azoth-Benchmark/1"})
    try:
        with opener.open(request, timeout=60) as response:
            body = response.read()
            final_url = response.geturl()
            media_type = response.headers.get_content_type()
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        raise BenchmarkArtifactError(f"fetch failed for {url}: {exc}") from None
    if not chain or chain[-1] != final_url:
        chain.append(final_url)
    return FetchResponse(body, url, tuple(chain), final_url, media_type)


def _require_https(url: Any, label: str) -> str:
    if not isinstance(url, str) or urllib.parse.urlparse(url).scheme.casefold() != "https":
        raise BenchmarkArtifactError(f"{label} must use HTTPS")
    return url


def _manifest_sources(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("benchmark_id") != BENCHMARK_ID:
        raise BenchmarkArtifactError(f"/benchmark_id: expected {BENCHMARK_ID}")
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        raise BenchmarkArtifactError("/sources: expected nonempty array")
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise BenchmarkArtifactError(f"/sources/{index}: expected object")
        identifier = source.get("paper_id")
        if not isinstance(identifier, str) or not identifier:
            raise BenchmarkArtifactError(f"/sources/{index}/paper_id: expected string")
        if identifier in seen:
            raise BenchmarkArtifactError(f"/sources/{index}/paper_id: duplicate {identifier}")
        seen.add(identifier)
        for field in ("stable_identifier", "exact_version", "title", "authors", "sha256"):
            if field not in source:
                raise BenchmarkArtifactError(f"/sources/{index}/{field}: required field missing")
        digest = source.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise BenchmarkArtifactError(f"/sources/{index}/sha256: expected SHA-256")
        validated.append(source)
    return validated


def _replace_directory(temporary: Path, destination: Path, *, force: bool) -> None:
    if destination.exists() and not force:
        raise BenchmarkArtifactError(f"destination already exists: {destination.name}")
    backup: Path | None = None
    try:
        if destination.exists():
            backup = Path(tempfile.mkdtemp(prefix=f".{destination.name}.backup.", dir=destination.parent))
            backup.rmdir()
            os.replace(destination, backup)
        os.replace(temporary, destination)
        if backup is not None:
            shutil.rmtree(backup)
    except BaseException:
        if backup is not None and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise


def fetch_sources(
    source_manifest: dict[str, Any],
    destination: Path,
    *,
    fetcher: Callable[[str], FetchResponse] = fetch_https,
    force: bool = False,
) -> dict[str, Any]:
    sources = _manifest_sources(source_manifest)
    target = Path(destination).expanduser().resolve(strict=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not force:
        raise BenchmarkArtifactError(f"destination already exists: {target.name}")
    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.fetch.", dir=target.parent))
    try:
        for index, source in enumerate(sources):
            url = _require_https(source.get("download_url"), f"/sources/{index}/download_url")
            response = fetcher(url)
            if response.requested_url != url:
                raise BenchmarkArtifactError(f"/sources/{index}/retrieval: requested URL mismatch")
            if not response.redirect_chain or response.redirect_chain[0] != url:
                raise BenchmarkArtifactError(f"/sources/{index}/retrieval: invalid redirect chain")
            for redirect in response.redirect_chain:
                _require_https(redirect, f"/sources/{index}/retrieval redirect")
            _require_https(response.final_url, f"/sources/{index}/final_url")
            if response.redirect_chain[-1] != response.final_url:
                raise BenchmarkArtifactError(f"/sources/{index}/retrieval: final URL mismatch")
            frozen_retrieval = source.get("retrieval")
            if isinstance(frozen_retrieval, dict):
                if list(response.redirect_chain) != frozen_retrieval.get("redirect_chain"):
                    raise BenchmarkArtifactError(
                        f"/sources/{index}/retrieval: frozen redirect chain drift"
                    )
                if response.final_url != frozen_retrieval.get("final_url"):
                    raise BenchmarkArtifactError(
                        f"/sources/{index}/retrieval: frozen final URL drift"
                    )
            if response.media_type.casefold() != "application/pdf":
                raise BenchmarkArtifactError(f"/sources/{index}/media_type: expected application/pdf")
            digest = hashlib.sha256(response.body).hexdigest()
            if digest != source.get("sha256"):
                raise BenchmarkArtifactError(f"/sources/{index}/sha256: source byte sha256 mismatch")
            identifier = str(source["paper_id"])
            (temporary / f"{identifier}.pdf").write_bytes(response.body)
            retrieval_record = {
                "requested_url": url,
                "redirect_chain": list(response.redirect_chain),
                "final_url": response.final_url,
                "media_type": response.media_type,
                "access_date": source.get("access_date"),
                "exact_version": source.get("exact_version"),
                "license_evidence_url": source.get("license_evidence_url"),
                "sha256": digest,
                "byte_count": len(response.body),
            }
            atomic_write_json(temporary / f"{identifier}.retrieval.json", retrieval_record)
        _replace_directory(temporary, target, force=force)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "benchmark_id": source_manifest["benchmark_id"],
        "source_count": len(sources),
        "source_manifest_sha256": canonical_digest(source_manifest),
    }


def _normalized_text(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value)).split())


def _reject_gold_fields(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}/{key}"
            if isinstance(key, str) and key.casefold() in FORBIDDEN_GOLD_FIELDS:
                raise BenchmarkArtifactError(f"{child_path}: gold-only field is forbidden")
            _reject_gold_fields(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_gold_fields(child, f"{path}/{index}")


def extract_pdf_record(body: bytes, source: dict[str, Any]) -> dict[str, Any]:
    try:
        import fitz

        document = fitz.open(stream=body, filetype="pdf")
        text = "\n".join(page.get_text("text") for page in document)
    except Exception as exc:
        raise BenchmarkArtifactError(f"cannot extract {source.get('paper_id')}: {exc}") from None
    visible = _normalized_text(text)
    if not visible:
        raise BenchmarkArtifactError(f"cannot extract {source.get('paper_id')}: no visible text")
    excerpt = visible[:8000]
    return {
        "abstract": excerpt,
        "extracted_record": {"visible_field": "source_text", "visible_text": excerpt},
        "claims": [],
        "methods": [],
        "caveats": [],
        "tags": [],
        "explicit_citations": [],
    }


def extract_synthetic_record(body: bytes, source: dict[str, Any]) -> dict[str, Any]:
    if source.get("synthetic") is not True:
        raise BenchmarkArtifactError("synthetic extractor requires synthetic source records")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BenchmarkArtifactError(f"cannot decode synthetic source: {exc}") from None
    if hashlib.sha256(body).hexdigest() != source.get("sha256"):
        raise BenchmarkArtifactError("synthetic source sha256 mismatch")
    return {
        "abstract": _normalized_text(text),
        "extracted_record": {
            "visible_field": "source_text",
            "visible_text": _normalized_text(text),
        },
        "claims": list(source.get("claims", [])),
        "methods": [f"Synthetic method for {source.get('stable_identifier')}"],
        "caveats": ["Synthetic fixture only."],
        "tags": ["synthetic", str(source.get("lane", "synthetic"))],
        "explicit_citations": [],
    }


def _visible_source(source: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "stable_identifier",
        "exact_version",
        "title",
        "authors",
        "publication_date",
        "canonical_url",
        "abstract",
        "extracted_record",
        "claims",
        "methods",
        "caveats",
        "tags",
        "explicit_citations",
    )
    result = {field: source[field] for field in allowed if field in source}
    result["paper_id"] = paper_id(str(source["stable_identifier"]), str(source["exact_version"]))
    return result


def build_blinded_packets(source_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    visible = sorted((_visible_source(source) for source in source_records), key=lambda row: row["paper_id"])
    if len(visible) < 2 or len({row["paper_id"] for row in visible}) != len(visible):
        raise BenchmarkArtifactError("source records require at least two unique canonical paper IDs")
    packets: list[dict[str, Any]] = []
    for first, second in combinations(visible, 2):
        identifier = pair_id(first["paper_id"], second["paper_id"])
        packets.append(
            {
                "schema_version": 1,
                "benchmark_id": BENCHMARK_ID,
                "packet_id": f"packet_{identifier.split('_', 1)[1]}",
                "pair_id": identifier,
                "paper_a_id": first["paper_id"],
                "paper_b_id": second["paper_id"],
                "sources": [first, second],
                "status": "pending_review",
            }
        )
    return sorted(packets, key=lambda packet: packet["pair_id"])


def _verify_source_root(source_manifest: dict[str, Any], source_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, source in enumerate(_manifest_sources(source_manifest)):
        identifier = str(source["paper_id"])
        source_path = source_root / f"{identifier}.pdf"
        retrieval_path = source_root / f"{identifier}.retrieval.json"
        try:
            body = source_path.read_bytes()
        except OSError as exc:
            raise BenchmarkArtifactError(f"/sources/{index}/source_bytes: {exc}") from None
        digest = hashlib.sha256(body).hexdigest()
        if digest != source.get("sha256"):
            raise BenchmarkArtifactError(f"/sources/{index}/sha256: source byte sha256 mismatch")
        try:
            retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BenchmarkArtifactError(f"/sources/{index}/retrieval: {exc}") from None
        if not isinstance(retrieval, dict) or retrieval.get("sha256") != digest:
            raise BenchmarkArtifactError(f"/sources/{index}/retrieval/sha256: mismatch")
        records.append({**source, "_body": body})
    return records


def prepare_benchmark(
    benchmark_root: Path,
    source_manifest: dict[str, Any],
    source_root: Path,
    destination: Path,
    *,
    extractor: Callable[[bytes, dict[str, Any]], dict[str, Any]] = extract_pdf_record,
    force: bool = False,
) -> dict[str, Any]:
    public_errors = validate_public_bundle(Path(benchmark_root))
    if public_errors:
        raise BenchmarkArtifactError("invalid public benchmark: " + "; ".join(sorted(public_errors)))
    destination = Path(destination)
    if destination.exists() and not force:
        raise BenchmarkArtifactError(f"destination already exists: {destination.name}")
    records: list[dict[str, Any]] = []
    source_digests: dict[str, str] = {}
    for source in _verify_source_root(source_manifest, Path(source_root)):
        body = source.pop("_body")
        extracted = extractor(body, source)
        if not isinstance(extracted, dict):
            raise BenchmarkArtifactError(f"extractor returned non-object for {source['paper_id']}")
        _reject_gold_fields(extracted, f"/sources/{source['paper_id']}")
        records.append({**source, **extracted})
        source_digests[str(source["paper_id"])] = hashlib.sha256(body).hexdigest()
    packets = build_blinded_packets(records)
    blinded_schema = load_mapping(Path(benchmark_root) / "blinded-packet-schema.yaml")
    packet_errors: list[str] = []
    for index, packet in enumerate(packets):
        packet_errors.extend(
            f"/packets/{index}{error}" for error in validate_blinded_packet(packet, blinded_schema)
        )
    if packet_errors:
        raise BenchmarkArtifactError("invalid blinded packet: " + "; ".join(sorted(packet_errors)))
    protocol = load_mapping(Path(benchmark_root) / "protocol.yaml")
    frozen_sources = load_mapping(Path(benchmark_root) / "sources.yaml")
    freeze = load_mapping(Path(benchmark_root) / "freeze-manifest.json")
    prompt = (Path(benchmark_root) / "generation-prompt.md").read_bytes()
    prepared = {
        "schema_version": 1,
        "artifact_type": PREPARED_TYPE,
        "benchmark_id": BENCHMARK_ID,
        "synthetic": all(source.get("synthetic") is True for source in _manifest_sources(source_manifest)),
        "notice": SYNTHETIC_NOTICE if all(source.get("synthetic") is True for source in _manifest_sources(source_manifest)) else None,
        "provenance": {
            "source_manifest_sha256": canonical_digest(source_manifest),
            "protocol_sha256": canonical_digest(protocol),
            "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
            "blinded_schema_sha256": canonical_digest(blinded_schema),
            "freeze_manifest_sha256": canonical_digest(freeze),
            "frozen_source_manifest_sha256": canonical_digest(frozen_sources),
            "source_bytes_sha256": canonical_digest(source_digests),
            "extraction_tool": f"{extractor.__module__}.{extractor.__name__}",
        },
        "packets": packets,
        "status": "prepared",
    }
    if not prepared["synthetic"]:
        prepared.pop("notice")
    errors = validate_prepared(prepared)
    if errors:
        raise BenchmarkArtifactError("invalid prepared artifact: " + "; ".join(errors))
    atomic_write_json(destination, prepared, force=force)
    return prepared


def _visible_tokens(source: dict[str, Any]) -> set[str]:
    values: list[str] = []
    for field in ("abstract", "claims", "methods", "tags", "extracted_record"):
        value = source.get(field)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, list):
            values.extend(str(item) for item in value)
        elif isinstance(value, dict):
            values.extend(str(item) for item in value.values())
    normalized = _normalized_text(" ".join(values)).casefold()
    tokens = re.findall(r"[a-z0-9_]{3,}", normalized)
    return {hashlib.sha256(token.encode("utf-8")).hexdigest()[:16] for token in tokens}


def _fallback_pair(packet: dict[str, Any], *, seed: int) -> dict[str, Any]:
    first, second = packet["sources"]
    first_tokens = _visible_tokens(first)
    second_tokens = _visible_tokens(second)
    union = first_tokens | second_tokens
    overlap = len(first_tokens & second_tokens) / len(union) if union else 0.0
    tie_bytes = hashlib.sha256(f"{seed}:{packet['pair_id']}".encode("utf-8")).digest()
    tie_break = int.from_bytes(tie_bytes[:2], "big") / 65535 * 1e-6
    score = round(min(1.0, overlap + tie_break), 12)
    if score < 0.10:
        predicted_label = 0
    elif score < 0.25:
        predicted_label = 1
    elif score < 0.50:
        predicted_label = 2
    else:
        predicted_label = 3
    candidate = predicted_label >= 2
    items: list[dict[str, Any]] = []
    if candidate:
        items.append(
            {
                "item_id": f"item_{packet['pair_id'].split('_', 1)[1]}",
                "assessment": "Deterministic visible-record overlap candidate.",
                "confidence": "likely" if predicted_label == 3 else "speculative",
                "evidence": [
                    {"paper_id": first["paper_id"], "visible_field": "source_record"},
                    {"paper_id": second["paper_id"], "visible_field": "source_record"},
                ],
                "status": "pending_review",
            }
        )
    return {
        "pair_id": packet["pair_id"],
        "paper_a_id": packet["paper_a_id"],
        "paper_b_id": packet["paper_b_id"],
        "predicted_label": predicted_label,
        "candidate": candidate,
        "score": score,
        "rank_a": 0,
        "rank_b": 0,
        "items": items,
        "status": "pending_review",
    }


def _assign_pair_ranks(results: list[dict[str, Any]]) -> None:
    incident: dict[str, list[tuple[float, str, str, dict[str, Any], str]]] = {}
    for row in results:
        first = str(row["paper_a_id"])
        second = str(row["paper_b_id"])
        score = float(row["score"])
        incident.setdefault(first, []).append((score, second, row["pair_id"], row, "rank_a"))
        incident.setdefault(second, []).append((score, first, row["pair_id"], row, "rank_b"))
    for entries in incident.values():
        ordered = sorted(entries, key=lambda item: (-item[0], item[1], item[2]))
        for rank, (_score, _other, _pair, row, field) in enumerate(ordered, start=1):
            row[field] = rank


def _run_artifact(
    prepared: dict[str, Any],
    *,
    backend: dict[str, Any],
    seed: int,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    run = {
        "schema_version": 1,
        "artifact_type": RUN_TYPE,
        "benchmark_id": BENCHMARK_ID,
        "synthetic": prepared["synthetic"],
        "prepared_sha256": artifact_digest(prepared),
        "backend": backend,
        "seed": seed,
        "results": sorted(results, key=lambda row: row["pair_id"]),
        "status": "locked",
    }
    if prepared["synthetic"]:
        run["notice"] = SYNTHETIC_NOTICE
    errors = validate_run(run)
    if errors:
        raise BenchmarkArtifactError("invalid run artifact: " + "; ".join(errors))
    return run


def run_fallback(prepared: dict[str, Any], *, seed: int = 5607) -> dict[str, Any]:
    errors = validate_prepared(prepared)
    if errors:
        raise BenchmarkArtifactError("invalid prepared artifact: " + "; ".join(errors))
    results = [_fallback_pair(packet, seed=seed) for packet in prepared["packets"]]
    _assign_pair_ranks(results)
    return _run_artifact(
        prepared,
        backend={"name": "deterministic_hash_fallback", "version": 1},
        seed=seed,
        results=results,
    )


def import_run(prepared: dict[str, Any], responses: dict[str, Any]) -> dict[str, Any]:
    prepared_errors = validate_prepared(prepared)
    if prepared_errors:
        raise BenchmarkArtifactError("invalid prepared artifact: " + "; ".join(prepared_errors))
    if not isinstance(responses, dict):
        raise BenchmarkArtifactError("responses: expected object")
    _reject_gold_fields(responses, "/responses")
    expected_digest = artifact_digest(prepared)
    if responses.get("prepared_sha256") != expected_digest:
        raise BenchmarkArtifactError("/prepared_sha256: does not match prepared artifact")
    if responses.get("benchmark_id") != BENCHMARK_ID:
        raise BenchmarkArtifactError(f"/benchmark_id: expected {BENCHMARK_ID}")
    backend = responses.get("backend")
    if not isinstance(backend, dict) or not isinstance(backend.get("name"), str):
        raise BenchmarkArtifactError("/backend: expected named object")
    response_rows = responses.get("results")
    if not isinstance(response_rows, list):
        raise BenchmarkArtifactError("/results: expected array")
    expected_packets = {packet["pair_id"]: packet for packet in prepared["packets"]}
    actual_ids = [row.get("pair_id") for row in response_rows if isinstance(row, dict)]
    if len(actual_ids) != len(response_rows) or set(actual_ids) != set(expected_packets) or len(actual_ids) != len(set(actual_ids)):
        raise BenchmarkArtifactError("/results: exact pair coverage required")
    results: list[dict[str, Any]] = []
    allowed_fields = {
        "pair_id",
        "paper_a_id",
        "paper_b_id",
        "predicted_label",
        "candidate",
        "score",
        "rank_a",
        "rank_b",
        "items",
        "status",
    }
    for index, row in enumerate(response_rows):
        if not isinstance(row, dict):
            raise BenchmarkArtifactError(f"/results/{index}: expected object")
        unexpected = sorted(set(row) - allowed_fields)
        if unexpected:
            raise BenchmarkArtifactError(f"/results/{index}/{unexpected[0]}: unexpected field")
        packet = expected_packets[row["pair_id"]]
        for field in ("paper_a_id", "paper_b_id"):
            if row.get(field) != packet[field]:
                raise BenchmarkArtifactError(f"/results/{index}/{field}: does not match prepared packet")
        results.append(dict(row))
    return _run_artifact(
        prepared,
        backend=dict(backend),
        seed=int(responses.get("seed", 5607)),
        results=results,
    )
