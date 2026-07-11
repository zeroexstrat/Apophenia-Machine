#!/usr/bin/env python3
"""Scrub personal-data-shaped titles from Azoth artifacts.

Fallback ingestion (no LLM) extracts a paper's "title" from the first lines of a
PDF, which are often front matter: author names, ORCIDs, emails, and mailing
addresses. Those junk titles are then echoed by ``azoth status`` and stored in the
registry, library, and exhaust records. This tool detects them and replaces each
with a deterministic, non-PII placeholder; PII embedded inside claim text is
redacted in place.

Redaction-safe: ``--report`` prints paper_ids and matched rule names only, never
the raw PII text, so running it does not re-surface personal data.

Usage:
  python3 scripts/scrub_pii_titles.py --report            # dry run, redacted summary
  python3 scripts/scrub_pii_titles.py --apply             # rewrite artifacts in place
  python3 scripts/scrub_pii_titles.py --apply --json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

# Ordered (name, pattern). A title matching any is treated as PII/junk and replaced.
# The same patterns redact PII spans inside free text (claims, evidence).
PII_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("orcid", re.compile(r"orcid|\b\d{4}-?\d{4}-?\d{4}-?\d{3}[\dxX]\b|\b\d{16}\b", re.IGNORECASE)),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    (
        "address",
        re.compile(
            r"\bRue\b|\bStra(?:ss|ß)e\b|\bAvenue\b|\bBoulevard\b|independent researcher|\b\d{5}\s+[A-Z][a-z]+",
            re.IGNORECASE,
        ),
    ),
    ("author_frag", re.compile(r"\bet\s+al\b|edited by", re.IGNORECASE)),
    ("ocr_junk", re.compile(r"(?:\b[A-Za-z]\s){4,}")),
)

# Span-level patterns (only the genuinely sensitive spans get cut from free text).
_STREET_SUFFIX = r"(?:Avenue|Ave|Street|St|Rue|Boulevard|Blvd|Road|Rd|Lane|Ln|Drive|Dr|Way|Court|Ct)"
_REDACT_SPANS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b\d{4}-?\d{4}-?\d{4}-?\d{3}[\dxX]\b"),
    re.compile(r"\b\d{16}\b"),
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    re.compile(r"\b\d{5}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*"),  # 12345 Town Name
    # street address, with or without a leading number: "77 Massachusetts Avenue", "Rue des Lavandières"
    re.compile(rf"\b(?:\d{{1,5}}\s+)?(?:[A-Z][A-Za-z.]+\s+){{1,4}}{_STREET_SUFFIX}\b\.?"),
    re.compile(rf"\b\d{{1,5}}\s+(?:[A-Z][A-Za-z.]+\s+){{0,4}}{_STREET_SUFFIX}\b\.?"),
    re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,?\s+[A-Z]{2}\s+\d{5}(?:-\d{4})?\b"),  # City, ST 12345
)


def matched_rules(text: Any) -> list[str]:
    if not isinstance(text, str) or not text.strip():
        return []
    names = [name for name, pattern in PII_RULES if pattern.search(text)]
    # Any genuine structured PII span (e.g. "City, ST 02139") counts as an address
    # even if the coarse rules missed it — keeps title detection a superset of the
    # strict span verifier, so nothing the verifier flags survives scrubbing.
    if "address" not in names and _has_pii_span(text):
        names.append("address")
    return names


def title_is_pii(text: Any) -> bool:
    return bool(matched_rules(text))


def _has_pii_span(text: Any) -> bool:
    if not isinstance(text, str):
        return False
    return any(pattern.search(text) for pattern in _REDACT_SPANS)


def redact_spans(text: Any) -> str:
    if not isinstance(text, str):
        return text
    out = text
    for pattern in _REDACT_SPANS:
        out = pattern.sub("[redacted]", out)
    return out


def has_pii_span(text: Any) -> bool:
    """Strict check for genuine PII structure in free text.

    Unlike the broad title detector, this does NOT fire on the common word
    "avenue"/"boulevard" — only on real ORCIDs, emails, and structured addresses.
    Used to verify no personal data survives inside claims/evidence.
    """
    return _has_pii_span(text)


def placeholder(paper_id: str, domain: str | None) -> str:
    """A stable, non-PII replacement title.

    Derived from a fresh hash of the paper_id (never the id's PII-bearing prefix),
    so no personal-data fragment leaks through.
    """
    tag = hashlib.sha1(str(paper_id).encode("utf-8")).hexdigest()[:8]
    dom = (domain or "").strip() or "unclassified"
    return f"Untitled {dom} paper {tag}"


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None


def scrub(root: Path | str, *, apply: bool = False) -> dict[str, Any]:
    root = Path(root)
    stats: Counter[str] = Counter()
    flagged_ids: dict[str, list[str]] = {}
    rule_hits: Counter[str] = Counter()

    # Resolve one placeholder per paper_id (needs domain from the registry).
    registry_path = root / "albedo" / "registry.jsonl"
    domains: dict[str, str] = {}
    if registry_path.exists():
        for line in registry_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict) and entry.get("paper_id"):
                domains[str(entry["paper_id"])] = str(entry.get("domain") or "unclassified")

    def title_replacement(paper_id: str) -> str:
        return placeholder(paper_id, domains.get(paper_id))

    # 1) registry.jsonl — title and source.title
    if registry_path.exists():
        lines_out: list[str] = []
        changed = False
        for line in registry_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                lines_out.append(line)
                continue
            pid = str(entry.get("paper_id") or "")
            hits = matched_rules(entry.get("title"))
            src = entry.get("source") if isinstance(entry.get("source"), dict) else None
            src_hits = matched_rules(src.get("title")) if src else []
            if hits or src_hits:
                flagged_ids.setdefault(pid, [])
                for r in set(hits + src_hits):
                    rule_hits[r] += 1
                    if r not in flagged_ids[pid]:
                        flagged_ids[pid].append(r)
                repl = title_replacement(pid)
                if hits:
                    entry["title"] = repl
                    stats["titles_scrubbed"] += 1
                if src_hits and src is not None:
                    src["title"] = repl
                    entry["source"] = src
                changed = True
            lines_out.append(json.dumps(entry))
        if changed and apply:
            registry_path.write_text("\n".join(lines_out) + "\n", encoding="utf-8")

    # 2) library/*.yaml — source.title (replace) + claim statements (redact spans)
    lib_dir = root / "albedo" / "library"
    if lib_dir.exists():
        for path in sorted(lib_dir.glob("*.yaml")):
            payload = _load_yaml(path)
            if not isinstance(payload, dict):
                continue
            pid = str(payload.get("id") or path.stem)
            changed = False
            src = payload.get("source")
            if isinstance(src, dict) and matched_rules(src.get("title")):
                src["title"] = title_replacement(pid)
                changed = True
            for claim in payload.get("claims", []) or []:
                if isinstance(claim, dict):
                    stmt = claim.get("statement")
                    red = redact_spans(stmt)
                    if red != stmt:
                        claim["statement"] = red
                        stats["claims_redacted"] += 1
                        changed = True
            if changed:
                stats["library_files_changed"] += 1
                if apply:
                    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    # 3) exhaust/*_exhaust.yaml — exhaustion.paper_title
    exh_dir = root / "albedo" / "exhaust"
    if exh_dir.exists():
        for path in sorted(exh_dir.glob("*_exhaust.yaml")):
            payload = _load_yaml(path)
            if not isinstance(payload, dict):
                continue
            meta = payload.get("exhaustion")
            if isinstance(meta, dict) and matched_rules(meta.get("paper_title")):
                pid = str(meta.get("paper_id") or path.stem.replace("_exhaust", ""))
                meta["paper_title"] = title_replacement(pid)
                stats["exhaust_titles_scrubbed"] += 1
                if apply:
                    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    # 4) rubedo/triage/*.yaml — evidence_table[].title
    triage_dir = root / "rubedo" / "triage"
    if triage_dir.exists():
        for path in sorted(triage_dir.rglob("*.yaml")):
            payload = _load_yaml(path)
            if not isinstance(payload, dict):
                continue
            changed = False
            for row in payload.get("evidence_table", []) or []:
                if isinstance(row, dict) and matched_rules(row.get("title")):
                    row["title"] = title_replacement(str(row.get("paper_id") or ""))
                    changed = True
            if changed:
                stats["triage_titles_scrubbed"] += 1
                if apply:
                    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    # 5) embeddings.json (local, gitignored) — redact PII spans in stored texts
    emb_path = root / "athanasor" / "embeddings.json"
    if emb_path.exists():
        try:
            emb = json.loads(emb_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            emb = None
        if isinstance(emb, dict) and isinstance(emb.get("texts"), dict):
            changed = False
            for key, value in list(emb["texts"].items()):
                red = redact_spans(value)
                if red != value:
                    emb["texts"][key] = red
                    stats["embedding_texts_redacted"] += 1
                    changed = True
            if changed and apply:
                emb_path.write_text(json.dumps(emb, indent=2), encoding="utf-8")

    return {
        "applied": apply,
        "titles_scrubbed": stats["titles_scrubbed"],
        "exhaust_titles_scrubbed": stats["exhaust_titles_scrubbed"],
        "library_files_changed": stats["library_files_changed"],
        "claims_redacted": stats["claims_redacted"],
        "triage_titles_scrubbed": stats["triage_titles_scrubbed"],
        "embedding_texts_redacted": stats["embedding_texts_redacted"],
        "flagged_papers": len(flagged_ids),
        "rule_breakdown": dict(rule_hits),
        "flagged_paper_ids": sorted(flagged_ids),  # ids only — never the raw titles
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scrub PII-shaped titles from Azoth artifacts.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="Project root (default: repo root).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--report", action="store_true", help="Dry run; redacted summary only (default).")
    mode.add_argument("--apply", action="store_true", help="Rewrite artifacts in place.")
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    args = parser.parse_args(argv)

    report = scrub(args.root, apply=args.apply)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    verb = "Scrubbed" if args.apply else "Would scrub"
    print(f"{verb} {report['titles_scrubbed']} registry title(s) across {report['flagged_papers']} paper(s).")
    print(f"  rule breakdown: {report['rule_breakdown']}")
    print(f"  exhaust titles: {report['exhaust_titles_scrubbed']}, library files: {report['library_files_changed']}, "
          f"claims redacted: {report['claims_redacted']}, triage: {report['triage_titles_scrubbed']}, "
          f"embeddings: {report['embedding_texts_redacted']}")
    if not args.apply:
        print("  (report mode — nothing written; re-run with --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
