#!/usr/bin/env python3
"""Audit the tracked public tree for private/runtime artifacts."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

RUNTIME_PREFIXES = (
    "albedo/",
    "citrinitas/",
    "rubedo/",
    "athanasor/vigil/reports/",
    "nigredo/",
)
RUNTIME_EXACT = {
    "athanasor/lapis/state.json",
    "athanasor/lapis/codex.md",
}
ABSOLUTE_PATTERNS = (
    re.compile(rb"/Users/[^\s`\"']+"),
    re.compile(rb"[A-Za-z]:\\Users\\[^\s`\"']+"),
)
PILOT_ID_PATTERNS = (
    re.compile(rb"orcid[0-9]{8,}_[0-9]{6,}"),
    re.compile(rb"loopedworldmodels_[0-9]{6,}"),
    re.compile(rb"paper_(?![0-9a-f]{16}\b)[0-9]{6,}\b"),
)
FALLBACK_DUMP_PATTERNS = (
    re.compile(rb"LLM unavailable; fallback connection", re.IGNORECASE),
    re.compile(rb'"tags"\s*:\s*\[[^\]]*"fallback"', re.IGNORECASE),
)
PATTERN_LITERAL_FILES = {
    "scripts/check_public_tree.py",
}
PATTERN_LITERAL_PREFIXES = ("tests/", "docs/superpowers/plans/")
BENCHMARK_PREFIX = "benchmarks/operations-decision-support-v1/"
BENCHMARK_SYNTHETIC_PREFIX = f"{BENCHMARK_PREFIX}synthetic/"
BENCHMARK_ARCHIVE_SUFFIXES = {".pdf", ".zip", ".tar", ".gz", ".docx"}
BENCHMARK_GOLD_KEY = re.compile(
    rb"(?m)(?:^|[{\n,])\s*[\"']?(?:anchor_pair_ids|canonical_pairs|evidence_spans|freeze|"
    rb"gold_pairs|gold_label|gold_rationale|gold_evidence_spans|label|presentations"
    rb")[\"']?\s*:"
)
BENCHMARK_RATIONALE_KEY = re.compile(
    rb"(?m)(?:^|[{\n,])\s*[\"']?rationale[\"']?\s*:"
)
BENCHMARK_RATIONALE_ALLOWED_PATHS = {
    f"{BENCHMARK_PREFIX}selection-log.yaml",
}
TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".jsonl",
    ".txt",
}
DATA_SUFFIXES = {".yaml", ".yml", ".json", ".jsonl"}


def tracked_paths(repo_root: Path = REPO_ROOT) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )
    return sorted(item.decode("utf-8") for item in result.stdout.split(b"\0") if item)


def audit_paths(paths: list[str], read_bytes: Callable[[str], bytes]) -> list[str]:
    findings: list[str] = []
    for rel in paths:
        normalized = rel.replace("\\", "/")
        suffix = Path(normalized).suffix.lower()
        is_benchmark = normalized.startswith(BENCHMARK_PREFIX)
        is_synthetic = normalized.startswith(BENCHMARK_SYNTHETIC_PREFIX)
        if suffix == ".pdf":
            findings.append(f"{rel}: tracked PDF")
        if is_benchmark and suffix in BENCHMARK_ARCHIVE_SUFFIXES:
            findings.append(f"{rel}: benchmark source archive")
        if is_benchmark and suffix == ".txt":
            findings.append(f"{rel}: benchmark source text")
        if (
            is_benchmark
            and not is_synthetic
            and Path(normalized).name.casefold().startswith("gold.")
        ):
            findings.append(f"{rel}: benchmark gold material")
        if normalized in RUNTIME_EXACT or normalized.startswith(RUNTIME_PREFIXES):
            findings.append(f"{rel}: tracked runtime artifact")
        if suffix not in TEXT_SUFFIXES:
            continue
        data = read_bytes(rel)
        if (
            is_benchmark
            and not is_synthetic
            and suffix in DATA_SUFFIXES
            and (
                BENCHMARK_GOLD_KEY.search(data)
                or (
                    normalized not in BENCHMARK_RATIONALE_ALLOWED_PATHS
                    and BENCHMARK_RATIONALE_KEY.search(data)
                )
            )
            and f"{rel}: benchmark gold material" not in findings
        ):
            findings.append(f"{rel}: benchmark gold material")
        if normalized in PATTERN_LITERAL_FILES or normalized.startswith(
            PATTERN_LITERAL_PREFIXES
        ):
            continue
        if any(pattern.search(data) for pattern in ABSOLUTE_PATTERNS):
            findings.append(f"{rel}: absolute user path")
        if any(pattern.search(data) for pattern in PILOT_ID_PATTERNS):
            findings.append(f"{rel}: pilot identifier")
        if suffix in DATA_SUFFIXES and any(
            pattern.search(data) for pattern in FALLBACK_DUMP_PATTERNS
        ):
            findings.append(f"{rel}: fallback runtime dump")
    return findings


def audit_repository(repo_root: Path = REPO_ROOT) -> list[str]:
    paths = tracked_paths(repo_root)
    return audit_paths(paths, lambda rel: (repo_root / rel).read_bytes())


def main() -> int:
    findings = audit_repository()
    if findings:
        print("Public tree audit: FAIL")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print("Public tree audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
