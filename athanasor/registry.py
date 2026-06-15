"""JSONL registry for paper-level pipeline state."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


VALID_STATUSES = {"pending", "ingested_only", "exhausted"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class RegistryEntry:
    paper_id: str
    filename: str
    domain: str
    domain_confidence: float
    title: str
    authors: list[str]
    year: int | None
    ingested: str
    exhausted_at_depth: int | None = None
    connected: bool = False
    detected: bool = False
    drafted: bool = False
    triaged: bool = False
    status: str = "pending"
    paths: dict[str, str] | None = None
    processing_notes: list[str] | None = None
    source: dict[str, Any] | None = None
    tags: list[str] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "paper_id": self.paper_id,
            "filename": self.filename,
            "domain": self.domain,
            "domain_confidence": self.domain_confidence,
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "ingested": self.ingested,
            "exhausted_at_depth": self.exhausted_at_depth,
            "connected": self.connected,
            "detected": self.detected,
            "drafted": self.drafted,
            "triaged": self.triaged,
            "status": self.status,
            "paths": self.paths or {},
            "processing_notes": self.processing_notes or [],
        }
        if self.source is not None:
            payload["source"] = self.source
        if self.tags is not None:
            payload["tags"] = self.tags
        return payload


class Registry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def _load(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        with open(self.path, "r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    entries.append(payload)
        return entries

    def _write_all(self, entries: list[dict[str, Any]]) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, sort_keys=False) + "\n")

    def list(self) -> list[dict[str, Any]]:
        return self._load()

    def exists(self, paper_id: str) -> bool:
        for entry in self._load():
            if entry.get("paper_id") == paper_id:
                return True
        return False

    def get(self, paper_id: str) -> dict[str, Any] | None:
        for entry in self._load():
            if entry.get("paper_id") == paper_id:
                return entry
        return None

    def add(self, entry: dict[str, Any] | RegistryEntry) -> dict[str, Any]:
        payload = entry.as_dict() if isinstance(entry, RegistryEntry) else entry
        payload = self._normalize(payload)
        if not payload.get("paper_id"):
            raise ValueError("paper_id missing.")
        if self.exists(payload["paper_id"]):
            raise ValueError(f"Entry for {payload['paper_id']} already exists.")
        entries = self._load()
        entries.append(payload)
        self._write_all(entries)
        return payload

    def update(self, paper_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        entries = self._load()
        updated: dict[str, Any] | None = None
        for idx, entry in enumerate(entries):
            if entry.get("paper_id") == paper_id:
                entry.update(fields)
                entry = self._normalize(entry)
                entries[idx] = entry
                updated = entry
                break
        if updated is None:
            raise KeyError(f"paper_id not found: {paper_id}")
        self._write_all(entries)
        return updated

    def list_by_status(self, status: str) -> list[dict[str, Any]]:
        return [entry for entry in self._load() if entry.get("status") == status]

    def list_by_domain(self, domain: str) -> list[dict[str, Any]]:
        return [entry for entry in self._load() if entry.get("domain") == domain]

    def list_by_id_prefix(self, prefix: str) -> list[dict[str, Any]]:
        return [entry for entry in self._load() if str(entry.get("paper_id", "")).startswith(prefix)]

    def list_exhaustable(self, domain: str | None = None) -> list[dict[str, Any]]:
        result = self._load()
        if domain is not None:
            result = [entry for entry in result if entry.get("domain") == domain]
        return [
            entry
            for entry in result
            if entry.get("status") in {"pending", "ingested_only"}
        ]

    def stats(self) -> dict[str, Any]:
        entries = self._load()
        status_counts = Counter(entry.get("status") for entry in entries)
        domain_counts = Counter(entry.get("domain") for entry in entries)
        return {
            "total": len(entries),
            "status_counts": dict(status_counts),
            "domain_counts": dict(domain_counts),
        }

    def iter_all(self) -> Iterable[dict[str, Any]]:
        for entry in self._load():
            yield entry

    def _normalize(self, entry: dict[str, Any]) -> dict[str, Any]:
        status = str(entry.get("status", "pending"))
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{status}'.")
        entry["status"] = status
        if "ingested" not in entry:
            entry["ingested"] = _now()
        entry.setdefault("connected", False)
        entry.setdefault("detected", False)
        entry.setdefault("drafted", False)
        entry.setdefault("triaged", False)
        entry.setdefault("paths", {})
        entry.setdefault("processing_notes", [])
        return entry
