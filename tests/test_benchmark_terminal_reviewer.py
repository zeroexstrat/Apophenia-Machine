from __future__ import annotations

from copy import deepcopy
from io import StringIO
from typing import Any

import pytest

from athanasor.benchmark.reviewer import ReviewerError
from scripts.review_benchmark_adjudication import (
    TerminalInputError,
    TerminalReviewer,
    parse_evidence_numbers,
    parse_label,
)


class FakeSession:
    def __init__(self, *, answered: set[int] | None = None) -> None:
        answered = answered or set()
        self.views: list[dict[str, Any]] = []
        for index in range(3):
            answer = {
                "label": 1 if index in answered else None,
                "rationale": "existing rationale" if index in answered else "",
                "evidence": {
                    "a": ["A evidence one."] if index in answered else [],
                    "b": ["B evidence one."] if index in answered else [],
                },
            }
            self.views.append(
                {
                    "position": index + 1,
                    "total": 3,
                    "completed": len(answered),
                    "paper_a": {
                        "title": f"Fictional source A{index + 1}",
                        "authors": ["Ada Example"],
                        "evidence": ["A evidence one.", "A evidence two."],
                    },
                    "paper_b": {
                        "title": f"Fictional source B{index + 1}",
                        "authors": ["Benoit Example"],
                        "evidence": ["B evidence one.", "B evidence two."],
                    },
                    "answer": answer,
                }
            )
        self.saved: list[tuple[int, int, str, dict[str, list[str]]]] = []
        self.fail_save = False

    def presentation(self, index: int) -> dict[str, Any]:
        view = deepcopy(self.views[index])
        view["completed"] = sum(
            item["answer"]["label"] is not None for item in self.views
        )
        return view

    def save_answer(
        self,
        index: int,
        *,
        label: int,
        rationale: str,
        evidence: dict[str, list[str]],
    ) -> dict[str, Any]:
        if self.fail_save:
            raise ReviewerError("synthetic save failure")
        self.saved.append((index, label, rationale, evidence))
        self.views[index]["answer"] = {
            "label": label,
            "rationale": rationale,
            "evidence": deepcopy(evidence),
        }
        return self.presentation(index)


def run_reviewer(
    session: FakeSession, input_text: str
) -> tuple[int, str]:
    output = StringIO()
    result = TerminalReviewer(
        session,
        input_stream=StringIO(input_text),
        output_stream=output,
    ).run()
    return result, output.getvalue()


def test_parse_evidence_numbers_deduplicates_in_order() -> None:
    assert parse_evidence_numbers(" 3, 1, 3 ", 4) == [2, 0]


@pytest.mark.parametrize("value", ["", "0", "-1", "a", "1,5", "1,"])
def test_parse_evidence_numbers_rejects_invalid_input(value: str) -> None:
    with pytest.raises(TerminalInputError):
        parse_evidence_numbers(value, 4)


@pytest.mark.parametrize(
    ("value", "expected"), [("0", 0), ("1", 1), ("2", 2), ("3", 3)]
)
def test_parse_label_accepts_frozen_scale(value: str, expected: int) -> None:
    assert parse_label(value) == expected


@pytest.mark.parametrize("value", ["", "4", "-1", "two", " 2 "])
def test_parse_label_rejects_noncanonical_input(value: str) -> None:
    with pytest.raises(TerminalInputError):
        parse_label(value)


def test_render_is_blinded_and_shows_numbered_evidence() -> None:
    result, rendered = run_reviewer(FakeSession(), ":quit\n")
    assert result == 0
    assert "Presentation 1 of 3 - 0 completed" in rendered
    assert "Paper A: Fictional source A1" in rendered
    assert "  [1] A evidence one." in rendered
    for forbidden in ("pair_id", "paper_id", "anchor", "lane", "selection"):
        assert forbidden not in rendered


def test_resumes_at_first_unanswered_and_saves() -> None:
    session = FakeSession(answered={0})
    result, rendered = run_reviewer(
        session,
        "1\n2\n2\nshared structure\ny\n:quit\n",
    )
    assert result == 0
    assert "Presentation 2 of 3 - 1 completed" in rendered
    assert session.saved == [
        (
            1,
            2,
            "shared structure",
            {"a": ["A evidence one."], "b": ["B evidence two."]},
        )
    ]


def test_declined_confirmation_does_not_save() -> None:
    session = FakeSession()
    result, rendered = run_reviewer(
        session,
        "1\n1\n2\nshared structure\nn\n:quit\n",
    )
    assert result == 0
    assert session.saved == []
    assert "Answer not saved." in rendered


def test_skip_and_edit_navigate_without_saving() -> None:
    session = FakeSession()
    _result, rendered = run_reviewer(session, ":skip\n:edit 3\n:quit\n")
    assert session.saved == []
    assert "Presentation 2 of 3" in rendered
    assert "Presentation 3 of 3" in rendered


def test_back_does_not_move_before_first_presentation() -> None:
    session = FakeSession()
    _result, rendered = run_reviewer(session, ":back\n:quit\n")
    assert rendered.count("Presentation 1 of 3") == 2
    assert session.saved == []


def test_progress_and_help_return_to_current_presentation() -> None:
    _result, rendered = run_reviewer(FakeSession(answered={0}), ":progress\n:help\n:quit\n")
    assert "Progress: 1 completed, 2 remaining." in rendered
    assert ":edit N" in rendered
    assert rendered.count("Presentation 2 of 3") == 3


def test_invalid_input_repeats_only_current_prompt() -> None:
    session = FakeSession()
    _result, rendered = run_reviewer(
        session,
        "0\n1\n1\n4\n2\nbrief rationale\ny\n:quit\n",
    )
    assert "evidence numbers must be between 1 and 2" in rendered
    assert "label must be 0, 1, 2, or 3" in rendered
    assert session.saved[0][1] == 2


def test_existing_answer_is_marked_when_editing() -> None:
    _result, rendered = run_reviewer(FakeSession(answered={0}), ":edit 1\n:quit\n")
    assert "Existing label: 1" in rendered
    assert "  *[1] A evidence one." in rendered
    assert "Existing rationale: existing rationale" in rendered


def test_save_error_preserves_current_presentation() -> None:
    session = FakeSession()
    session.fail_save = True
    _result, rendered = run_reviewer(
        session,
        "1\n1\n2\nshared structure\ny\n:quit\n",
    )
    assert "Save failed: synthetic save failure" in rendered
    assert rendered.count("Presentation 1 of 3") == 2
    assert session.saved == []


def test_eof_exits_without_saving() -> None:
    session = FakeSession()
    result, rendered = run_reviewer(session, "")
    assert result == 0
    assert "Review stopped; no unsaved answer was written." in rendered
    assert session.saved == []
