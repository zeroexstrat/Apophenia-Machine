# Terminal Adjudication Reviewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a sequential terminal interface that resumes, validates, and atomically records blinded P5 adjudications in the existing private packet.

**Architecture:** A standalone script wraps the existing `ReviewSession`; pure parsers convert evidence and label input, while `TerminalReviewer` owns rendering, navigation, confirmation, and resume behavior. All source verification, hidden topology, evidence authority, and persistence remain in the existing review model.

**Tech Stack:** Python 3.10+, standard library, existing `athanasor.benchmark.reviewer`, pytest.

## Global Constraints

- Read and write the same private packet used by the browser reviewer.
- Never print lane, selection, graph, pair, paper ID, or anchor metadata.
- Never infer or autofill evidence, labels, or rationales.
- Delegate every write to `ReviewSession.save_answer`.
- Navigation and declined confirmation never write.
- Use injectable input/output streams; do not require a real TTY for tests.
- Exit cleanly on `:quit`, EOF, or keyboard interruption.

---

### Task 1: Sequential terminal reviewer

**Files:**
- Create: `scripts/review_benchmark_adjudication.py`
- Create: `tests/test_benchmark_terminal_reviewer.py`
- Modify: `benchmarks/operations-decision-support-v1/README.md`

**Interfaces:**
- Consumes: `ReviewSession.open`, `ReviewSession.presentation`, `ReviewSession.save_answer`, CLI paths, and line-oriented input/output streams.
- Produces: `parse_evidence_numbers(value: str, count: int) -> list[int]`, `parse_label(value: str) -> int`, `TerminalReviewer.run() -> int`, and a standalone CLI.

- [ ] **Step 1: Write failing parser and rendering tests**

```python
def test_parse_evidence_numbers_deduplicates_in_order() -> None:
    assert parse_evidence_numbers(" 3, 1, 3 ", 4) == [2, 0]


@pytest.mark.parametrize("value", ["", "0", "-1", "a", "1,5"])
def test_parse_evidence_numbers_rejects_invalid_input(value: str) -> None:
    with pytest.raises(TerminalInputError):
        parse_evidence_numbers(value, 4)


def test_render_is_blinded(fake_session: FakeSession) -> None:
    output = StringIO()
    reviewer = TerminalReviewer(fake_session, input_stream=StringIO(":quit\n"), output_stream=output)
    reviewer.run()
    rendered = output.getvalue()
    assert "Paper A: Fictional source A" in rendered
    for forbidden in ("pair_id", "paper_id", "anchor", "lane", "selection"):
        assert forbidden not in rendered
```

- [ ] **Step 2: Write failing resume, save, navigation, and exit tests**

```python
def test_resumes_at_first_unanswered_and_saves(fake_session: FakeSession) -> None:
    fake_session.views[0]["answer"]["label"] = 1
    input_stream = StringIO("1\n1\n2\nshared structure\ny\n:quit\n")
    reviewer = TerminalReviewer(fake_session, input_stream=input_stream, output_stream=StringIO())
    assert reviewer.run() == 0
    assert fake_session.saved == [(1, 2, "shared structure", {"a": ["A evidence."], "b": ["B evidence."]})]


def test_declined_confirmation_does_not_save(fake_session: FakeSession) -> None:
    reviewer = TerminalReviewer(
        fake_session,
        input_stream=StringIO("1\n1\n2\nshared structure\nn\n:quit\n"),
        output_stream=StringIO(),
    )
    reviewer.run()
    assert fake_session.saved == []


def test_eof_exits_without_saving(fake_session: FakeSession) -> None:
    reviewer = TerminalReviewer(fake_session, input_stream=StringIO(""), output_stream=StringIO())
    assert reviewer.run() == 0
    assert fake_session.saved == []
```

Add focused tests for `:back`, `:skip`, `:edit N`, `:progress`, `:help`, invalid-input retry, existing-answer rendering, and save errors preserving the current presentation.

- [ ] **Step 3: Run tests and confirm missing-script failure**

Run: `uv run pytest tests/test_benchmark_terminal_reviewer.py -q`

Expected: collection fails because `scripts.review_benchmark_adjudication` does not exist.

- [ ] **Step 4: Implement parsers and the terminal loop**

Use these public shapes:

```python
class TerminalInputError(ValueError):
    pass


def parse_evidence_numbers(value: str, count: int) -> list[int]:
    parts = [part.strip() for part in value.split(",")]
    if not parts or any(not part.isdigit() for part in parts):
        raise TerminalInputError("enter one or more comma-separated evidence numbers")
    selected = [int(part) for part in parts]
    if any(number < 1 or number > count for number in selected):
        raise TerminalInputError(f"evidence numbers must be between 1 and {count}")
    return list(dict.fromkeys(number - 1 for number in selected))


def parse_label(value: str) -> int:
    if value not in {"0", "1", "2", "3"}:
        raise TerminalInputError("label must be 0, 1, 2, or 3")
    return int(value)


class TerminalReviewer:
    def __init__(self, session: ReviewSession, *, input_stream: TextIO, output_stream: TextIO) -> None: ...
    def run(self) -> int: ...
```

Model navigation as one private `_Navigation` exception carrying `back`, `skip`,
`edit`, `progress`, `help`, or `quit`. A `_read(prompt)` helper recognizes command
lines at every prompt. Render evidence with 1-based indexes and mark existing
selections with `*`. Build answer summaries from the exact current view, ask
`Save this answer? [y/n]`, and call `save_answer` only after `y`.

Find the first unanswered view at startup. After saving, move to the next
unanswered presentation after the current position, wrapping once; if none
remain, print `All 70 presentations are answered.` and accept `:edit N` or
`:quit`. Catch EOF and `KeyboardInterrupt` at the top-level loop.

- [ ] **Step 5: Add deterministic CLI startup and usage documentation**

The CLI opens the review session with the four required path arguments and maps
`ReviewerError` to `Reviewer startup failed: <message>` with exit 2. Add this
README command:

```bash
uv run python scripts/review_benchmark_adjudication.py \
  --private-gold "$AZOTH_P5_PRIVATE_ROOT/gold/operations-decision-support-v1.json" \
  --source-dir "$AZOTH_P5_PRIVATE_ROOT/sources" \
  --benchmark-root benchmarks/operations-decision-support-v1 \
  --repo-root .
```

- [ ] **Step 6: Verify the implementation and real-packet no-write smoke test**

Run: `uv run pytest tests/test_benchmark_terminal_reviewer.py tests/test_benchmark_reviewer.py tests/test_benchmark_reviewer_server.py tests/test_benchmark_freeze.py tests/test_benchmark_protocol.py -q`

Expected: all pass.

Hash the private packet, pipe `:quit` to the real CLI, hash it again, and require
equal hashes. The output must start at Presentation 2 because Presentation 1 is
already answered.

- [ ] **Step 7: Commit**

```bash
git add scripts/review_benchmark_adjudication.py tests/test_benchmark_terminal_reviewer.py benchmarks/operations-decision-support-v1/README.md
git commit -m "feat: add terminal benchmark adjudication reviewer"
```
