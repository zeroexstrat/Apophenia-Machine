from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from athanasor.benchmark.artifacts import BenchmarkArtifactError, artifact_digest, atomic_write_json
from athanasor.benchmark.evaluation import (
    build_annotation_template,
    build_comparison,
    build_failure_analysis,
    render_public_summary,
    validate_annotation_packet,
)
from athanasor.benchmark.locking import build_lock_manifest, seal_lock_tree
from athanasor.benchmark.scoring import score_run
from tests.test_benchmark_locking import (
    BENCHMARK_ROOT,
    IMPLEMENTATION_SHA,
    _restore_writable,
    _write_lock_inputs,
)
from tests.test_benchmark_scoring import install_synthetic_commitment, synthetic_gold


def _sealed_lock(tmp_path: Path) -> tuple[Path, dict[str, object], dict[str, object], dict[str, object]]:
    lock_root, prepared_path, run_paths, manifest = _write_lock_inputs(tmp_path)
    lock = build_lock_manifest(
        prepared_path,
        run_paths,
        manifest,
        private_root=lock_root,
        benchmark_root=BENCHMARK_ROOT,
        implementation_git_sha=IMPLEMENTATION_SHA,
    )
    atomic_write_json(lock_root / "lock-manifest.json", lock)
    model_run = json.loads(run_paths["model_5_6_sol"].read_text(encoding="utf-8"))
    seal_lock_tree(lock_root)
    return lock_root, lock, model_run, manifest


def _complete_annotations(template: dict[str, object]) -> dict[str, object]:
    for field in ("claims", "evidence_spans", "items"):
        for row in template[field]:  # type: ignore[index]
            if field == "items":
                row.update({"supported": True, "useful": True, "redundant": False})
            else:
                row["supported"] = True
            row["rationale"] = "Synthetic human contract annotation."
    template["status"] = "completed"
    return template


def test_annotation_template_covers_every_model_item_claim_and_span(tmp_path: Path) -> None:
    lock_root, lock, model_run, _manifest = _sealed_lock(tmp_path)
    try:
        template = build_annotation_template(model_run, lock)
        items = [item for result in model_run["results"] for item in result["items"]]
        assert {row["item_id"] for row in template["items"]} == {
            item["item_id"] for item in items
        }
        assert {row["claim_id"] for row in template["claims"]} == {
            item["claim_id"] for item in items
        }
        assert {row["span_id"] for row in template["evidence_spans"]} == {
            span["span_id"] for item in items for span in item["evidence"]
        }
        assert all(
            row["supported"] is None
            and row["useful"] is None
            and row["redundant"] is None
            for row in template["items"]
        )
        assert validate_annotation_packet(template, model_run, lock, require_complete=False) == []
        assert validate_annotation_packet(template, model_run, lock, require_complete=True)
    finally:
        _restore_writable(lock_root)


def test_complete_annotation_packet_validates_exact_coverage(tmp_path: Path) -> None:
    lock_root, lock, model_run, _manifest = _sealed_lock(tmp_path)
    try:
        annotations = _complete_annotations(build_annotation_template(model_run, lock))
        assert validate_annotation_packet(annotations, model_run, lock, require_complete=True) == []
        annotations["items"].pop()  # type: ignore[index]
        assert any(
            "exact item coverage" in error
            for error in validate_annotation_packet(annotations, model_run, lock, require_complete=True)
        )
    finally:
        _restore_writable(lock_root)


def test_p7_score_refuses_missing_verified_lock(tmp_path: Path) -> None:
    lock_root, _lock, model_run, _manifest = _sealed_lock(tmp_path)
    benchmark = tmp_path / "benchmark"
    shutil.copytree(BENCHMARK_ROOT, benchmark)
    gold = synthetic_gold(model_run)
    install_synthetic_commitment(benchmark, gold)
    try:
        with pytest.raises(BenchmarkArtifactError, match="verified P7 lock"):
            score_run(benchmark, model_run, gold)
    finally:
        _restore_writable(lock_root)


