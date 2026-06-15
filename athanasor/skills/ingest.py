"""Ingest skill: PDF -> structured record + registry."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..config import Config, load_config
from ..domain_classifier import classify
from ..embeddings import EmbeddingStore
from ..llm import LLMUnavailableError, LLMClient
from ..pdf_parser import parse_pdf
from ..registry import Registry
from ..schemas import validate as validate_schema
from ..skills.common import now_iso, ensure_dir, short_id, slugify, write_yaml
from . import common

import yaml


INGEST_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "SCHEMA.yaml"


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest PDFs into Albedo.")
    parser.add_argument("path", nargs="+", help="PDF file(s) or folder(s)")
    parser.add_argument("--reprocess", action="store_true", help="Reingest even if already in registry.")
    parser.add_argument("--domain-override", dest="domain_override", default=None, help="Optional domain override.")
    return parser


def _run_vigil(root: Path, phase: str) -> tuple[int, str]:
    result = subprocess.run(
        ["python3", str(root / "athanasor" / "vigil" / "verify.py"), phase],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    return result.returncode, (result.stdout + result.stderr)


def _safe_title(parsed: dict[str, Any]) -> str:
    title = (parsed.get("title") or "").strip()
    if title:
        return title
    for line in parsed.get("sections", []):
        txt = (line.get("title") or "").strip()
        if txt:
            return txt
    return parsed.get("filename", "Untitled").replace("_", " ")


def _load_schema_template() -> dict[str, Any]:
    with open(INGEST_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _fallback_extraction(parsed: dict[str, Any], path: Path, title: str, authors: list[str], year: int | None) -> dict[str, Any]:
    abstract = (parsed.get("abstract") or "").strip()
    return {
        "schema_version": 1,
        "id": None,
        "source": {
            "title": title,
            "authors": authors or ["Unknown"],
            "year": year or 0,
            "path": str(path),
            "arxiv": None,
            "doi": None,
            "venue": None,
        },
        "claims": [
            {
                "statement": abstract[:420] or f"Automated ingest found content in {path.name}.",
                "confidence": "demonstrated",
                "evidence": "Full text contains this section summary.",
            }
        ],
        "methods": [
            {
                "name": "automated text parsing",
                "description": "Content was extracted from the PDF with fallback parsing.",
                "domain": "general",
            }
        ],
        "techniques": [],
        "caveats": ["Automated extraction used; review before downstream analysis."],
        "connections_explicit": [],
        "tags": ["ingested", "fallback"],
        "ingestion": {
            "date": now_iso(),
            "agent": "ingest-fallback",
            "schema_version": 1,
            "status": "ingested",
        },
    }


def _extract_with_llm(
    llm: LLMClient | None,
    parsed: dict[str, Any],
    schema: dict[str, Any],
    retry_with_errors: list[str] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    if llm is None:
        return {}, []

    title = _safe_title(parsed)
    raw_text = (parsed.get("full_text") or "")[:18000]
    schema_hint = schema.get("schema_version", 1)
    prompt = (
        "Extract a structured record from this research paper.\n\n"
        f"Paper title: {title}\n\n"
        f"Schema version: {schema_hint}\n\n"
        "Return JSON with the exact structure expected by SCHEMA.yaml.\n\n"
        f"Full paper text:\n{raw_text}"
    )
    if retry_with_errors:
        prompt += "\n\nValidation errors:\n- " + "\n- ".join(retry_with_errors)

    result = llm.complete(
        prompt,
        structured=True,
        schema=schema,
        temperature=0.2,
        max_tokens=4096,
        retry_parse_fail=True,
    )
    if not isinstance(result, dict):
        raise LLMUnavailableError("Structured LLM output not available.")
    result.setdefault("schema_version", 1)
    return result, []


def _validate_and_fix(payload: dict[str, Any], schema: dict[str, Any]) -> tuple[bool, list[str], dict[str, Any], bool]:
    ok, errors, fixed, changed = validate_schema(payload, schema, fix=True)
    if not ok:
        return False, errors, fixed, changed
    return True, [], fixed, changed


def ingest_path(
    target: Path,
    *,
    config: Config | None = None,
    llm: LLMClient | None = None,
    reprocess: bool = False,
    domain_override: str | None = None,
) -> list[dict[str, Any]]:
    config = config or load_config()
    root = Path(config.project_root).expanduser().resolve()
    paths = config.resolved_paths
    nigredo_dir = paths["nigredo"]
    albedo_library = paths["albedo"] / "library"
    registry_path = root / "albedo" / "registry.jsonl"

    ensure_dir(albedo_library)
    registry = Registry(registry_path)
    ensure_dir(nigredo_dir)
    embedding_path = root / config.embeddings["store_path"]
    store = EmbeddingStore(embedding_path, model_name=config.embeddings.get("model", "all-MiniLM-L6-v2"))

    if not target.exists():
        return []

    files = _gather_files(target)
    if not files:
        return []

    _run_vigil(root, "start")

    schema = _load_schema_template()
    outputs: list[dict[str, Any]] = []
    for file_path in files:
        parsed = parse_pdf(file_path)
        if parsed.get("encrypted") or parsed.get("image_only"):
            # skip but keep a trace in warnings.
            continue

        src_title = _safe_title(parsed)
        if not src_title:
            src_title = file_path.stem.replace("_", " ")

        # domain classification
        classification = classify(
            title=src_title,
            abstract=parsed.get("abstract"),
            llm=llm,
            config=config,
        )
        domain = domain_override or classification.domain
        domain_conf = float(classification.confidence or 0.0)
        if domain_conf < 0.6:
            domain = "unclassified"
        if domain not in {"physics", "ML", "philosophy", "neuroscience", "mathematics", "unclassified"}:
            domain = "unclassified"

        domain_dir = nigredo_dir / domain
        destination_pdf = common.move_to_domain(file_path, domain_dir, filename=file_path.name)
        parsed["path"] = str(destination_pdf)

        authors = _extract_authors(parsed.get("full_text", ""))
        year = _extract_year(parsed.get("full_text", ""))
        paper_id = f"{slugify(src_title)}_{short_id(destination_pdf.name)}"

        # If already exists and no reprocess, skip.
        if registry.exists(paper_id) and not reprocess:
            continue

        if llm is not None:
            try:
                raw_payload, _ = _extract_with_llm(llm, parsed, schema)
                ok, errors, fixed, _ = _validate_and_fix(raw_payload, schema)
                if not ok:
                    raw_payload, _ = _extract_with_llm(llm, parsed, schema, retry_with_errors=errors)
                    ok, errors, fixed, _ = _validate_and_fix(raw_payload, schema)
                payload = fixed
                parse_errors = [] if ok else errors
            except Exception as exc:
                payload = _fallback_extraction(
                    parsed=parsed,
                    path=destination_pdf,
                    title=src_title,
                    authors=authors,
                    year=year,
                )
                parse_errors = [str(exc)]
        else:
            payload = _fallback_extraction(
                parsed=parsed,
                path=destination_pdf,
                title=src_title,
                authors=authors,
                year=year,
            )
            parse_errors = ["LLM unavailable"]

        payload["id"] = paper_id
        payload["source"]["title"] = src_title
        payload["source"]["path"] = str(destination_pdf)
        payload["source"]["page_count"] = parsed.get("page_count")
        payload["source"]["year"] = year or 0
        payload["claims"] = payload.get("claims", [])
        payload["tags"] = payload.get("tags") or []
        if "ingestion" not in payload:
            payload["ingestion"] = {}
        payload["ingestion"]["date"] = now_iso()
        payload["ingestion"]["agent"] = "azoth-ingest"
        payload["ingestion"]["schema_version"] = schema.get("schema_version", 1)
        if parse_errors:
            payload.setdefault("parse_errors", parse_errors)

        library_path = albedo_library / f"{paper_id}.yaml"
        write_yaml(library_path, payload)

        for idx, claim in enumerate(payload.get("claims", []), start=1):
            text = claim.get("statement")
            if text:
                store.add(f"{paper_id}_claim_{idx}", str(text))
        for idx, method in enumerate(payload.get("methods", []), start=1):
            store.add(
                f"{paper_id}_method_{idx}",
                str(method.get("name", "")) + " " + str(method.get("description", "")),
            )
        for idx, technique in enumerate(payload.get("techniques", []), start=1):
            store.add(
                f"{paper_id}_technique_{idx}",
                str(technique.get("name", "")) + " " + str(technique.get("description", "")),
            )
        store.save()

        tags = payload.get("tags", [])
        entry = {
            "paper_id": paper_id,
            "filename": destination_pdf.name,
            "domain": domain,
            "domain_confidence": round(domain_conf, 3),
            "title": src_title,
            "authors": authors,
            "year": year,
            "ingested": now_iso(),
            "exhausted_at_depth": None,
            "connected": False,
            "detected": False,
            "drafted": False,
            "triaged": False,
            "status": "ingested_only",
            "paths": {
                "library": str(library_path.relative_to(root)),
                "pdf": str(destination_pdf.relative_to(root)),
                "exhaust": f"albedo/exhaust/{paper_id}_exhaust.yaml",
            },
            "processing_notes": parse_errors or [],
            "title": src_title,
            "source": payload.get("source"),
            "tags": tags,
            "secondary_domains": [],
        }
        if registry.exists(paper_id):
            registry.update(paper_id, {"status": "ingested_only", **entry})
        else:
            registry.add(entry)

        outputs.append(entry)

    _run_vigil(root, "verify")
    return outputs


def _gather_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target] if target.suffix.lower() == ".pdf" else []
    files: list[Path] = []
    for ext in ("*.pdf",):
        files.extend(sorted(target.rglob(ext)))
    return sorted(files)


def _extract_year(text: str) -> int | None:
    for token in text.replace("\n", " ").split(" "):
        if len(token) == 4 and token.isdigit():
            year = int(token)
            if 1900 <= year <= 2100:
                return year
    return None


def _extract_authors(text: str) -> list[str]:
    first_lines = text.splitlines()[:25]
    joined = " ".join(line.strip() for line in first_lines if line.strip())
    if " - " in joined and not joined.endswith("-"):
        candidate = joined.split(" - ")[1][:120]
        names = [name.strip() for name in candidate.split(",") if name.strip()]
        if names:
            return names[:4]
    return ["Unknown"]
