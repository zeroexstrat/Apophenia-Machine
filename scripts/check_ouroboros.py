#!/usr/bin/env python3
"""Focused checks for Ouroboros prior-art expansion."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from athanasor.config import Config
from athanasor.skills.ouroboros import resolve_source_url, run_ouroboros


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"check failed: {message}")
    print(f"[ok] {message}")


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False)


def _read_yaml(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        payload = yaml.safe_load(f)
    if not isinstance(payload, dict):
        raise SystemExit(f"check failed: expected YAML object at {path}")
    return payload


def _config(root: Path) -> Config:
    return Config(
        project_root=str(root),
        paths={
            "project_root": str(root),
            "nigredo": "nigredo",
            "albedo": "albedo",
            "citrinitas": "citrinitas",
            "rubedo": "rubedo",
            "athanasor": "athanasor",
        },
        llm={},
        embeddings={"store_path": "athanasor/embeddings.store"},
        domains=["ML"],
        exhaustion={},
    )


def _fake_downloader(url: str, target_path: Path, timeout: float = 30) -> dict[str, Any]:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(b"%PDF-1.4\nfixture pdf\n")
    return {"ok": True, "bytes": target_path.stat().st_size, "timeout": timeout, "url": url}


def _build_prior_art_fixture(root: Path, cluster_id: str, *, rejected: bool = True) -> None:
    _write_yaml(
        root / "rubedo" / "prior_art" / f"{cluster_id}.yaml",
        {
            "schema_version": 1,
            "artifact_type": "rubedo_prior_art",
            "cluster_id": cluster_id,
            "decision": "reject_novelty_claim" if rejected else "needs_prior_art",
            "assessment": {"novelty_result": "rejected" if rejected else "unknown"},
            "sources": [
                {
                    "title": "Parcae Stable Looped Language Models",
                    "url": "https://arxiv.org/html/2604.12946v1",
                    "impact": "direct_prior_art",
                },
                {
                    "title": "STARS Looped Language Models",
                    "url": "https://arxiv.org/abs/2605.26733v1",
                    "impact": "direct_prior_art",
                },
                {
                    "title": "Direct PDF Fixture",
                    "url": "https://example.org/papers/direct-fixture.pdf",
                    "impact": "related_prior_art",
                },
                {
                    "title": "Manual Proceedings Page",
                    "url": "https://proceedings.mlr.press/v139/kim21i.html",
                    "impact": "foundational_related_prior_art",
                },
            ],
        },
    )


def main() -> int:
    _assert(
        resolve_source_url("https://arxiv.org/abs/2604.12946v1")
        == "https://arxiv.org/pdf/2604.12946v1.pdf",
        "arXiv abs URL resolves to PDF",
    )
    _assert(
        resolve_source_url("https://arxiv.org/html/2605.26733v1")
        == "https://arxiv.org/pdf/2605.26733v1.pdf",
        "arXiv HTML URL resolves to PDF",
    )
    _assert(
        resolve_source_url("https://example.org/papers/direct-fixture.pdf?download=1")
        == "https://example.org/papers/direct-fixture.pdf?download=1",
        "direct PDF URL is accepted",
    )
    _assert(resolve_source_url("https://example.org/landing") is None, "HTML landing page requires manual handling")

    with tempfile.TemporaryDirectory(prefix="azoth-ouroboros-") as tmp:
        root = Path(tmp)
        cluster_id = "cluster_fixture"
        _build_prior_art_fixture(root, cluster_id)
        cfg = _config(root)

        expansion_path = run_ouroboros(
            cluster_id,
            config=cfg,
            download=True,
            include_impacts=["direct_prior_art", "related_prior_art", "foundational_related_prior_art"],
            max_sources=4,
            downloader=_fake_downloader,
        )
        _assert(expansion_path.exists(), "expansion artifact created")
        expansion = _read_yaml(expansion_path)
        _assert(expansion["artifact_type"] == "nigredo_ouroboros_expansion", "expansion artifact typed")
        _assert(len(expansion["items"]) == 4, "expansion includes bounded source items")
        statuses = {item["status"] for item in expansion["items"]}
        _assert("downloaded" in statuses, "safe sources are downloaded")
        _assert("manual_required" in statuses, "unresolved sources remain manual")
        downloaded = [item for item in expansion["items"] if item["status"] == "downloaded"]
        _assert(all((root / item["target_path"]).exists() for item in downloaded), "downloaded PDFs exist in inbox")
        _assert(all(str(item["target_path"]).startswith("nigredo/inbox/") for item in downloaded), "downloads land in nigredo inbox")

        report = _read_yaml(root / "nigredo" / "ouroboros" / f"{cluster_id}_report.yaml")
        _assert(report["downloaded_count"] == len(downloaded), "report counts downloads")
        _assert(report["manual_required_count"] == 1, "report counts manual-required sources")
        _assert(report["source_artifact"] == f"rubedo/prior_art/{cluster_id}.yaml", "report stores portable source artifact path")

    with tempfile.TemporaryDirectory(prefix="azoth-ouroboros-reject-gate-") as tmp:
        root = Path(tmp)
        cluster_id = "cluster_not_rejected"
        _build_prior_art_fixture(root, cluster_id, rejected=False)
        cfg = _config(root)
        try:
            run_ouroboros(cluster_id, config=cfg, download=False)
        except ValueError as exc:
            _assert("rejected" in str(exc).lower(), "non-rejected prior-art artifact is blocked")
        else:
            raise SystemExit("check failed: non-rejected prior-art artifact should not expand")

    print("\nOuroboros checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
