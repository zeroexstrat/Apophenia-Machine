from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from itertools import combinations
from pathlib import Path
from types import MappingProxyType
from typing import Any
from urllib.parse import urlparse

import yaml


LANES = (
    "operations_prescriptive_decision_support",
    "ml_data_science_planning",
    "human_organizational_decision_making",
)
PAPER_ID_PATTERN = re.compile(r"paper_[0-9a-f]{16}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
BENCHMARK_ID = "operations-decision-support-v1"

_EXPECTED_P5_METRIC_CONTRACTS: dict[str, dict[str, Any]] = {
    "macro_f1": {
        "population": "all 66 canonical pair-label predictions",
        "numerator": "classwise true positives used in precision and recall for labels 0-3",
        "denominator": "all gold and predicted instances for each label 0-3",
        "averaging": "unweighted mean of classwise F1 across labels 0-3",
        "undefined_case": "report null if any classwise F1 is undefined and report its zero denominator",
        "uncertainty": "paired bootstrap 95% interval with seed 5607",
        "future_artifact": "P7 locked pair-classification report",
        "comparison": ">=",
        "threshold": {"operator": ">=", "value": 0.80},
    },
    "unsafe_ood_assignment": {
        "population": "all evaluated out-of-domain assignment decisions",
        "numerator": "out-of-domain decisions assigned to an unsafe in-domain target",
        "denominator": "all evaluated out-of-domain assignment decisions",
        "averaging": "micro proportion",
        "undefined_case": "report null and denominator zero when no out-of-domain decisions are eligible",
        "uncertainty": "Wilson 95% interval",
        "future_artifact": "P7 locked safety report",
        "comparison": "==",
        "threshold": {"operator": "==", "value": 0.00},
    },
    "claim_precision": {
        "population": "all generated structural claims selected for evaluation",
        "numerator": "evaluated claims judged supported by visible source evidence",
        "denominator": "all generated structural claims selected for evaluation",
        "averaging": "micro proportion",
        "undefined_case": "report null and denominator zero when no claims are generated",
        "uncertainty": "Wilson 95% interval",
        "future_artifact": "P7 locked claim-evaluation report",
        "comparison": ">=",
        "threshold": {"operator": ">=", "value": 0.90},
    },
    "reference_recall": {
        "population": "all adjudicated relevant canonical pairs",
        "numerator": "adjudicated relevant pairs recovered by the locked output",
        "denominator": "all adjudicated relevant canonical pairs",
        "averaging": "micro proportion",
        "undefined_case": "report null and denominator zero when no relevant canonical pairs exist",
        "uncertainty": "Wilson 95% interval",
        "future_artifact": "P7 locked pair-recall report",
        "comparison": ">=",
        "threshold": {"operator": ">=", "value": 0.70},
    },
    "candidate_recall": {
        "population": "all adjudicated relevant pairs eligible for candidate generation",
        "numerator": "eligible relevant pairs present in the locked candidate set",
        "denominator": "all adjudicated relevant pairs eligible for candidate generation",
        "averaging": "micro proportion",
        "undefined_case": "report null and denominator zero when no relevant pairs are eligible",
        "uncertainty": "Wilson 95% interval",
        "future_artifact": "P7 locked candidate-generation report",
        "comparison": ">=",
        "threshold": {"operator": ">=", "value": 0.90},
    },
    "workload_reduction": {
        "population": "all 66 canonical pairs",
        "numerator": "canonical pairs excluded from the locked human-review queue",
        "denominator": "all 66 canonical pairs",
        "averaging": "paired comparison against exhaustive review",
        "undefined_case": "report null and denominator zero when no canonical pairs are eligible",
        "uncertainty": "paired bootstrap 95% interval with seed 5607",
        "future_artifact": "P7 locked workload report",
        "comparison": ">=",
        "threshold": {"operator": ">=", "value": 0.50},
    },
    "precision_at_5": {
        "population": "all benchmark queries with at least one adjudicated relevant candidate",
        "numerator": "adjudicated relevant results among the first five locked ranked results",
        "denominator": "up to five locked ranked results per eligible query",
        "averaging": "macro mean across eligible queries",
        "undefined_case": "report null and denominator zero when no query is eligible",
        "uncertainty": "paired bootstrap 95% interval with seed 5607",
        "future_artifact": "P7 locked ranking report",
        "comparison": ">=",
        "threshold": {"operator": ">=", "value": 0.60},
    },
    "ndcg_at_10": {
        "population": "all benchmark queries with adjudicated graded relevance",
        "numerator": "discounted cumulative gain in the first ten locked ranked results",
        "denominator": "ideal discounted cumulative gain in the first ten results",
        "averaging": "macro mean across eligible queries",
        "undefined_case": "report null and denominator zero when ideal gain is zero for every query",
        "uncertainty": "paired bootstrap 95% interval with seed 5607",
        "future_artifact": "P7 locked ranking report",
        "comparison": ">=",
        "threshold": {"operator": ">=", "value": 0.65},
    },
    "evidence_support": {
        "population": "all evidence spans attached to locked generated items",
        "numerator": "evidence spans verified against visible source records",
        "denominator": "all evidence spans attached to locked generated items",
        "averaging": "micro proportion",
        "undefined_case": "report null and denominator zero when no evidence spans are emitted",
        "uncertainty": "Wilson 95% interval",
        "future_artifact": "P7 locked evidence audit",
        "comparison": ">=",
        "threshold": {"operator": ">=", "value": 0.90},
    },
    "supported_items": {
        "population": "all locked generated items selected for human review",
        "numerator": "reviewed items supported by visible source evidence",
        "denominator": "all locked generated items selected for human review",
        "averaging": "micro proportion",
        "undefined_case": "report null and denominator zero when no items are reviewed",
        "uncertainty": "Wilson 95% interval",
        "future_artifact": "P7 locked item-quality report",
        "comparison": ">=",
        "threshold": {"operator": ">=", "value": 0.85},
    },
    "useful_items": {
        "population": "all locked generated items selected for human review",
        "numerator": "reviewed items judged useful for decision support",
        "denominator": "all locked generated items selected for human review",
        "averaging": "micro proportion",
        "undefined_case": "report null and denominator zero when no items are reviewed",
        "uncertainty": "Wilson 95% interval",
        "future_artifact": "P7 locked item-quality report",
        "comparison": ">=",
        "threshold": {"operator": ">=", "value": 0.60},
    },
    "redundancy": {
        "population": "all locked generated items selected for human review",
        "numerator": "reviewed items judged materially redundant with another locked item",
        "denominator": "all locked generated items selected for human review",
        "averaging": "micro proportion",
        "undefined_case": "report null and denominator zero when no items are reviewed",
        "uncertainty": "Wilson 95% interval",
        "future_artifact": "P7 locked redundancy report",
        "comparison": "<=",
        "threshold": {"operator": "<=", "value": 0.15},
    },
    "unsupported_derived_items": {
        "population": "all locked generated items carrying derived confidence",
        "numerator": "derived items not supported by visible source evidence",
        "denominator": "all locked generated items carrying derived confidence",
        "averaging": "micro proportion",
        "undefined_case": "report null and denominator zero when no derived items are emitted",
        "uncertainty": "Wilson 95% interval",
        "future_artifact": "P7 locked derivation audit",
        "comparison": "<=",
        "threshold": {"operator": "<=", "value": 0.05},
    },
}


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(
        {
            key: _freeze_mapping(child) if isinstance(child, Mapping) else child
            for key, child in value.items()
        }
    )


EXPECTED_P5_METRIC_CONTRACTS: Mapping[str, Mapping[str, Any]] = _freeze_mapping(
    _EXPECTED_P5_METRIC_CONTRACTS
)
EXPECTED_P5_THRESHOLDS: Mapping[str, Mapping[str, float | str]] = MappingProxyType(
    {
        name: contract["threshold"]
        for name, contract in EXPECTED_P5_METRIC_CONTRACTS.items()
    }
)

REQUIRED_SOURCE_FIELDS = (
    "paper_id",
    "title",
    "authors",
    "lane",
    "stable_identifier",
    "exact_version",
    "publication_date",
    "canonical_url",
    "download_url",
    "access_date",
    "sha256",
    "license",
    "license_evidence_url",
    "redistribution_status",
    "retrieval",
    "source_text_quality",
)
FORBIDDEN_GOLD_FIELDS = frozenset(
    {
        "gold_label",
        "gold_rationale",
        "gold_evidence_spans",
        "adjudication_notes",
        "adjudication_confidence",
        "relevance_class",
        "positive_degree",
        "target_thresholds",
        "benchmark_acceptance",
    }
)
PRIVATE_PACKET_FIELDS = frozenset(
    {
        "anchor_pair_ids",
        "canonical_pairs",
        "evidence_spans",
        "final_authority",
        "freeze",
        "gold_pairs",
        "label",
        "presentations",
        "rationale",
    }
)
BLINDED_FORBIDDEN_FIELDS = FORBIDDEN_GOLD_FIELDS | PRIVATE_PACKET_FIELDS
BLINDED_REQUIRED_TOP_LEVEL_FIELDS = (
    "schema_version",
    "benchmark_id",
    "packet_id",
    "pair_id",
    "paper_a_id",
    "paper_b_id",
    "sources",
    "status",
)
BLINDED_REQUIRED_SOURCE_FIELDS = (
    "paper_id",
    "stable_identifier",
    "exact_version",
    "title",
    "authors",
)
BLINDED_REQUIRED_EXPLICIT_CITATION_FIELDS = (
    "cited_paper_id",
    "citation_text",
)
BLINDED_IDENTITY_CONTRACT = {
    "paper_id": "paper_id(stable_identifier, exact_version)",
    "pair_id": "pair_id(paper_a_id, paper_b_id)",
    "packet_id": "packet_<pair_id digest>",
}
BLINDED_ALLOWED_FIELDS = {
    "packet": BLINDED_REQUIRED_TOP_LEVEL_FIELDS,
    "source_identity": ("paper_id", "stable_identifier", "exact_version"),
    "bibliographic_metadata": (
        "title",
        "authors",
        "publication_date",
        "canonical_url",
    ),
    "source_record": (
        "abstract",
        "extracted_record",
        "claims",
        "methods",
        "caveats",
        "tags",
        "explicit_citations",
    ),
    "extracted_record": (
        "claim",
        "method",
        "caveat",
        "tag",
        "visible_field",
        "visible_text",
    ),
    "explicit_citation": BLINDED_REQUIRED_EXPLICIT_CITATION_FIELDS,
}


class BenchmarkProtocolError(ValueError):
    """A benchmark artifact violates the frozen P5 contract."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def paper_id(stable_identifier: str, exact_version: str) -> str:
    identity = {
        "stable_identifier": " ".join(stable_identifier.split()).casefold(),
        "exact_version": " ".join(exact_version.split()).casefold(),
    }
    if not all(identity.values()):
        raise BenchmarkProtocolError("paper identity requires stable_identifier and exact_version")
    return f"paper_{canonical_digest(identity)[:16]}"


def pair_id(first: str, second: str) -> str:
    papers = sorted((first, second))
    if papers[0] == papers[1] or not all(PAPER_ID_PATTERN.fullmatch(item) for item in papers):
        raise BenchmarkProtocolError("benchmark pair requires two distinct valid paper IDs")
    return f"pair_{canonical_digest(papers)[:16]}"


def canonical_pairs(paper_ids: list[str]) -> list[dict[str, str]]:
    unique = sorted(set(paper_ids))
    if len(paper_ids) != 12 or len(unique) != 12:
        raise BenchmarkProtocolError("benchmark requires exactly 12 unique paper IDs")
    if not all(PAPER_ID_PATTERN.fullmatch(item) for item in unique):
        raise BenchmarkProtocolError("benchmark contains an invalid paper ID")
    return [
        {"pair_id": pair_id(a, b), "paper_a_id": a, "paper_b_id": b}
        for a, b in combinations(unique, 2)
    ]


def load_mapping(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        value = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise BenchmarkProtocolError(f"cannot read {path.name}: {exc}") from None
    if not isinstance(value, dict):
        raise BenchmarkProtocolError(f"{path.name}: expected top-level object")
    return value


def _walk_fields(
    value: Any, path: str = "/", seen: set[int] | None = None
) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen = set() if seen is None else seen
    if isinstance(value, (dict, list)):
        identity = id(value)
        if identity in seen:
            return found
        seen.add(identity)
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path.rstrip('/')}/{key}"
            found.append((child_path, str(key)))
            found.extend(_walk_fields(child, child_path, seen))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_walk_fields(child, f"{path.rstrip('/')}/{index}", seen))
    return found


def _is_nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_https(value: Any) -> bool:
    if not _is_nonempty(value):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _is_local_path(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return (
        value.startswith(("/", "~/", "file://", "\\\\"))
        or bool(re.match(r"^[A-Za-z]:[\\/]", value))
    )


def _forbidden_field_errors(payload: Any, forbidden: frozenset[str]) -> list[str]:
    if not isinstance(payload, dict):
        return ["/: expected object"]
    return [
        f"{path}: forbidden gold field {field}"
        for path, field in _walk_fields(payload)
        if field in forbidden
    ]


def validate_blinded_schema(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["/: expected object"]
    errors = _forbidden_field_errors(payload, FORBIDDEN_GOLD_FIELDS)
    expected_top_level = {
        "schema_version",
        "benchmark_id",
        "artifact_type",
        "required_top_level_fields",
        "required_source_fields",
        "required_explicit_citation_fields",
        "identity_contract",
        "allowed_fields",
        "forbidden_fields",
        "status_contract",
        "unknown_fields",
    }
    for field in sorted(set(payload) - expected_top_level, key=str):
        errors.append(f"/{field}: unexpected schema field")
    for field in sorted(expected_top_level - set(payload), key=str):
        errors.append(f"/{field}: required schema field missing")
    expected_values = {
        "schema_version": 1,
        "benchmark_id": BENCHMARK_ID,
        "artifact_type": "blinded_generation_packet_schema",
        "required_top_level_fields": list(BLINDED_REQUIRED_TOP_LEVEL_FIELDS),
        "required_source_fields": list(BLINDED_REQUIRED_SOURCE_FIELDS),
        "required_explicit_citation_fields": list(
            BLINDED_REQUIRED_EXPLICIT_CITATION_FIELDS
        ),
        "identity_contract": BLINDED_IDENTITY_CONTRACT,
        "forbidden_fields": sorted(BLINDED_FORBIDDEN_FIELDS),
        "status_contract": {
            "generation_input": "pending_review",
            "generation_output": "pending_review",
        },
        "unknown_fields": "reject",
    }
    for field, expected in expected_values.items():
        if payload.get(field) != expected:
            errors.append(f"/{field}: does not match frozen blinded schema")
    allowed = payload.get("allowed_fields")
    if not isinstance(allowed, dict):
        errors.append("/allowed_fields: expected object")
    else:
        if set(allowed) != set(BLINDED_ALLOWED_FIELDS):
            errors.append("/allowed_fields: expected exact field groups")
        for group, fields in BLINDED_ALLOWED_FIELDS.items():
            if allowed.get(group) != list(fields):
                errors.append(f"/allowed_fields/{group}: expected exact ordered fields")
    return errors


def _unexpected_fields(value: dict[str, Any], allowed: set[str], base: str) -> list[str]:
    return [
        f"{base.rstrip('/')}/{field}: unknown field rejected"
        for field in sorted(set(value) - allowed, key=str)
    ]


def validate_blinded_packet(
    payload: Any, schema: dict[str, Any] | None = None
) -> list[str]:
    if not isinstance(payload, dict):
        return ["/: expected object"]
    errors = _forbidden_field_errors(payload, BLINDED_FORBIDDEN_FIELDS)
    if schema is not None:
        errors.extend(f"/schema{error}" for error in validate_blinded_schema(schema))
    packet_fields = set(BLINDED_ALLOWED_FIELDS["packet"])
    errors.extend(_unexpected_fields(payload, packet_fields, "/"))
    for field in BLINDED_REQUIRED_TOP_LEVEL_FIELDS:
        if field not in payload:
            errors.append(f"/{field}: required field missing")
    if payload.get("schema_version") != 1:
        errors.append("/schema_version: expected 1")
    if payload.get("benchmark_id") != BENCHMARK_ID:
        errors.append(f"/benchmark_id: expected {BENCHMARK_ID}")
    for field in ("packet_id", "pair_id", "paper_a_id", "paper_b_id"):
        if not _is_nonempty(payload.get(field)):
            errors.append(f"/{field}: expected nonempty string")
    if payload.get("status") != "pending_review":
        errors.append("/status: expected pending_review")
    first_id = payload.get("paper_a_id")
    second_id = payload.get("paper_b_id")
    if isinstance(first_id, str) and first_id == second_id:
        errors.append("/paper_b_id: must differ from paper_a_id")
    expected_pair_id = ""
    if isinstance(first_id, str) and isinstance(second_id, str):
        try:
            expected_pair_id = pair_id(first_id, second_id)
        except BenchmarkProtocolError:
            errors.append("/paper_a_id: expected canonical paper identity")
            errors.append("/paper_b_id: expected canonical paper identity")
        else:
            if payload.get("pair_id") != expected_pair_id:
                errors.append("/pair_id: must match canonical paper pair identity")
            if payload.get("packet_id") != f"packet_{expected_pair_id.removeprefix('pair_')}":
                errors.append("/packet_id: must match canonical pair packet identity")

    sources = payload.get("sources")
    if not isinstance(sources, list):
        return errors + ["/sources: expected array"]
    if len(sources) != 2:
        errors.append("/sources: expected exactly two source records")
    allowed_source_fields = set(
        BLINDED_ALLOWED_FIELDS["source_identity"]
        + BLINDED_ALLOWED_FIELDS["bibliographic_metadata"]
        + BLINDED_ALLOWED_FIELDS["source_record"]
    )
    expected_source_ids = [first_id, second_id]
    extracted_allowed = set(BLINDED_ALLOWED_FIELDS["extracted_record"])
    citation_allowed = set(BLINDED_ALLOWED_FIELDS["explicit_citation"])
    for index, source in enumerate(sources):
        base = f"/sources/{index}"
        if not isinstance(source, dict):
            errors.append(f"{base}: expected object")
            continue
        errors.extend(_unexpected_fields(source, allowed_source_fields, base))
        for field in BLINDED_REQUIRED_SOURCE_FIELDS:
            if field not in source:
                errors.append(f"{base}/{field}: required field missing")
        for field in ("paper_id", "stable_identifier", "exact_version", "title"):
            if not _is_nonempty(source.get(field)):
                errors.append(f"{base}/{field}: expected nonempty string")
        if _is_nonempty(source.get("stable_identifier")) and _is_nonempty(
            source.get("exact_version")
        ):
            expected_paper_id = paper_id(
                source["stable_identifier"], source["exact_version"]
            )
            if source.get("paper_id") != expected_paper_id:
                errors.append(
                    f"{base}/paper_id: must match stable_identifier and exact_version"
                )
        if index < len(expected_source_ids) and source.get("paper_id") != expected_source_ids[index]:
            errors.append(f"{base}/paper_id: must match packet paper identity order")
        authors = source.get("authors")
        if not isinstance(authors, list) or not authors or not all(
            _is_nonempty(author) for author in authors
        ):
            errors.append(f"{base}/authors: expected nonempty string array")
        for field in ("publication_date", "abstract"):
            if field in source and not _is_nonempty(source[field]):
                errors.append(f"{base}/{field}: expected nonempty string")
        if "canonical_url" in source and not _is_https(source["canonical_url"]):
            errors.append(f"{base}/canonical_url: expected HTTPS URL")
        for field in ("claims", "methods", "caveats", "tags"):
            if field in source and (
                not isinstance(source[field], list)
                or not all(_is_nonempty(item) for item in source[field])
            ):
                errors.append(f"{base}/{field}: expected string array")
        extracted = source.get("extracted_record")
        if extracted is not None:
            if not isinstance(extracted, dict) or not extracted:
                errors.append(f"{base}/extracted_record: expected nonempty object")
            else:
                errors.extend(
                    _unexpected_fields(
                        extracted, extracted_allowed, f"{base}/extracted_record"
                    )
                )
                if not all(_is_nonempty(item) for item in extracted.values()):
                    errors.append(f"{base}/extracted_record: expected nonempty string values")
        citations = source.get("explicit_citations")
        if citations is not None:
            if not isinstance(citations, list):
                errors.append(f"{base}/explicit_citations: expected array")
            else:
                for citation_index, citation in enumerate(citations):
                    citation_base = f"{base}/explicit_citations/{citation_index}"
                    if not isinstance(citation, dict):
                        errors.append(f"{citation_base}: expected object")
                    else:
                        errors.extend(
                            _unexpected_fields(citation, citation_allowed, citation_base)
                        )
                        for field in BLINDED_REQUIRED_EXPLICIT_CITATION_FIELDS:
                            if field not in citation:
                                errors.append(
                                    f"{citation_base}/{field}: required field missing"
                                )
                        if not all(_is_nonempty(item) for item in citation.values()):
                            errors.append(f"{citation_base}: expected nonempty string values")
        if not _is_nonempty(source.get("abstract")) and not isinstance(
            source.get("extracted_record"), dict
        ):
            errors.append(f"{base}: abstract or extracted_record required")
    return errors


def validate_sources(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["/: expected object"]
    errors = _forbidden_field_errors(payload, FORBIDDEN_GOLD_FIELDS)
    if payload.get("schema_version") != 1:
        errors.append("/schema_version: expected 1")
    if payload.get("benchmark_id") != BENCHMARK_ID:
        errors.append(f"/benchmark_id: expected {BENCHMARK_ID}")
    sources = payload.get("sources")
    if not isinstance(sources, list):
        return errors + ["/sources: expected array"]
    if len(sources) != 12:
        errors.append("/sources: expected exactly 12 records")

    lane_counts: Counter[Any] = Counter()
    seen_ids: set[str] = set()
    for index, source in enumerate(sources):
        base = f"/sources/{index}"
        if not isinstance(source, dict):
            errors.append(f"{base}: expected object")
            continue
        for field in REQUIRED_SOURCE_FIELDS:
            if field not in source:
                errors.append(f"{base}/{field}: required field missing")
        for path, field in _walk_fields(source, base):
            if "path" in field.casefold():
                errors.append(f"{path}: paths are forbidden in public source records")
        for path, _field in _walk_fields(source, base):
            cursor: Any = source
            try:
                for part in path[len(base) :].strip("/").split("/"):
                    if part:
                        cursor = cursor[int(part)] if isinstance(cursor, list) else cursor[part]
            except (KeyError, IndexError, TypeError, ValueError):
                continue
            if _is_local_path(cursor):
                errors.append(f"{path}: private or local paths are forbidden")

        lane = source.get("lane")
        if isinstance(lane, str) and lane in LANES:
            lane_counts[lane] += 1
        else:
            errors.append(f"{base}/lane: expected one of {', '.join(LANES)}")
        identifier = source.get("paper_id")
        if not isinstance(identifier, str) or not PAPER_ID_PATTERN.fullmatch(identifier):
            errors.append(f"{base}/paper_id: invalid paper ID")
        elif identifier in seen_ids:
            errors.append(f"{base}/paper_id: duplicate paper ID {identifier}")
        else:
            seen_ids.add(identifier)
        stable = source.get("stable_identifier")
        version = source.get("exact_version")
        if _is_nonempty(stable) and _is_nonempty(version):
            if identifier != paper_id(stable, version):
                errors.append(f"{base}/paper_id: does not match stable_identifier and exact_version")
        else:
            if not _is_nonempty(stable):
                errors.append(f"{base}/stable_identifier: expected nonempty string")
            if not _is_nonempty(version):
                errors.append(f"{base}/exact_version: expected nonempty string")
        for field in ("canonical_url", "download_url", "license_evidence_url"):
            if not _is_https(source.get(field)):
                errors.append(f"{base}/{field}: expected HTTPS URL")
        digest = source.get("sha256")
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            errors.append(f"{base}/sha256: expected lowercase SHA-256")
        for field in ("title", "publication_date", "access_date", "license", "source_text_quality"):
            if not _is_nonempty(source.get(field)):
                errors.append(f"{base}/{field}: expected nonempty string")
        authors = source.get("authors")
        if not isinstance(authors, list) or not authors or not all(_is_nonempty(a) for a in authors):
            errors.append(f"{base}/authors: expected nonempty author strings")
        if source.get("redistribution_status") != "fetch_only":
            errors.append(f"{base}/redistribution_status: expected fetch_only")
        retrieval = source.get("retrieval")
        if not isinstance(retrieval, dict):
            errors.append(f"{base}/retrieval: expected object")
        else:
            if retrieval.get("method") != "https_get":
                errors.append(f"{base}/retrieval/method: expected https_get")
            if retrieval.get("redirect_policy") != "record_exact_chain":
                errors.append(f"{base}/retrieval/redirect_policy: expected record_exact_chain")
            final_url = retrieval.get("final_url")
            if not _is_https(final_url):
                errors.append(f"{base}/retrieval/final_url: expected HTTPS URL")
            redirect_chain = retrieval.get("redirect_chain")
            if not isinstance(redirect_chain, list):
                errors.append(f"{base}/retrieval/redirect_chain: expected exact URL array")
            elif (
                not redirect_chain
                or not all(_is_https(url) for url in redirect_chain)
                or redirect_chain[0] != source.get("download_url")
                or redirect_chain[-1] != final_url
            ):
                errors.append(
                    f"{base}/retrieval/redirect_chain: must run from download_url to final_url"
                )

    if any(lane_counts.get(lane, 0) != 4 for lane in LANES) or any(
        lane not in LANES for lane in lane_counts
    ):
        rendered = ", ".join(f"{lane}={lane_counts.get(lane, 0)}" for lane in LANES)
        errors.append(f"/sources: lane balance must be exactly 4/4/4 ({rendered})")
    return errors


def validate_source_directory(payload: Any, source_dir: Path) -> list[str]:
    errors = validate_sources(payload)
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        return errors
    for index, source in enumerate(payload["sources"]):
        if (
            not isinstance(source, dict)
            or not isinstance(source.get("paper_id"), str)
            or not PAPER_ID_PATTERN.fullmatch(source["paper_id"])
        ):
            continue
        base = f"/sources/{index}"
        identifier = source["paper_id"]
        pdf_path = source_dir / f"{identifier}.pdf"
        retrieval_path = source_dir / f"{identifier}.retrieval.json"
        try:
            actual_digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        except OSError as exc:
            errors.append(f"{base}/source_bytes: cannot read {pdf_path.name}: {exc}")
        else:
            if actual_digest != source.get("sha256"):
                errors.append(f"{base}/sha256: source byte sha256 mismatch")
        try:
            retrieval = load_mapping(retrieval_path)
        except BenchmarkProtocolError as exc:
            errors.append(f"{base}/retrieval_record: {exc}")
            continue
        public_retrieval = source.get("retrieval")
        if not isinstance(public_retrieval, dict):
            continue
        expected = {
            "requested_url": source.get("download_url"),
            "final_url": public_retrieval.get("final_url"),
            "access_date": source.get("access_date"),
            "exact_version": source.get("exact_version"),
            "license_evidence_url": source.get("license_evidence_url"),
            "sha256": source.get("sha256"),
        }
        for field, expected_value in expected.items():
            if retrieval.get(field) != expected_value:
                errors.append(f"{base}/retrieval_record/{field}: does not match public source record")
        if retrieval.get("media_type") != "application/pdf":
            errors.append(f"{base}/retrieval_record/media_type: expected application/pdf")
        chain = retrieval.get("redirect_chain")
        public_chain = public_retrieval.get("redirect_chain")
        if (
            not isinstance(chain, list)
            or not chain
            or chain[0] != retrieval.get("requested_url")
            or chain[-1] != retrieval.get("final_url")
            or not all(_is_https(url) for url in chain)
        ):
            errors.append(f"{base}/retrieval_record/redirect_chain: invalid exact redirect chain")
        elif chain != public_chain:
            errors.append(
                f"{base}/retrieval_record/redirect_chain: does not match public source record"
            )
    return errors


def validate_protocol(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["/: expected object"]
    errors = _forbidden_field_errors(payload, FORBIDDEN_GOLD_FIELDS)
    if payload.get("schema_version") != 1:
        errors.append("/schema_version: expected 1")
    if payload.get("benchmark_id") != BENCHMARK_ID:
        errors.append(f"/benchmark_id: expected {BENCHMARK_ID}")
    if payload.get("rubric_version") != "pair-relevance-v1":
        errors.append("/rubric_version: expected pair-relevance-v1")
    rubric = payload.get("rubric")
    if not isinstance(rubric, dict):
        errors.append("/rubric: expected object")
    else:
        scale = rubric.get("scale")
        if (
            not isinstance(scale, dict)
            or set(scale) != {0, 1, 2, 3}
            or not all(_is_nonempty(description) for description in scale.values())
        ):
            errors.append("/rubric/scale: expected nonempty definitions for labels 0-3")
        if rubric.get("relevant_labels") != [2, 3]:
            errors.append("/rubric/relevant_labels: expected [2, 3]")
    adjudication = payload.get("adjudication")
    if not isinstance(adjudication, dict):
        errors.append("/adjudication: expected object")
    else:
        expected_adjudication = {
            "final_authority": "Rafael",
            "canonical_pair_count": 66,
            "presentation_seed": 5607,
            "repeated_anchor_count": 4,
        }
        for field, expected in expected_adjudication.items():
            if adjudication.get(field) != expected:
                errors.append(f"/adjudication/{field}: expected {expected}")
    if payload.get("no_retuning") is not True:
        errors.append("/no_retuning: expected true")

    metrics = payload.get("metrics")
    if not isinstance(metrics, list):
        return errors + ["/metrics: expected array"]
    if len(metrics) != 13:
        errors.append("/metrics: expected exactly 13 records")
    names: list[str] = []
    for index, metric in enumerate(metrics):
        if not isinstance(metric, dict):
            continue
        name = metric.get("name")
        if not isinstance(name, str):
            errors.append(f"/metrics/{index}/name: expected metric name string")
        else:
            names.append(name)
    if len(names) != len(set(names)):
        errors.append("/metrics: metric names must be unique")
    if set(names) != set(EXPECTED_P5_THRESHOLDS):
        errors.append("/metrics: expected exact preregistered metric names")
    for index, metric in enumerate(metrics):
        base = f"/metrics/{index}"
        if not isinstance(metric, dict):
            errors.append(f"{base}: expected object")
            continue
        name = metric.get("name")
        expected = EXPECTED_P5_METRIC_CONTRACTS.get(name) if isinstance(name, str) else None
        if expected is not None:
            for field, expected_value in expected.items():
                if metric.get(field) != expected_value:
                    errors.append(f"{base}/{field}: does not match preregistered metric contract")
    return errors


def validate_freeze_manifest(
    payload: Any,
    *,
    source_digest: str,
    protocol_digest: str,
    prompt_digest: str,
    blinded_schema_digest: str,
) -> list[str]:
    if not isinstance(payload, dict):
        return ["/: expected object"]
    errors = _forbidden_field_errors(payload, FORBIDDEN_GOLD_FIELDS)
    expected_fields = {
        "schema_version": 1,
        "artifact_type": "azoth_benchmark_freeze",
        "benchmark_id": BENCHMARK_ID,
        "source_manifest_sha256": source_digest,
        "protocol_sha256": protocol_digest,
        "prompt_sha256": prompt_digest,
        "blinded_schema_sha256": blinded_schema_digest,
        "pair_count": 66,
        "label_authority": "Rafael",
        "no_retuning": True,
    }
    for field, expected in expected_fields.items():
        if payload.get(field) != expected:
            errors.append(f"/{field}: expected {expected}")
    status = payload.get("status")
    commitment = payload.get("private_gold_commitment")
    if status == "pending_human_adjudication":
        if commitment is not None:
            errors.append("/private_gold_commitment: must be null while human adjudication is pending")
    elif status == "frozen":
        if not isinstance(commitment, dict):
            errors.append("/private_gold_commitment: complete commitment required when frozen")
        else:
            required_commitment_fields = {
                "algorithm",
                "private_gold_sha256",
                "schema_version",
                "freeze_time",
            }
            unexpected_fields = [field for field in commitment if field not in required_commitment_fields]
            for field in sorted(unexpected_fields, key=str):
                errors.append(f"/private_gold_commitment/{field}: unexpected commitment field")
            expected_commitment = {
                "algorithm": "sha256-canonical-json-v1",
                "schema_version": 1,
            }
            for field, expected in expected_commitment.items():
                if commitment.get(field) != expected:
                    errors.append(f"/private_gold_commitment/{field}: expected {expected}")
            digest = commitment.get("private_gold_sha256")
            if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
                errors.append("/private_gold_commitment/private_gold_sha256: expected lowercase SHA-256")
            freeze_time = commitment.get("freeze_time")
            if not isinstance(freeze_time, str) or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", freeze_time
            ):
                errors.append("/private_gold_commitment/freeze_time: expected UTC timestamp")
    else:
        errors.append("/status: expected pending_human_adjudication or frozen")
    return errors


def validate_public_bundle(benchmark_root: Path) -> list[str]:
    sources = load_mapping(benchmark_root / "sources.yaml")
    protocol = load_mapping(benchmark_root / "protocol.yaml")
    blinded_schema = load_mapping(benchmark_root / "blinded-packet-schema.yaml")
    freeze = load_mapping(benchmark_root / "freeze-manifest.json")
    try:
        prompt_bytes = (benchmark_root / "generation-prompt.md").read_bytes()
    except OSError as exc:
        raise BenchmarkProtocolError(f"cannot read generation-prompt.md: {exc}") from None
    errors = validate_sources(sources)
    errors.extend(validate_protocol(protocol))
    errors.extend(validate_blinded_schema(blinded_schema))
    synthetic_packet_path = benchmark_root / "synthetic" / "blinded-packet.json"
    if synthetic_packet_path.exists():
        synthetic_packet = load_mapping(synthetic_packet_path)
        errors.extend(
            f"/synthetic/blinded-packet{error}"
            for error in validate_blinded_packet(synthetic_packet, blinded_schema)
        )
    try:
        source_digest = canonical_digest(sources)
    except (TypeError, ValueError, RecursionError) as exc:
        errors.append(f"/sources: cannot compute canonical digest: {exc}")
        source_digest = ""
    try:
        protocol_digest = canonical_digest(protocol)
    except (TypeError, ValueError, RecursionError) as exc:
        errors.append(f"/protocol: cannot compute canonical digest: {exc}")
        protocol_digest = ""
    try:
        blinded_schema_digest = canonical_digest(blinded_schema)
    except (TypeError, ValueError, RecursionError) as exc:
        errors.append(f"/blinded_schema: cannot compute canonical digest: {exc}")
        blinded_schema_digest = ""
    errors.extend(
        validate_freeze_manifest(
            freeze,
            source_digest=source_digest,
            protocol_digest=protocol_digest,
            prompt_digest=hashlib.sha256(prompt_bytes).hexdigest(),
            blinded_schema_digest=blinded_schema_digest,
        )
    )
    return errors
