"""The five documented Vigil gates must enforce their bounded contracts."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

from athanasor.rejections import append_rejection
from tests.fixture_factory import (
    registry_entry,
    write_connection,
    write_exhaust,
    write_hypothesis,
    write_library,
    write_registry,
    write_yaml,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _vigil():
    spec = importlib.util.spec_from_file_location(
        "vigil_gates_under_test", REPO_ROOT / "athanasor" / "vigil" / "verify.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


# --- Corpus: processed library records are schema-valid and evidence-bearing ---


def test_corpus_rejects_missing_library_record(tmp_path: Path) -> None:
    vigil = _vigil()
    write_registry(tmp_path, [registry_entry("synthetic_001", status="ingested_only", depth=None)])

    passed, detail = vigil.check_corpus(tmp_path)

    assert passed is False
    assert "synthetic_001" in detail


def test_corpus_rejects_schema_invalid_record(tmp_path: Path) -> None:
    vigil = _vigil()
    write_registry(tmp_path, [registry_entry("synthetic_001", status="ingested_only", depth=None)])
    path = write_library(tmp_path, "synthetic_001")
    payload = _read_yaml(path)
    del payload["source"]["authors"]
    write_yaml(path, payload)

    passed, detail = vigil.check_corpus(tmp_path)

    assert passed is False
    assert "schema" in detail.lower()
    assert "authors" in detail


def test_corpus_rejects_blank_claim_evidence(tmp_path: Path) -> None:
    vigil = _vigil()
    write_registry(tmp_path, [registry_entry("synthetic_001", status="ingested_only", depth=None)])
    path = write_library(tmp_path, "synthetic_001")
    payload = _read_yaml(path)
    payload["claims"][0]["evidence"] = "   "
    write_yaml(path, payload)

    passed, detail = vigil.check_corpus(tmp_path)

    assert passed is False
    assert "synthetic_001" in detail
    assert "evidence" in detail


def test_corpus_passes_schema_valid_evidence_bearing_record(tmp_path: Path) -> None:
    vigil = _vigil()
    write_registry(tmp_path, [registry_entry("synthetic_001", status="ingested_only", depth=None)])
    write_library(tmp_path, "synthetic_001")

    passed, detail = vigil.check_corpus(tmp_path)

    assert passed is True
    assert "structural evidence fields" in detail


# --- Coniunctio: persisted connections validate and declared citations bound novelty labels ---


def _connection_workspace(root: Path) -> None:
    write_library(root, "synthetic_001")
    write_library(root, "synthetic_002")


def test_coniunctio_rejects_schema_invalid_connection(tmp_path: Path) -> None:
    vigil = _vigil()
    _connection_workspace(tmp_path)
    path = write_connection(tmp_path, "synthetic_001", "synthetic_002")
    payload = _read_yaml(path)
    del payload["significance"]
    write_yaml(path, payload)

    passed, detail = vigil.check_coniunctio(tmp_path)

    assert passed is False
    assert "schema" in detail.lower()
    assert "significance" in detail


def test_coniunctio_rejects_missing_library_record(tmp_path: Path) -> None:
    vigil = _vigil()
    write_library(tmp_path, "synthetic_001")
    write_connection(tmp_path, "synthetic_001", "synthetic_002")

    passed, detail = vigil.check_coniunctio(tmp_path)

    assert passed is False
    assert "synthetic_002" in detail
    assert "library" in detail.lower()


def test_coniunctio_rejects_placeholder_evidence(tmp_path: Path) -> None:
    vigil = _vigil()
    _connection_workspace(tmp_path)
    write_connection(
        tmp_path,
        "synthetic_001",
        "synthetic_002",
        evidence_a="Unspecified",
    )

    passed, detail = vigil.check_coniunctio(tmp_path)

    assert passed is False
    assert "evidence_a" in detail


def test_coniunctio_rejects_declared_explicit_link(tmp_path: Path) -> None:
    vigil = _vigil()
    write_library(tmp_path, "synthetic_001", explicit_targets=["Synthetic study synthetic_002"])
    write_library(tmp_path, "synthetic_002")
    write_connection(tmp_path, "synthetic_001", "synthetic_002", novelty="non-obvious")

    passed, detail = vigil.check_coniunctio(tmp_path)

    assert passed is False
    assert "declared explicit citation" in detail


def test_coniunctio_passes_uncited_valid_pair_with_honest_limit(tmp_path: Path) -> None:
    vigil = _vigil()
    _connection_workspace(tmp_path)
    write_connection(tmp_path, "synthetic_001", "synthetic_002")

    passed, detail = vigil.check_coniunctio(tmp_path)

    assert passed is True
    assert "declared explicit citations only" in detail
    assert "not an external novelty search" in detail


# --- Calcinatio: exhaustion schema, trace fields, and speculative ceiling ---


def test_calcinatio_rejects_schema_invalid_exhaustion(tmp_path: Path) -> None:
    vigil = _vigil()
    path = write_exhaust(tmp_path, "synthetic_001")
    payload = _read_yaml(path)
    del payload["exhaustion"]["paper_title"]
    write_yaml(path, payload)

    passed, detail = vigil.check_calcinatio(tmp_path)

    assert passed is False
    assert "paper_title" in detail


def test_calcinatio_rejects_placeholder_trace(tmp_path: Path) -> None:
    vigil = _vigil()
    write_exhaust(
        tmp_path,
        "synthetic_001",
        derivations=[
            {
                "statement": "A bounded queue caps work in progress.",
                "follows_from": "Unspecified",
                "confidence": "likely",
            }
        ],
    )

    passed, detail = vigil.check_calcinatio(tmp_path)

    assert passed is False
    assert "trace" in detail.lower()


def test_calcinatio_rejects_six_consecutive_speculative_items(tmp_path: Path) -> None:
    vigil = _vigil()
    write_exhaust(
        tmp_path,
        "synthetic_001",
        derivations=[
            {
                "statement": f"Speculative consequence {index}.",
                "follows_from": "claim_1",
                "confidence": "speculative",
            }
            for index in range(6)
        ],
    )

    passed, detail = vigil.check_calcinatio(tmp_path)

    assert passed is False
    assert "speculative ceiling" in detail.lower()


def test_calcinatio_passes_valid_traced_derivations(tmp_path: Path) -> None:
    vigil = _vigil()
    write_exhaust(tmp_path, "synthetic_001")

    passed, detail = vigil.check_calcinatio(tmp_path)

    assert passed is True
    assert "trace fields" in detail
    assert "does not prove logical validity" in detail


# --- Caput Mortuum: registry cursor and exhaustion artifact agree exactly ---


def test_caput_mortuum_rejects_missing_exhaustion(tmp_path: Path) -> None:
    vigil = _vigil()
    write_registry(tmp_path, [registry_entry("synthetic_001")])

    passed, detail = vigil.check_caput_mortuum(tmp_path)

    assert passed is False
    assert "synthetic_001" in detail


def test_caput_mortuum_rejects_paper_id_mismatch(tmp_path: Path) -> None:
    vigil = _vigil()
    write_registry(tmp_path, [registry_entry("synthetic_001")])
    path = write_exhaust(tmp_path, "synthetic_001")
    payload = _read_yaml(path)
    payload["exhaustion"]["paper_id"] = "synthetic_002"
    write_yaml(path, payload)

    passed, detail = vigil.check_caput_mortuum(tmp_path)

    assert passed is False
    assert "paper id" in detail.lower()


def test_caput_mortuum_rejects_depth_below_registry(tmp_path: Path) -> None:
    vigil = _vigil()
    write_registry(tmp_path, [registry_entry("synthetic_001", depth=4)])
    write_exhaust(tmp_path, "synthetic_001", depth=3)

    passed, detail = vigil.check_caput_mortuum(tmp_path)

    assert passed is False
    assert "depth 3" in detail and "cursor 4" in detail


def test_caput_mortuum_rejects_depth_above_registry(tmp_path: Path) -> None:
    vigil = _vigil()
    write_registry(tmp_path, [registry_entry("synthetic_001", depth=2)])
    write_exhaust(tmp_path, "synthetic_001", depth=3)

    passed, detail = vigil.check_caput_mortuum(tmp_path)

    assert passed is False
    assert "depth 3" in detail and "cursor 2" in detail


def test_caput_mortuum_rejects_cursor_on_non_exhausted_row(tmp_path: Path) -> None:
    vigil = _vigil()
    write_registry(tmp_path, [registry_entry("synthetic_001", status="ingested_only", depth=2)])

    passed, detail = vigil.check_caput_mortuum(tmp_path)

    assert passed is False
    assert "ingested_only" in detail
    assert "cursor" in detail


def test_caput_mortuum_passes_exact_id_and_depth(tmp_path: Path) -> None:
    vigil = _vigil()
    write_registry(tmp_path, [registry_entry("synthetic_001", depth=3)])
    write_exhaust(tmp_path, "synthetic_001", depth=3)

    passed, detail = vigil.check_caput_mortuum(tmp_path)

    assert passed is True
    assert "exactly match" in detail
    assert "cannot reconstruct prior token use" in detail


# --- Nigredo Redux: rejected cluster fingerprints persist across artifact replacement ---


def test_nigredo_redux_rejects_inline_resurfaced_rejection(tmp_path: Path) -> None:
    vigil = _vigil()
    path = write_hypothesis(
        tmp_path,
        "cluster_synthetic",
        ["synthetic_001", "synthetic_002", "synthetic_003"],
    )
    payload = _read_yaml(path)
    payload["triage"] = {"decision": "rejected", "reviewer": "human"}
    write_yaml(path, payload)

    passed, detail = vigil.check_nigredo_redux(tmp_path)

    assert passed is False
    assert "cluster_synthetic" in detail


def test_nigredo_redux_passes_inline_stable_rejection(tmp_path: Path) -> None:
    vigil = _vigil()
    path = write_hypothesis(
        tmp_path,
        "cluster_synthetic",
        ["synthetic_001", "synthetic_002", "synthetic_003"],
        status="rejected",
    )
    payload = _read_yaml(path)
    payload["triage"] = {"decision": "rejected", "reviewer": "human"}
    write_yaml(path, payload)
    append_rejection(
        tmp_path / "athanasor" / "lapis" / "rejections.jsonl",
        payload,
        _rejection_triage(),
    )

    passed, _ = vigil.check_nigredo_redux(tmp_path)

    assert passed is True


def _rejection_triage() -> dict:
    return {
        "decision": "rejected",
        "reviewer": "reviewer@example",
        "note": "The same evidence was rejected.",
        "reviewed_at": "2026-07-11T12:00:00+00:00",
    }


def test_nigredo_redux_rejects_resurfaced_ledger_fingerprint(tmp_path: Path) -> None:
    vigil = _vigil()
    path = write_hypothesis(
        tmp_path,
        "cluster_synthetic",
        ["synthetic_001", "synthetic_002", "synthetic_003"],
    )
    hypothesis = _read_yaml(path)
    append_rejection(
        tmp_path / "athanasor" / "lapis" / "rejections.jsonl",
        hypothesis,
        _rejection_triage(),
    )

    passed, detail = vigil.check_nigredo_redux(tmp_path)

    assert passed is False
    assert "recorded rejection fingerprint" in detail


def test_nigredo_redux_rejects_rejected_hypothesis_missing_ledger(tmp_path: Path) -> None:
    vigil = _vigil()
    path = write_hypothesis(
        tmp_path,
        "cluster_synthetic",
        ["synthetic_001", "synthetic_002", "synthetic_003"],
        status="rejected",
    )
    hypothesis = _read_yaml(path)
    hypothesis["triage"] = _rejection_triage()
    write_yaml(path, hypothesis)

    passed, detail = vigil.check_nigredo_redux(tmp_path)

    assert passed is False
    assert "missing from rejection ledger" in detail


def test_nigredo_redux_rejects_malformed_ledger(tmp_path: Path) -> None:
    vigil = _vigil()
    ledger = tmp_path / "athanasor" / "lapis" / "rejections.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text("not-json\n", encoding="utf-8")

    passed, detail = vigil.check_nigredo_redux(tmp_path)

    assert passed is False
    assert "malformed rejection ledger" in detail


def test_nigredo_redux_allows_changed_evidence_for_same_cluster(tmp_path: Path) -> None:
    vigil = _vigil()
    path = write_hypothesis(
        tmp_path,
        "cluster_synthetic",
        ["synthetic_001", "synthetic_002", "synthetic_003"],
    )
    hypothesis = _read_yaml(path)
    append_rejection(
        tmp_path / "athanasor" / "lapis" / "rejections.jsonl",
        hypothesis,
        _rejection_triage(),
    )
    hypothesis["gaps"][0]["supporting_evidence"] = "A new synthetic run changes the evidence packet."
    write_yaml(path, hypothesis)

    passed, detail = vigil.check_nigredo_redux(tmp_path)

    assert passed is True
    assert "changed evidence" in detail


def test_empty_workspace_passes_all_structural_gates(tmp_path: Path) -> None:
    vigil = _vigil()
    for name in (
        "check_corpus",
        "check_coniunctio",
        "check_calcinatio",
        "check_caput_mortuum",
        "check_nigredo_redux",
    ):
        passed, detail = getattr(vigil, name)(tmp_path)
        assert passed, f"{name} unexpectedly failed: {detail}"


def test_live_repo_passes_all_gates() -> None:
    vigil = _vigil()
    for name in (
        "check_corpus",
        "check_coniunctio",
        "check_calcinatio",
        "check_caput_mortuum",
        "check_nigredo_redux",
    ):
        passed, detail = getattr(vigil, name)(REPO_ROOT)
        assert passed, f"{name} failed on live repo: {detail[:300]}"
