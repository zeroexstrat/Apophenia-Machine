"""Durable fingerprints for human-rejected Rubedo hypothesis clusters."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


REJECTION_SCHEMA_VERSION = 1
REJECTION_ARTIFACT_TYPE = "rubedo_rejection"


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def candidate_fingerprint(hypothesis: dict[str, Any]) -> str:
    identity = {
        "paper_ids": sorted(
            {
                str(item).strip()
                for item in hypothesis.get("paper_ids", [])
                if str(item).strip()
            }
        ),
        "scope": _normalized(hypothesis.get("scope")),
    }
    return _digest(identity)


def evidence_fingerprint(hypothesis: dict[str, Any]) -> str:
    evidence: list[dict[str, Any]] = []
    for gap in hypothesis.get("gaps", []):
        if not isinstance(gap, dict):
            continue
        item = {
            "gap_type": _normalized(gap.get("gap_type")),
            "supporting_papers": sorted(
                {
                    str(paper_id).strip()
                    for paper_id in gap.get("supporting_papers", [])
                    if str(paper_id).strip()
                }
            ),
            "supporting_evidence": _normalized(gap.get("supporting_evidence")),
            "references": sorted(
                {
                    _normalized(reference)
                    for reference in gap.get("references", [])
                    if _normalized(reference)
                }
            ),
        }
        evidence.append(item)
    evidence.sort(key=lambda item: _canonical_bytes(item))
    return _digest(evidence)


def _validate_entry(entry: Any, line_number: int) -> list[str]:
    prefix = f"line {line_number}"
    if not isinstance(entry, dict):
        return [f"{prefix}: rejection entry is not an object"]
    errors: list[str] = []
    expected = {
        "schema_version": int,
        "artifact_type": str,
        "candidate_fingerprint": str,
        "evidence_fingerprint": str,
        "cluster_id": str,
        "paper_ids": list,
        "decision": str,
        "reviewer": str,
        "note": str,
        "reviewed_at": str,
    }
    for field, field_type in expected.items():
        value = entry.get(field)
        if not isinstance(value, field_type) or (field_type is str and not value.strip()):
            errors.append(f"{prefix}: invalid or missing {field}")
    if entry.get("schema_version") != REJECTION_SCHEMA_VERSION:
        errors.append(f"{prefix}: unsupported schema_version")
    if entry.get("artifact_type") != REJECTION_ARTIFACT_TYPE:
        errors.append(f"{prefix}: invalid artifact_type")
    if entry.get("decision") != "rejected":
        errors.append(f"{prefix}: decision must be rejected")
    for field in ("candidate_fingerprint", "evidence_fingerprint"):
        value = entry.get(field)
        if isinstance(value, str) and (
            len(value) != 64 or any(char not in "0123456789abcdef" for char in value)
        ):
            errors.append(f"{prefix}: {field} must be a lowercase SHA-256 digest")
    paper_ids = entry.get("paper_ids")
    if isinstance(paper_ids, list) and (
        not paper_ids
        or any(not isinstance(item, str) or not item.strip() for item in paper_ids)
        or paper_ids != sorted(set(paper_ids))
    ):
        errors.append(f"{prefix}: paper_ids must be a nonempty sorted unique string list")
    return errors


def load_rejections(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    if not path.exists():
        return [], []
    entries: list[dict[str, Any]] = []
    errors: list[str] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: invalid JSON ({exc.msg})")
            continue
        row_errors = _validate_entry(payload, line_number)
        if row_errors:
            details = "; ".join(
                error.split(": ", 1)[1] if ": " in error else error
                for error in row_errors
            )
            errors.append(f"line {line_number}: invalid rejection entry ({details})")
            continue
        entries.append(payload)
    return entries, errors


def rejection_entry(
    hypothesis: dict[str, Any],
    triage: dict[str, Any],
) -> dict[str, Any]:
    if triage.get("decision") != "rejected":
        raise ValueError("A rejection ledger entry requires decision='rejected'.")
    return {
        "schema_version": REJECTION_SCHEMA_VERSION,
        "artifact_type": REJECTION_ARTIFACT_TYPE,
        "candidate_fingerprint": candidate_fingerprint(hypothesis),
        "evidence_fingerprint": evidence_fingerprint(hypothesis),
        "cluster_id": str(hypothesis.get("cluster_id") or "").strip(),
        "paper_ids": sorted(
            {
                str(item).strip()
                for item in hypothesis.get("paper_ids", [])
                if str(item).strip()
            }
        ),
        "decision": "rejected",
        "reviewer": str(triage.get("reviewer") or "").strip(),
        "note": str(triage.get("note") or "").strip(),
        "reviewed_at": str(triage.get("reviewed_at") or "").strip(),
    }


def append_rejection(
    path: Path,
    hypothesis: dict[str, Any],
    triage: dict[str, Any],
) -> dict[str, Any]:
    entry = rejection_entry(hypothesis, triage)
    validation_errors = _validate_entry(entry, 1)
    if validation_errors:
        raise ValueError("Invalid rejection entry: " + "; ".join(validation_errors))
    existing, errors = load_rejections(path)
    if errors:
        raise ValueError("Rejection ledger is malformed: " + "; ".join(errors))
    identity = (entry["candidate_fingerprint"], entry["evidence_fingerprint"])
    for prior in existing:
        if (prior["candidate_fingerprint"], prior["evidence_fingerprint"]) == identity:
            return prior

    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = _canonical_bytes(entry) + b"\n"
    with open(path, "ab") as handle:
        handle.write(rendered)
        handle.flush()
        os.fsync(handle.fileno())
    return entry


def is_rejected(path: Path, hypothesis: dict[str, Any]) -> bool:
    entries, errors = load_rejections(path)
    if errors:
        raise ValueError("Rejection ledger is malformed: " + "; ".join(errors))
    candidate = candidate_fingerprint(hypothesis)
    evidence = evidence_fingerprint(hypothesis)
    return any(
        entry["candidate_fingerprint"] == candidate
        and entry["evidence_fingerprint"] == evidence
        for entry in entries
    )
