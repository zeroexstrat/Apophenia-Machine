from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from athanasor.benchmark.freeze import atomic_write_private, build_adjudication_packet
from athanasor.benchmark.reviewer import (
    ReviewSession,
    ReviewerError,
    _pdf_text,
    extract_evidence_sentences,
)
from tests.benchmark_fixtures import (
    protocol_fixture,
    source_manifest_fixture,
    write_private_source_fixture,
    write_valid_public_bundle,
)


def _open_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ReviewSession:
    repo = tmp_path / "repo"
    benchmark = write_valid_public_bundle(repo)
    private = tmp_path / "private"
    source_dir = private / "sources"
    write_private_source_fixture(source_dir, source_manifest_fixture())
    packet_path = private / "gold" / "packet.json"
    atomic_write_private(
        packet_path,
        build_adjudication_packet(source_manifest_fixture(), protocol_fixture()),
        repo,
    )
    monkeypatch.setattr(
        "athanasor.benchmark.reviewer._pdf_text",
        lambda _path: (
            "Title\nABSTRACT\n"
            "First useful evidence sentence. Second useful evidence sentence.\n"
            "1 INTRODUCTION\nHidden body sentence."
        ),
    )
    return ReviewSession.open(
        packet_path=packet_path,
        source_dir=source_dir,
        benchmark_root=benchmark,
        repo_root=repo,
    )


def test_extract_evidence_prefers_abstract_sentences() -> None:
    text = (
        "Title\nABSTRACT\nFirst useful sentence. Second useful sentence.\n"
        "1 INTRODUCTION\nHidden body."
    )
    assert extract_evidence_sentences(text) == [
        "First useful sentence.",
        "Second useful sentence.",
    ]


def test_extract_evidence_ignores_interleaved_column_heading() -> None:
    text = (
        "Title\nABSTRACT                         KEYWORDS\n"
        "Useful model-reporting evidence sentence. Another useful sentence.\n"
        "1 INTRODUCTION\nHidden body."
    )
    assert extract_evidence_sentences(text) == [
        "Useful model-reporting evidence sentence.",
        "Another useful sentence.",
    ]


def test_extract_evidence_filters_bibliographic_header_sentence() -> None:
    text = (
        "Paper title Author author@example.org arXiv:1234.5678v1 Useful first sentence. "
        "Second useful evidence sentence. Third useful evidence sentence."
    )
    assert extract_evidence_sentences(text) == [
        "Second useful evidence sentence.",
        "Third useful evidence sentence.",
    ]


def test_extract_evidence_uses_introduction_when_abstract_is_absent() -> None:
    text = (
        "Paper title arXiv:1234.5678v1\n1 Introduction\n"
        "Data shapes model behavior in deployment. "
        "Dataset documentation supports accountable decisions."
    )
    assert extract_evidence_sentences(text) == [
        "Data shapes model behavior in deployment.",
        "Dataset documentation supports accountable decisions.",
    ]


def test_pdf_text_uses_reading_order_instead_of_interleaving_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        captured.extend(command)
        return SimpleNamespace(returncode=0, stdout="ABSTRACT\nUseful evidence sentence.")

    monkeypatch.setattr("athanasor.benchmark.reviewer.subprocess.run", fake_run)
    assert "Useful evidence" in _pdf_text(Path("synthetic.pdf"))
    assert "-layout" not in captured


def test_pdf_text_extends_to_page_four_when_front_matter_has_no_prose_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []
    outputs = iter(
        [
            "Cover page and copyright notice only.",
            "Cover pages\nAbstract\nSubstantive evidence sentence.",
        ]
    )

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout=next(outputs))

    monkeypatch.setattr("athanasor.benchmark.reviewer.subprocess.run", fake_run)
    result = _pdf_text(Path("front-matter-heavy.pdf"))
    assert "Substantive evidence sentence." in result
    assert [command[command.index("-l") + 1] for command in commands] == ["2", "4"]


def test_pdf_text_does_not_extend_when_introduction_is_already_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        commands.append(command)
        return SimpleNamespace(
            returncode=0,
            stdout="Title\n1 Introduction\nSubstantive evidence sentence.",
        )

    monkeypatch.setattr("athanasor.benchmark.reviewer.subprocess.run", fake_run)
    _pdf_text(Path("ordinary.pdf"))
    assert len(commands) == 1


