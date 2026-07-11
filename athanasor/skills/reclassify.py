"""Reclassify skill: re-file already-ingested papers into (possibly new) domains.

Unlike ``ingest``, this never re-parses PDFs or mints new paper IDs. Status
(``ingested_only`` / ``exhausted``) is always preserved.

Two ways to decide a paper's domain:

* **Classifier** — re-run domain classification from the stored library record,
  using the configured LLM backend (Ollama / OpenAI-compatible) or heuristics.
* **Agent assignments** — apply domain decisions the *driving agent* produced by
  reading the papers itself (``--assignments``). This needs no separate LLM
  backend: when Azoth runs as a skill inside an app, the app's own model is the
  classifier.

Both paths share one apply step (move file, update registry in place) and one
open-vocabulary rule: a confident new domain outside the current taxonomy can be
adopted — appended to ``config.domains`` and persisted to ``azoth.config.yaml`` —
so the operator never hand-maintains the category list.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from ..config import Config, load_config, save_config
from ..domain_classifier import classify
from ..llm import LLMClient
from ..registry import Registry
from . import common
from .common import load_yaml_tolerant, run_vigil_check

# A domain label must be a short, filesystem-safe token — never a path fragment.
_DOMAIN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]{1,40}$")


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reclassify ingested papers into domains.")
    parser.add_argument("--scope", default="unclassified", help="'unclassified', 'all', or a domain name.")
    parser.add_argument("--min-confidence", type=float, default=0.6)
    parser.add_argument("--allow-new-domains", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--apply", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--assignments", type=Path, default=None, help="JSON of agent-produced decisions.")
    return parser


def _run_vigil(root: Path, phase: str) -> None:
    run_vigil_check(root=root, phase=phase, skill="reclassify")


def run_reclassify(
    *,
    config: Config | None = None,
    llm: LLMClient | None = None,
    scope: str = "unclassified",
    allow_new_domains: bool = True,
    min_confidence: float = 0.6,
    apply: bool = True,
    assignments: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    config = config or load_config()
    root = Path(config.project_root).expanduser().resolve()
    registry = Registry(root / "albedo" / "registry.jsonl")

    if assignments is not None:
        return _run_assignments(
            root=root,
            registry=registry,
            config=config,
            assignments=assignments,
            allow_new_domains=allow_new_domains,
            min_confidence=min_confidence,
            apply=apply,
        )

    entries = _select_entries(registry, scope)
    if not entries:
        return []

    _run_vigil(root, "start")
    results: list[dict[str, Any]] = []
    config_dirty = False

    for entry in entries:
        paper_id = str(entry.get("paper_id") or "")
        if not paper_id:
            continue

        title, abstract, context_text = _classification_signal(root, entry)
        classification = classify(
            title=title,
            abstract=abstract,
            llm=llm,
            config=config,
            filename=str(entry.get("filename") or ""),
            context_text=context_text,
            allow_new_domains=allow_new_domains,
        )
        result, dirty = _decide_and_apply(
            root=root,
            registry=registry,
            config=config,
            entry=entry,
            new_domain=classification.domain,
            confidence=float(classification.confidence or 0.0),
            proposed=bool(classification.proposed),
            source="classifier",
            allow_new_domains=allow_new_domains,
            min_confidence=min_confidence,
            apply=apply,
        )
        config_dirty = config_dirty or dirty
        results.append(result)

    if config_dirty:
        _persist_domains(root, config)
    _run_vigil(root, "verify")
    return results


def _run_assignments(
    *,
    root: Path,
    registry: Registry,
    config: Config,
    assignments: list[dict[str, Any]],
    allow_new_domains: bool,
    min_confidence: float,
    apply: bool,
) -> list[dict[str, Any]]:
    _run_vigil(root, "start")
    results: list[dict[str, Any]] = []
    config_dirty = False

    for raw in assignments:
        if not isinstance(raw, dict):
            results.append({"paper_id": None, "action": "invalid_assignment", "detail": repr(raw)[:120]})
            continue
        paper_id = str(raw.get("paper_id") or "").strip()
        new_domain = str(raw.get("domain") or "").strip()
        entry = registry.get(paper_id) if paper_id else None

        if entry is None:
            results.append({"paper_id": paper_id or None, "new_domain": new_domain, "action": "not_found"})
            continue
        if not _DOMAIN_RE.match(new_domain):
            results.append(
                {
                    "paper_id": paper_id,
                    "old_domain": entry.get("domain"),
                    "new_domain": new_domain,
                    "action": "invalid_domain",
                }
            )
            continue

        try:
            confidence = float(raw.get("confidence", 0.9))
        except (TypeError, ValueError):
            confidence = 0.9
        confidence = max(0.0, min(1.0, confidence))
        canonical = new_domain.replace(" ", "_")
        proposed = bool(raw.get("proposed", canonical not in config.domains and canonical != "unclassified"))

        result, dirty = _decide_and_apply(
            root=root,
            registry=registry,
            config=config,
            entry=entry,
            new_domain=canonical,
            confidence=confidence,
            proposed=proposed,
            source="agent",
            allow_new_domains=allow_new_domains,
            min_confidence=min_confidence,
            apply=apply,
        )
        config_dirty = config_dirty or dirty
        results.append(result)

    if config_dirty:
        _persist_domains(root, config)
    _run_vigil(root, "verify")
    return results


def _decide_and_apply(
    *,
    root: Path,
    registry: Registry,
    config: Config,
    entry: dict[str, Any],
    new_domain: str,
    confidence: float,
    proposed: bool,
    source: str,
    allow_new_domains: bool,
    min_confidence: float,
    apply: bool,
) -> tuple[dict[str, Any], bool]:
    paper_id = str(entry.get("paper_id"))
    old_domain = str(entry.get("domain") or "unclassified")
    result: dict[str, Any] = {
        "paper_id": paper_id,
        "old_domain": old_domain,
        "new_domain": new_domain,
        "confidence": round(confidence, 3),
        "proposed": proposed,
        "source": source,
        "action": "unchanged",
    }

    if new_domain == old_domain:
        return result, False
    if new_domain == "unclassified":
        result["action"] = "left_unclassified"
        return result, False
    if confidence < min_confidence:
        result["action"] = "low_confidence"
        result["new_domain"] = old_domain
        return result, False
    if proposed and not allow_new_domains:
        result["action"] = "proposal_disallowed"
        result["new_domain"] = old_domain
        return result, False
    if not apply:
        result["action"] = "would_reassign"
        return result, False

    config_dirty = False
    if proposed and new_domain not in config.domains:
        config.domains.append(new_domain)  # in-place: keeps later decisions consistent
        config_dirty = True
        (root / "nigredo" / new_domain).mkdir(parents=True, exist_ok=True)

    _apply_reassignment(root, registry, entry, new_domain, confidence, proposed)
    result["action"] = "reassigned"
    return result, config_dirty


def _select_entries(registry: Registry, scope: str) -> list[dict[str, Any]]:
    normalized = (scope or "unclassified").strip()
    if normalized == "all":
        return registry.list()
    return registry.list_by_domain(normalized)


def _classification_signal(root: Path, entry: dict[str, Any]) -> tuple[str, str, str]:
    title = str(entry.get("title") or "").strip()
    abstract = ""
    context_parts: list[str] = []

    library_rel = (entry.get("paths") or {}).get("library")
    record = load_yaml_tolerant(root / library_rel) if library_rel else None
    if record is None:
        record = load_yaml_tolerant(root / "albedo" / "library" / f"{entry.get('paper_id')}.yaml")

    if isinstance(record, dict):
        source = record.get("source") if isinstance(record.get("source"), dict) else {}
        title = title or str(source.get("title") or "").strip()
        abstract = str(source.get("abstract") or "").strip()
        for claim in record.get("claims", [])[:6]:
            if isinstance(claim, dict):
                text = str(claim.get("statement") or "").strip()
                if text:
                    context_parts.append(text)
        tags = record.get("tags")
        if isinstance(tags, list):
            context_parts.extend(str(tag) for tag in tags if isinstance(tag, str))

    entry_tags = entry.get("tags")
    if isinstance(entry_tags, list):
        context_parts.extend(str(tag) for tag in entry_tags if isinstance(tag, str))

    context_text = " ".join(context_parts)[:4000]
    return title, abstract, context_text


def _apply_reassignment(
    root: Path,
    registry: Registry,
    entry: dict[str, Any],
    new_domain: str,
    confidence: float,
    proposed: bool,
) -> None:
    paper_id = str(entry.get("paper_id"))
    paths = dict(entry.get("paths") or {})
    pdf_rel = paths.get("pdf")
    notes = list(entry.get("processing_notes") or [])

    if pdf_rel and (root / pdf_rel).exists():
        destination = common.move_to_domain(root / pdf_rel, root / "nigredo" / new_domain)
        paths["pdf"] = str(destination.relative_to(root))
        new_filename = destination.name
    else:
        notes.append(f"reclassify: source PDF missing at {pdf_rel!r}; domain updated without move.")
        new_filename = entry.get("filename")

    origin = "proposed new domain" if proposed else "reassigned"
    notes.append(f"reclassify: {entry.get('domain')} -> {new_domain} ({origin}, confidence={round(confidence, 3)}).")

    fields = {
        "domain": new_domain,
        "domain_confidence": round(confidence, 3),
        "paths": paths,
        "processing_notes": notes,
    }
    if new_filename:
        fields["filename"] = new_filename
    registry.update(paper_id, fields)


def _persist_domains(root: Path, config: Config) -> None:
    config_path = root / "azoth.config.yaml"
    on_disk = load_config(path=config_path)
    merged = list(dict.fromkeys([*on_disk.domains, *config.domains]))
    updated = Config(
        llm=on_disk.llm,
        embeddings=on_disk.embeddings,
        paths=on_disk.paths,
        domains=merged,
        exhaustion=on_disk.exhaustion,
        project_root=str(root),
    )
    save_config(updated, path=config_path)
