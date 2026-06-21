"""Ouroboros skill: turn rejected prior art into Nigredo expansion queues."""

from __future__ import annotations

import argparse
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from ..config import Config
from ..skills.common import now_iso, short_id, slugify, write_yaml
from .rubedo_common import load_yaml, project_root, relpath, run_optional_vigil


DEFAULT_IMPACTS = ["direct_prior_art", "related_prior_art"]
DownloadResult = dict[str, Any]
Downloader = Callable[[str, Path, float], DownloadResult]


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Expand rejected Rubedo prior art into Nigredo.")
    parser.add_argument("cluster_id", help="Hypothesis cluster id.")
    parser.add_argument("--download", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-impact", action="append", default=None)
    parser.add_argument("--max-sources", type=int, default=8)
    return parser


def run_ouroboros(
    cluster_id: str,
    *,
    config: Config | None = None,
    download: bool = True,
    include_impacts: list[str] | tuple[str, ...] | None = None,
    max_sources: int = 8,
    downloader: Downloader | None = None,
) -> Path:
    """Build a bounded expansion queue from a rejected prior-art artifact."""
    if max_sources < 1:
        raise ValueError("max_sources must be >= 1")

    root = project_root(config)
    run_optional_vigil(root, "start", "ouroboros")

    prior_path = root / "rubedo" / "prior_art" / f"{cluster_id}.yaml"
    prior_art = load_yaml(prior_path)
    if prior_art is None:
        raise FileNotFoundError(f"Prior-art artifact not found: {prior_path}")
    if not _is_rejected_prior_art(prior_art):
        raise ValueError("Ouroboros requires a rejected prior-art artifact.")

    impacts = list(include_impacts) if include_impacts else list(DEFAULT_IMPACTS)
    sources = _filtered_sources(prior_art, impacts, max_sources)
    items: list[dict[str, Any]] = []
    downloader = downloader or _download_pdf

    for index, source in enumerate(sources, start=1):
        item = _queue_item(source, index)
        resolved = item.get("resolved_url")
        if not resolved:
            item["status"] = "manual_required"
            item["reason"] = "URL is not a safe direct PDF/arXiv source."
            items.append(item)
            continue

        if not download:
            item["status"] = "queued"
            item["reason"] = "Download disabled; source queued for later ingestion."
            items.append(item)
            continue

        target_path = _target_path(root, source, resolved)
        try:
            result = downloader(str(resolved), target_path, 30)
        except Exception as exc:
            item["status"] = "failed"
            item["reason"] = f"Download failed: {exc}"
            item["target_path"] = relpath(root, target_path)
            items.append(item)
            continue

        ok = bool(result.get("ok", True)) if isinstance(result, dict) else True
        if ok and target_path.exists():
            item["status"] = "downloaded"
            item["reason"] = "Safe source downloaded into Nigredo inbox."
            item["target_path"] = relpath(root, target_path)
            if isinstance(result, dict):
                item["bytes"] = result.get("bytes", target_path.stat().st_size)
        else:
            item["status"] = "failed"
            item["reason"] = "Downloader did not produce a target PDF."
            item["target_path"] = relpath(root, target_path)
        items.append(item)

    expansion = {
        "schema_version": 1,
        "artifact_type": "nigredo_ouroboros_expansion",
        "cluster_id": cluster_id,
        "generated_at": now_iso(),
        "source_artifact": relpath(root, prior_path),
        "download_enabled": download,
        "included_impacts": impacts,
        "max_sources": max_sources,
        "items": items,
        "next_commands": [
            "azoth ingest nigredo/inbox/",
            "azoth awaken ML --depth 3 --count 8",
            "azoth connect --within ML --reanalyze-depth-upgrades",
            "azoth detect --domain ML",
        ],
    }
    report = _report_payload(cluster_id, prior_path, expansion)

    out_dir = root / "nigredo" / "ouroboros"
    expansion_path = out_dir / f"{cluster_id}_expansion.yaml"
    report_path = out_dir / f"{cluster_id}_report.yaml"
    write_yaml(expansion_path, expansion)
    write_yaml(report_path, report)
    run_optional_vigil(root, "verify", "ouroboros")
    return expansion_path


def resolve_source_url(url: str) -> str | None:
    """Resolve safe source URLs to ingest-ready PDF URLs."""
    parsed = urlparse(str(url).strip())
    if not parsed.scheme or not parsed.netloc:
        return None

    host = parsed.netloc.lower()
    path = parsed.path.strip("/")
    if host.endswith("arxiv.org"):
        for prefix in ("abs/", "html/"):
            if path.startswith(prefix):
                paper_id = path.removeprefix(prefix).strip("/")
                if paper_id:
                    return f"https://arxiv.org/pdf/{paper_id}.pdf"

    if parsed.path.lower().endswith(".pdf"):
        return url
    return None


def _is_rejected_prior_art(payload: dict[str, Any]) -> bool:
    if payload.get("artifact_type") != "rubedo_prior_art":
        return False
    decision = str(payload.get("decision", "")).strip().lower()
    assessment = payload.get("assessment") if isinstance(payload.get("assessment"), dict) else {}
    novelty = str(assessment.get("novelty_result", "")).strip().lower()
    return decision in {"reject_novelty_claim", "rejected"} or novelty == "rejected"


def _filtered_sources(payload: dict[str, Any], impacts: list[str], max_sources: int) -> list[dict[str, Any]]:
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise ValueError("Prior-art artifact must contain a sources list.")
    wanted = set(impacts)
    filtered = [
        source
        for source in sources
        if isinstance(source, dict) and str(source.get("impact", "")).strip() in wanted
    ]
    return filtered[:max_sources]


def _queue_item(source: dict[str, Any], index: int) -> dict[str, Any]:
    url = str(source.get("url", "")).strip()
    resolved = resolve_source_url(url) if url else None
    return {
        "source_index": index,
        "title": str(source.get("title", "")).strip() or f"source-{index}",
        "url": url,
        "resolved_url": resolved,
        "impact": str(source.get("impact", "")).strip() or "unspecified",
        "status": "queued",
        "reason": "Queued for expansion.",
        "finding": source.get("finding"),
    }


def _target_path(root: Path, source: dict[str, Any], resolved_url: str) -> Path:
    title = str(source.get("title", "")).strip() or Path(urlparse(resolved_url).path).stem
    suffix = short_id(resolved_url)
    filename = f"{slugify(title, fallback='prior-art')}_{suffix}.pdf"
    target = root / "nigredo" / "inbox" / filename
    if not target.exists():
        return target
    stem = target.stem
    for idx in range(2, 1000):
        candidate = target.with_name(f"{stem}_{idx}{target.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not allocate target filename for {target}")


def _download_pdf(url: str, target_path: Path, timeout: float = 30) -> DownloadResult:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "Azoth-Ouroboros/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = str(response.headers.get("Content-Type", "")).lower()
            data = response.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc)) from exc

    if not (url.lower().split("?")[0].endswith(".pdf") or "pdf" in content_type or data.startswith(b"%PDF")):
        raise RuntimeError(f"Response is not PDF-like: content-type={content_type or 'unknown'}")

    target_path.write_bytes(data)
    return {"ok": True, "bytes": len(data), "content_type": content_type}


def _report_payload(cluster_id: str, prior_path: Path, expansion: dict[str, Any]) -> dict[str, Any]:
    items = [item for item in expansion.get("items", []) if isinstance(item, dict)]
    root = prior_path.parents[2]
    counts = {
        "downloaded_count": sum(1 for item in items if item.get("status") == "downloaded"),
        "queued_count": sum(1 for item in items if item.get("status") == "queued"),
        "manual_required_count": sum(1 for item in items if item.get("status") == "manual_required"),
        "failed_count": sum(1 for item in items if item.get("status") == "failed"),
    }
    return {
        "schema_version": 1,
        "artifact_type": "nigredo_ouroboros_report",
        "cluster_id": cluster_id,
        "generated_at": expansion.get("generated_at"),
        "source_artifact": relpath(root, prior_path),
        "total_sources": len(items),
        **counts,
        "next_command": "azoth ingest nigredo/inbox/",
    }
