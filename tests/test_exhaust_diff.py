"""Diff harness: compare exhaust output across runs (one per agent/model)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_diff_module():
    spec = importlib.util.spec_from_file_location(
        "exhaust_diff_under_test", REPO_ROOT / "scripts" / "exhaust_diff.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_exhaust(root: Path, paper_id: str, buckets: dict[str, int]) -> None:
    out = root / "albedo" / "exhaust"
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 2,
        "exhaustion": {"paper_id": paper_id, "paper_title": paper_id, "exhaustion_depth": 3},
    }
    for name, count in buckets.items():
        payload[name] = [
            {"statement": f"{name} item {i}", "confidence": "derived"} for i in range(count)
        ]
    (out / f"{paper_id}_exhaust.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")


def test_compare_reports_per_run_and_per_paper_counts(tmp_path: Path) -> None:
    diff = _load_diff_module()
    root_a = tmp_path / "claude"
    root_b = tmp_path / "gpt"
    _write_exhaust(root_a, "p1", {"derivations": 5, "missing_angles": 2})
    _write_exhaust(root_a, "p2", {"derivations": 1})
    _write_exhaust(root_b, "p1", {"derivations": 3, "missing_angles": 4, "experiments": 1})
    # p2 absent from run B — coverage gap.

    report = diff.compare({"claude": root_a, "gpt": root_b})

    assert set(report["runs"]) == {"claude", "gpt"}
    # Totals per run.
    assert report["totals"]["claude"]["total_items"] == 8  # 5+2+1
    assert report["totals"]["gpt"]["total_items"] == 8  # 3+4+1
    # Per-paper, per-run bucket counts.
    p1 = report["papers"]["p1"]
    assert p1["claude"]["derivations"] == 5
    assert p1["gpt"]["derivations"] == 3
    # Coverage: p2 only in claude.
    assert report["papers"]["p2"]["claude"]["derivations"] == 1
    assert report["papers"]["p2"]["gpt"] is None
    assert report["coverage"]["claude"] == 2
    assert report["coverage"]["gpt"] == 1
    assert report["papers_in_all_runs"] == ["p1"]


def test_render_text_is_nonempty_table(tmp_path: Path) -> None:
    diff = _load_diff_module()
    root_a = tmp_path / "a"
    _write_exhaust(root_a, "p1", {"derivations": 2})
    report = diff.compare({"a": root_a})
    text = diff.render_text(report)
    assert "p1" in text
    assert "derivations" in text or "total" in text.lower()


def test_compare_handles_empty_run(tmp_path: Path) -> None:
    diff = _load_diff_module()
    empty = tmp_path / "empty"
    empty.mkdir()
    report = diff.compare({"empty": empty})
    assert report["totals"]["empty"]["total_items"] == 0
    assert report["coverage"]["empty"] == 0
