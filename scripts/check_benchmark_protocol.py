#!/usr/bin/env python3
"""Audit the public benchmark freeze and optional private frozen inputs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from athanasor.benchmark.freeze import (  # noqa: E402
    ensure_outside_repository,
    gold_commitment,
    validate_gold_packet,
)
from athanasor.benchmark.protocol import (  # noqa: E402
    BenchmarkProtocolError,
    load_mapping,
    validate_public_bundle,
    validate_source_directory,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--benchmark-root",
        required=True,
        type=Path,
        help="Public benchmark bundle directory.",
    )
    parser.add_argument(
        "--private-gold",
        type=Path,
        help="Private reconciled gold packet outside the repository.",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        help="Private fetched source directory outside the repository.",
    )
    parser.add_argument(
        "--repo-root",
        required=True,
        type=Path,
        help="Repository root used to enforce the private-data boundary.",
    )
    return parser


def _require_directory(path: Path, description: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        raise BenchmarkProtocolError(f"{description} is not a readable directory: {path}")
    return resolved


def _require_file(path: Path, description: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise BenchmarkProtocolError(f"{description} is not a readable file: {path}")
    return resolved


def _private_arguments(
    private_gold: Path | None, source_dir: Path | None
) -> tuple[Path, Path] | None:
    if (private_gold is None) != (source_dir is None):
        raise BenchmarkProtocolError(
            "--private-gold and --source-dir must be provided together"
        )
    if private_gold is None or source_dir is None:
        return None
    return private_gold, source_dir


def main() -> int:
    args = build_parser().parse_args()
    mode = "public"
    try:
        benchmark_root = _require_directory(args.benchmark_root, "benchmark root")
        repo_root = _require_directory(args.repo_root, "repository root")
        private_inputs = _private_arguments(args.private_gold, args.source_dir)
        errors = validate_public_bundle(benchmark_root)

        if private_inputs is not None:
            private_gold, source_dir = private_inputs
            private_gold = ensure_outside_repository(private_gold, repo_root)
            source_dir = ensure_outside_repository(source_dir, repo_root)
            private_gold = _require_file(private_gold, "private gold")
            source_dir = _require_directory(source_dir, "source directory")

            sources = load_mapping(benchmark_root / "sources.yaml")
            protocol = load_mapping(benchmark_root / "protocol.yaml")
            gold = load_mapping(private_gold)
            public_freeze = load_mapping(benchmark_root / "freeze-manifest.json")

            errors.extend(validate_source_directory(sources, source_dir))
            errors.extend(validate_gold_packet(gold, sources, protocol))
            try:
                actual_commitment = gold_commitment(gold)
            except BenchmarkProtocolError as exc:
                errors.append(f"/private_gold_commitment: {exc}")
            else:
                if actual_commitment != public_freeze.get("private_gold_commitment"):
                    errors.append(
                        "/private_gold_commitment: private gold digest does not match "
                        "public commitment"
                    )
            mode = "public+private"
    except BenchmarkProtocolError as exc:
        print(f"Benchmark protocol audit: ERROR: {exc}")
        return 2

    if errors:
        print(f"Benchmark protocol audit: FAIL mode={mode}")
        for error in sorted(dict.fromkeys(errors)):
            print(f"- {error}")
        return 1

    print(f"Benchmark protocol audit: PASS mode={mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
