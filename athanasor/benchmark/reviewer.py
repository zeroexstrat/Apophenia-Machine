from __future__ import annotations

import re
import subprocess
import threading
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from athanasor.benchmark.freeze import (
    atomic_write_private,
    build_adjudication_packet,
    ensure_outside_repository,
)
from athanasor.benchmark.protocol import (
    BenchmarkProtocolError,
    load_mapping,
    validate_source_directory,
)


_ABSTRACT = re.compile(r"\bABSTRACT\b", re.IGNORECASE)
_ABSTRACT_END = re.compile(
    r"(?:\bCCS CONCEPTS\b|\bKEYWORDS\b|\bINDEX TERMS\b|\n\s*1[.\s]+INTRODUCTION\b)",
    re.IGNORECASE,
)
_INTRODUCTION = re.compile(r"\n\s*1[.\s]+INTRODUCTION\b", re.IGNORECASE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


class ReviewerError(ValueError):
    """The private adjudication reviewer cannot safely fulfill a request."""


def _pdf_text(path: Path) -> str:
    def extract(last_page: int, *, required: bool) -> str | None:
        try:
            result = subprocess.run(
                ["pdftotext", "-f", "1", "-l", str(last_page), str(path), "-"],
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            raise ReviewerError("cannot run pdftotext for private source") from exc
        if result.returncode != 0 or not result.stdout.strip():
            if required:
                raise ReviewerError("cannot extract readable text from private source")
            return None
        return result.stdout

    text = extract(2, required=True)
    assert text is not None
    if not _ABSTRACT.search(text) and not _INTRODUCTION.search(text):
        return extract(4, required=False) or text
    return text


def _normalize_prose(value: str) -> str:
    value = value.replace("\u00ad", "").replace("\x0c", "\n")
    value = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", value)
    return re.sub(r"\s+", " ", value).strip()


def extract_evidence_sentences(text: str) -> list[str]:
    match = _ABSTRACT.search(text)
    if match:
        candidate = text[match.end() :]
        boundary = _ABSTRACT_END.search(candidate)
        if boundary and len(_normalize_prose(candidate[: boundary.start()]).split()) < 3:
            # Two-column PDFs can place a neighboring KEYWORDS/CCS heading on the
            # same extracted line as ABSTRACT, before the abstract prose itself.
            candidate = candidate[: boundary.start()] + " " + candidate[boundary.end() :]
            boundary = _ABSTRACT_END.search(candidate)
        if boundary:
            candidate = candidate[: boundary.start()]
    else:
        introduction = _INTRODUCTION.search(text)
        candidate = text[introduction.end() :] if introduction else text
    normalized = _normalize_prose(candidate)
    sentences = [
        sentence.strip()
        for sentence in _SENTENCE.split(normalized)
        if 3 <= len(sentence.split()) <= 90
        and "arxiv:" not in sentence.casefold()
        and "@" not in sentence
        and "http://" not in sentence.casefold()
        and "https://" not in sentence.casefold()
    ]
    if not sentences:
        raise ReviewerError("private source has no usable evidence sentences")
    return sentences[:20]


@dataclass(frozen=True)
class _VisibleSource:
    title: str
    authors: tuple[str, ...]
    evidence: tuple[str, ...]


class ReviewSession:
    def __init__(
        self,
        *,
        packet_path: Path,
        repo_root: Path,
        packet: dict[str, Any],
        pairs: dict[str, dict[str, str]],
        sources: dict[str, _VisibleSource],
    ) -> None:
        self.packet_path = packet_path
        self.repo_root = repo_root
        self.packet = packet
        self._pairs = pairs
        self._sources = sources
        self._lock = threading.RLock()

    @classmethod
    def open(
        cls,
        *,
        packet_path: Path,
        source_dir: Path,
        benchmark_root: Path,
        repo_root: Path,
    ) -> "ReviewSession":
        try:
            safe_packet = ensure_outside_repository(packet_path, repo_root)
            safe_sources = ensure_outside_repository(source_dir, repo_root)
        except BenchmarkProtocolError as exc:
            raise ReviewerError(str(exc)) from None

        sources_payload = load_mapping(Path(benchmark_root) / "sources.yaml")
        protocol = load_mapping(Path(benchmark_root) / "protocol.yaml")
        source_errors = validate_source_directory(sources_payload, safe_sources)
        if source_errors:
            raise ReviewerError("private source validation failed: " + "; ".join(source_errors))
        packet = load_mapping(safe_packet)
        expected = build_adjudication_packet(sources_payload, protocol)
        cls._validate_topology(packet, expected)

        visible_sources: dict[str, _VisibleSource] = {}
        for source in sources_payload["sources"]:
            identifier = source["paper_id"]
            evidence = extract_evidence_sentences(
                _pdf_text(safe_sources / f"{identifier}.pdf")
            )
            visible_sources[identifier] = _VisibleSource(
                title=source["title"],
                authors=tuple(source["authors"]),
                evidence=tuple(evidence),
            )
        pairs = {row["pair_id"]: row for row in expected["canonical_pairs"]}
        return cls(
            packet_path=safe_packet,
            repo_root=Path(repo_root).expanduser().resolve(),
            packet=packet,
            pairs=pairs,
            sources=visible_sources,
        )

    @staticmethod
    def _validate_topology(packet: dict[str, Any], expected: dict[str, Any]) -> None:
        for key in (
            "schema_version",
            "artifact_type",
            "benchmark_id",
            "source_manifest_sha256",
            "rubric_version",
            "final_authority",
            "canonical_pairs",
            "anchor_pair_ids",
        ):
            if packet.get(key) != expected.get(key):
                raise ReviewerError(f"private packet topology mismatch at {key}")
        actual_rows = packet.get("presentations")
        expected_rows = expected["presentations"]
        if not isinstance(actual_rows, list) or len(actual_rows) != len(expected_rows):
            raise ReviewerError("private packet presentation count mismatch")
        actual_topology = [
            (row.get("presentation_id"), row.get("pair_id"))
            if isinstance(row, dict)
            else None
            for row in actual_rows
        ]
        expected_topology = [
            (row["presentation_id"], row["pair_id"]) for row in expected_rows
        ]
        if actual_topology != expected_topology:
            raise ReviewerError("private packet presentation topology mismatch")

    def _row_and_sources(
        self, index: int
    ) -> tuple[dict[str, Any], _VisibleSource, _VisibleSource]:
        rows = self.packet["presentations"]
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(rows):
            raise ReviewerError("presentation index is out of range")
        row = rows[index]
        pair = self._pairs[row["pair_id"]]
        return row, self._sources[pair["paper_a_id"]], self._sources[pair["paper_b_id"]]

    @staticmethod
    def _answer(row: dict[str, Any]) -> dict[str, Any]:
        evidence: dict[str, list[str]] = {"a": [], "b": []}
        spans = row.get("evidence_spans")
        if isinstance(spans, list):
            for span in spans:
                if isinstance(span, dict) and span.get("paper_role") in evidence:
                    text = span.get("text")
                    if isinstance(text, str):
                        evidence[span["paper_role"]].append(text)
        return {
            "label": row.get("label"),
            "rationale": row.get("rationale", ""),
            "evidence": evidence,
        }

    @classmethod
    def _offered_evidence(
        cls,
        row: dict[str, Any],
        paper_a: _VisibleSource,
        paper_b: _VisibleSource,
    ) -> dict[str, list[str]]:
        answer = cls._answer(row)
        return {
            "a": list(dict.fromkeys([*answer["evidence"]["a"], *paper_a.evidence])),
            "b": list(dict.fromkeys([*answer["evidence"]["b"], *paper_b.evidence])),
        }

    def presentation(self, index: int) -> dict[str, Any]:
        with self._lock:
            row, paper_a, paper_b = self._row_and_sources(index)
            offered = self._offered_evidence(row, paper_a, paper_b)
            completed = sum(
                item.get("label") is not None
                for item in self.packet["presentations"]
                if isinstance(item, dict)
            )
            return {
                "position": index + 1,
                "total": len(self.packet["presentations"]),
                "completed": completed,
                "paper_a": {
                    "title": paper_a.title,
                    "authors": list(paper_a.authors),
                    "evidence": offered["a"],
                },
                "paper_b": {
                    "title": paper_b.title,
                    "authors": list(paper_b.authors),
                    "evidence": offered["b"],
                },
                "answer": self._answer(row),
            }

    def save_answer(
        self,
        index: int,
        *,
        label: int,
        rationale: str,
        evidence: dict[str, list[str]],
    ) -> dict[str, Any]:
        with self._lock:
            row, paper_a, paper_b = self._row_and_sources(index)
            offered_by_role = self._offered_evidence(row, paper_a, paper_b)
            if isinstance(label, bool) or not isinstance(label, int) or label not in range(4):
                raise ReviewerError("label must be an integer from 0 to 3")
            if not isinstance(rationale, str) or not rationale.strip():
                raise ReviewerError("rationale is required")
            if not isinstance(evidence, dict):
                raise ReviewerError("evidence must cover both papers")
            selected: dict[str, list[str]] = {}
            for role in ("a", "b"):
                offered = offered_by_role[role]
                values = evidence.get(role)
                if not isinstance(values, list) or not values:
                    raise ReviewerError("evidence must cover both papers")
                if not all(isinstance(value, str) and value in offered for value in values):
                    raise ReviewerError("answer contains text that is not offered evidence")
                selected[role] = list(dict.fromkeys(values))

            updated = deepcopy(self.packet)
            updated_row = updated["presentations"][index]
            updated_row["label"] = label
            updated_row["rationale"] = rationale.strip()
            updated_row["evidence_spans"] = [
                {"paper_role": role, "text": text}
                for role in ("a", "b")
                for text in selected[role]
            ]
            try:
                atomic_write_private(self.packet_path, updated, self.repo_root)
            except BenchmarkProtocolError as exc:
                raise ReviewerError(str(exc)) from None
            self.packet = updated
            return self.presentation(index)
