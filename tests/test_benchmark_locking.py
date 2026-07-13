from __future__ import annotations

from pathlib import Path

import pytest

from athanasor.benchmark.artifacts import (
    BenchmarkArtifactError,
    atomic_write_json,
)
from athanasor.benchmark.execution import (
    RUN_IDS,
    adapt_model_responses,
    generate_baseline,
    load_execution_manifest,
)
from athanasor.benchmark.locking import (
    build_lock_manifest,
    seal_lock_tree,
    verify_lock_manifest,
)
from test_benchmark_execution import (
    BENCHMARK_ROOT,
    _model_responses,
    _prepared_fixture,
    _proved_provenance,
)


IMPLEMENTATION_SHA = "cb0957a5848fde37b6c7704330485adc201c04e3"


def _write_lock_inputs(tmp_path: Path) -> tuple[Path, Path, dict[str, Path], dict[str, object]]:
    private_parent = tmp_path / "private-p7"
    private_parent.mkdir(mode=0o700)
    lock_root = private_parent / "lock"
    runs_root = lock_root / "runs"
    runs_root.mkdir(parents=True)
    prepared = _prepared_fixture(tmp_path / "fixture")
    prepared_path = lock_root / "prepared.json"
    atomic_write_json(prepared_path, prepared)
    manifest = load_execution_manifest(BENCHMARK_ROOT / "execution-manifest.yaml")
    run_paths: dict[str, Path] = {}
    model_run = adapt_model_responses(
        prepared, manifest, _model_responses(prepared), _proved_provenance()
    )
    for run_id in RUN_IDS:
        run = model_run if run_id == RUN_IDS[0] else generate_baseline(prepared, manifest, run_id)
        path = runs_root / f"{run_id}.json"
        atomic_write_json(path, run)
        run_paths[run_id] = path
    return lock_root, prepared_path, run_paths, manifest


def _restore_writable(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts)):
        if path.is_dir():
            path.chmod(0o700)
        elif path.is_file():
            path.chmod(0o600)
    root.chmod(0o700)


def test_lock_requires_all_seven_runs_and_exact_prepared_digest(tmp_path: Path) -> None:
    lock_root, prepared_path, run_paths, manifest = _write_lock_inputs(tmp_path)
    run_paths.pop("shared_tag")
    with pytest.raises(BenchmarkArtifactError, match="exact seven run IDs"):
        build_lock_manifest(
            prepared_path,
            run_paths,
            manifest,
            private_root=lock_root,
            benchmark_root=BENCHMARK_ROOT,
            implementation_git_sha=IMPLEMENTATION_SHA,
        )


def test_complete_lock_seals_and_verifies(tmp_path: Path) -> None:
    lock_root, prepared_path, run_paths, manifest = _write_lock_inputs(tmp_path)
    try:
        lock = build_lock_manifest(
            prepared_path,
            run_paths,
            manifest,
            private_root=lock_root,
            benchmark_root=BENCHMARK_ROOT,
            implementation_git_sha=IMPLEMENTATION_SHA,
        )
        atomic_write_json(lock_root / "lock-manifest.json", lock)
        assert verify_lock_manifest(
            lock,
            private_root=lock_root,
            benchmark_root=BENCHMARK_ROOT,
            expected_git_sha=IMPLEMENTATION_SHA,
            require_sealed=False,
        ) == []
        seal_lock_tree(lock_root)
        assert verify_lock_manifest(
            lock,
            private_root=lock_root,
            benchmark_root=BENCHMARK_ROOT,
            expected_git_sha=IMPLEMENTATION_SHA,
        ) == []
        assert (lock_root / "prepared.json").stat().st_mode & 0o777 == 0o400
        assert lock_root.stat().st_mode & 0o777 == 0o500
        assert lock_root.parent.stat().st_mode & 0o777 == 0o700
    finally:
        _restore_writable(lock_root)


def test_lock_verifier_detects_byte_tamper_after_seal(tmp_path: Path) -> None:
    lock_root, prepared_path, run_paths, manifest = _write_lock_inputs(tmp_path)
    try:
        lock = build_lock_manifest(
            prepared_path,
            run_paths,
            manifest,
            private_root=lock_root,
            benchmark_root=BENCHMARK_ROOT,
            implementation_git_sha=IMPLEMENTATION_SHA,
        )
        atomic_write_json(lock_root / "lock-manifest.json", lock)
        seal_lock_tree(lock_root)
        target = lock_root / lock["runs"][0]["relative_path"]
        target.chmod(0o600)
        target.write_bytes(target.read_bytes() + b" ")
        errors = verify_lock_manifest(
            lock,
            private_root=lock_root,
            benchmark_root=BENCHMARK_ROOT,
            expected_git_sha=IMPLEMENTATION_SHA,
        )
        assert any("sha256" in error for error in errors)
    finally:
        _restore_writable(lock_root)


def test_lock_rejects_contaminating_file_names(tmp_path: Path) -> None:
    lock_root, prepared_path, run_paths, manifest = _write_lock_inputs(tmp_path)
    (lock_root / "gold-copy.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(BenchmarkArtifactError, match="forbidden lock-tree name"):
        build_lock_manifest(
            prepared_path,
            run_paths,
            manifest,
            private_root=lock_root,
            benchmark_root=BENCHMARK_ROOT,
            implementation_git_sha=IMPLEMENTATION_SHA,
        )


def test_lock_verifier_rejects_manifest_path_escape(tmp_path: Path) -> None:
    lock_root, prepared_path, run_paths, manifest = _write_lock_inputs(tmp_path)
    lock = build_lock_manifest(
        prepared_path,
        run_paths,
        manifest,
        private_root=lock_root,
        benchmark_root=BENCHMARK_ROOT,
        implementation_git_sha=IMPLEMENTATION_SHA,
    )
    lock["prepared"]["relative_path"] = "../prepared.json"
    errors = verify_lock_manifest(
        lock,
        private_root=lock_root,
        benchmark_root=BENCHMARK_ROOT,
        expected_git_sha=IMPLEMENTATION_SHA,
        require_sealed=False,
    )
    assert any("relative_path" in error for error in errors)