def test_p7_score_binds_lock_execution_manifest_and_annotations(tmp_path: Path) -> None:
    lock_root, lock, model_run, manifest = _sealed_lock(tmp_path)
    benchmark = tmp_path / "benchmark"
    shutil.copytree(BENCHMARK_ROOT, benchmark)
    gold = synthetic_gold(model_run)
    install_synthetic_commitment(benchmark, gold)
    annotations = _complete_annotations(build_annotation_template(model_run, lock))
    try:
        score = score_run(
            benchmark,
            model_run,
            gold,
            annotations=annotations,
            verified_lock=lock,
            lock_private_root=lock_root,
            execution_manifest=manifest,
            expected_git_sha=IMPLEMENTATION_SHA,
        )
        assert score["lock_manifest_sha256"] == artifact_digest(lock)
        assert score["execution_manifest_sha256"] == lock["execution_manifest_sha256"]
        assert score["annotation_sha256"] == artifact_digest(annotations)
    finally:
        _restore_writable(lock_root)


def _score_fixtures(
    tmp_path: Path,
) -> tuple[
    Path,
    dict[str, object],
    dict[str, dict[str, object]],
    dict[str, dict[str, object]],
    dict[str, object],
    dict[str, object],
]:
    lock_root, lock, model_run, manifest = _sealed_lock(tmp_path)
    benchmark = tmp_path / "benchmark"
    shutil.copytree(BENCHMARK_ROOT, benchmark)
    gold = synthetic_gold(model_run)
    install_synthetic_commitment(benchmark, gold)
    annotations = _complete_annotations(build_annotation_template(model_run, lock))
    runs: dict[str, dict[str, object]] = {}
    scores: dict[str, dict[str, object]] = {}
    for record in lock["runs"]:
        run_id = record["run_id"]
        run = json.loads((lock_root / record["relative_path"]).read_text(encoding="utf-8"))
        runs[run_id] = run
        scores[run_id] = score_run(
            benchmark,
            run,
            gold,
            annotations=annotations if run_id == "model_5_6_sol" else None,
            verified_lock=lock,
            lock_private_root=lock_root,
            execution_manifest=manifest,
            expected_git_sha=IMPLEMENTATION_SHA,
        )
    return lock_root, lock, runs, scores, gold, annotations


def test_comparison_requires_all_runs_and_all_thirteen_metrics(tmp_path: Path) -> None:
    lock_root, lock, _runs, scores, _gold, _annotations = _score_fixtures(tmp_path)
    try:
        scores.pop("shared_tag")
        with pytest.raises(BenchmarkArtifactError, match="exact seven run IDs"):
            build_comparison(lock, scores)
    finally:
        _restore_writable(lock_root)


def test_comparison_is_complete_and_deterministic(tmp_path: Path) -> None:
    lock_root, lock, _runs, scores, _gold, _annotations = _score_fixtures(tmp_path)
    try:
        first = build_comparison(lock, scores)
        second = build_comparison(lock, json.loads(json.dumps(scores)))
        assert first == second
        assert [row["run_id"] for row in first["runs"]] == [
            row["run_id"] for row in lock["runs"]
        ]
        assert all(len(row["metrics"]) == 13 for row in first["runs"])
    finally:
        _restore_writable(lock_root)


def test_failure_analysis_and_public_summary_report_all_misses_without_leaks(
    tmp_path: Path,
) -> None:
    lock_root, lock, runs, scores, gold, annotations = _score_fixtures(tmp_path)
    try:
        failure = build_failure_analysis(lock, runs, scores, gold, annotations)
        text = render_public_summary(build_comparison(lock, scores), failure)
        assert "threshold not met" in text.lower()
        assert "undefined" in text.lower()
        assert "/Users/" not in text
        assert str(tmp_path) not in text
        assert "gold_rationale" not in text
        assert "Synthetic human contract annotation" not in text
        assert all("rationale" not in str(value) for value in failure.values())
    finally:
        _restore_writable(lock_root)