def test_visible_presentation_omits_hidden_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = _open_session(tmp_path, monkeypatch).presentation(0)
    assert view["position"] == 1
    assert view["total"] == 70
    assert view["paper_a"]["evidence"] == [
        "First useful evidence sentence.",
        "Second useful evidence sentence.",
    ]
    serialized = json.dumps(view)
    for forbidden in ("pair_id", "paper_id", "anchor", "lane", "selection"):
        assert forbidden not in serialized


@pytest.mark.parametrize("label", [-1, 4, True, "2"])
def test_save_rejects_invalid_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, label: object
) -> None:
    session = _open_session(tmp_path, monkeypatch)
    view = session.presentation(0)
    with pytest.raises(ReviewerError, match="label"):
        session.save_answer(
            0,
            label=label,
            rationale="shared mechanism",
            evidence={
                "a": [view["paper_a"]["evidence"][0]],
                "b": [view["paper_b"]["evidence"][0]],
            },
        )


def test_save_requires_rationale_and_both_papers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _open_session(tmp_path, monkeypatch)
    view = session.presentation(0)
    evidence = {
        "a": [view["paper_a"]["evidence"][0]],
        "b": [view["paper_b"]["evidence"][0]],
    }
    with pytest.raises(ReviewerError, match="rationale"):
        session.save_answer(0, label=2, rationale="", evidence=evidence)
    with pytest.raises(ReviewerError, match="both papers"):
        session.save_answer(
            0,
            label=2,
            rationale="shared mechanism",
            evidence={"a": evidence["a"], "b": []},
        )


def test_save_rejects_unoffered_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _open_session(tmp_path, monkeypatch)
    view = session.presentation(0)
    with pytest.raises(ReviewerError, match="offered evidence"):
        session.save_answer(
            0,
            label=2,
            rationale="shared mechanism",
            evidence={
                "a": ["Invented evidence."],
                "b": [view["paper_b"]["evidence"][0]],
            },
        )


def test_save_updates_only_answer_fields_and_reloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _open_session(tmp_path, monkeypatch)
    before = deepcopy(session.packet)
    view = session.presentation(0)
    result = session.save_answer(
        0,
        label=2,
        rationale="  shared decision structure  ",
        evidence={
            "a": [view["paper_a"]["evidence"][0]],
            "b": [view["paper_b"]["evidence"][1]],
        },
    )
    after = json.loads(session.packet_path.read_text(encoding="utf-8"))
    expected = deepcopy(before)
    expected["presentations"][0] = after["presentations"][0]
    assert after == expected
    assert result["answer"] == {
        "label": 2,
        "rationale": "shared decision structure",
        "evidence": {
            "a": [view["paper_a"]["evidence"][0]],
            "b": [view["paper_b"]["evidence"][1]],
        },
    }
    assert session.presentation(0)["answer"] == result["answer"]


def test_presentation_keeps_previously_saved_spans_selectable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _open_session(tmp_path, monkeypatch)
    row = session.packet["presentations"][0]
    row["label"] = 2
    row["rationale"] = "brief human rationale"
    row["evidence_spans"] = [
        {"paper_role": "a", "text": "Previously selected excerpt A."},
        {"paper_role": "b", "text": "Previously selected excerpt B."},
    ]
    view = session.presentation(0)
    assert "Previously selected excerpt A." in view["paper_a"]["evidence"]
    assert "Previously selected excerpt B." in view["paper_b"]["evidence"]


def test_open_rejects_private_packet_inside_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    benchmark = write_valid_public_bundle(repo)
    source_dir = tmp_path / "private" / "sources"
    write_private_source_fixture(source_dir, source_manifest_fixture())
    packet_path = repo / "packet.json"
    packet_path.write_text(
        json.dumps(build_adjudication_packet(source_manifest_fixture(), protocol_fixture())),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "athanasor.benchmark.reviewer._pdf_text",
        lambda _path: "ABSTRACT\nUseful evidence sentence.\nINTRODUCTION",
    )
    with pytest.raises(ReviewerError, match="outside the repository"):
        ReviewSession.open(
            packet_path=packet_path,
            source_dir=source_dir,
            benchmark_root=benchmark,
            repo_root=repo,
        )
