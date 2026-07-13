# Local Adjudication Reviewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and launch a localhost-only browser reviewer that atomically records Rafael's 70 blinded P5 adjudications in the private packet.

**Architecture:** A pure `athanasor.benchmark.reviewer` module validates paths, extracts private PDF evidence, builds generation-safe presentation views, and persists answers through the existing atomic writer. A standard-library HTTP entry point serves one embedded HTML application on loopback behind a random token.

**Tech Stack:** Python 3.10+, standard library, existing PyYAML dependency, `pdftotext`, vanilla HTML/CSS/JavaScript, pytest.

## Global Constraints

- Bind only to `127.0.0.1`; never call an external service.
- Keep the private packet and PDF bytes outside Git.
- Hide lane, selection, graph, pair, and anchor metadata from browser responses.
- Require label 0-3, a nonempty human rationale, and selected source evidence from both papers.
- Save only on explicit user action and use `atomic_write_private` for every write.
- Verify private source bytes against the public manifest before serving.
- Preserve all packet fields other than the selected presentation's `label`, `rationale`, and `evidence_spans`.

---

### Task 1: Private review model and atomic answer store

**Files:**
- Create: `athanasor/benchmark/reviewer.py`
- Modify: `athanasor/benchmark/__init__.py`
- Create: `tests/test_benchmark_reviewer.py`

**Interfaces:**
- Consumes: public source manifest, private packet path, private source directory, repository root, and `pdftotext` output.
- Produces: `ReviewSession.open(...)`, `ReviewSession.presentation(index)`, `ReviewSession.save_answer(...)`, `extract_evidence_sentences(text)`, and `ReviewerError`.

- [ ] **Step 1: Write failing tests for extraction and visible boundaries**

```python
def test_extract_evidence_prefers_abstract_sentences() -> None:
    text = "Title\nABSTRACT\nFirst useful sentence. Second useful sentence.\n1 INTRODUCTION\nHidden body."
    assert extract_evidence_sentences(text) == [
        "First useful sentence.",
        "Second useful sentence.",
    ]


def test_visible_presentation_omits_hidden_metadata(review_session: ReviewSession) -> None:
    view = review_session.presentation(0)
    serialized = json.dumps(view)
    for forbidden in ("pair_id", "paper_id", "anchor", "lane", "selection"):
        assert forbidden not in serialized
```

- [ ] **Step 2: Write failing tests for answer validation and persistence**

```python
def test_save_requires_label_rationale_and_both_papers(review_session: ReviewSession) -> None:
    with pytest.raises(ReviewerError, match="rationale"):
        review_session.save_answer(0, label=2, rationale="", evidence={"a": ["A."], "b": ["B."]})
    with pytest.raises(ReviewerError, match="both papers"):
        review_session.save_answer(0, label=2, rationale="shared mechanism", evidence={"a": ["A."], "b": []})


def test_save_updates_only_answer_fields(review_session: ReviewSession) -> None:
    before = deepcopy(review_session.packet)
    view = review_session.presentation(0)
    review_session.save_answer(0, label=2, rationale="shared decision structure", evidence={
        "a": [view["paper_a"]["evidence"][0]],
        "b": [view["paper_b"]["evidence"][0]],
    })
    after = json.loads(review_session.packet_path.read_text())
    expected = deepcopy(before)
    expected["presentations"][0].update(after["presentations"][0])
    assert after == expected
```

- [ ] **Step 3: Run the focused tests and confirm missing-module failure**

Run: `uv run pytest tests/test_benchmark_reviewer.py -q`

Expected: collection fails because `athanasor.benchmark.reviewer` does not exist.

- [ ] **Step 4: Implement extraction, authoritative loading, visible views, and saves**

Implement immutable source records and a lock-protected `ReviewSession`. Resolve
and reject private paths with `ensure_outside_repository`; validate the public
manifest; hash every `{paper_id}.pdf`; invoke `pdftotext -f 1 -l 2 -layout`;
extract 3-20 useful sentences; map shuffled presentations through authoritative
canonical pairs; omit all internal identifiers from returned paper objects; and
validate submitted sentences by exact membership before calling
`atomic_write_private`.

Use these signatures:

```python
class ReviewerError(ValueError):
    pass


def extract_evidence_sentences(text: str) -> list[str]: ...


class ReviewSession:
    @classmethod
    def open(cls, *, packet_path: Path, source_dir: Path, benchmark_root: Path, repo_root: Path) -> "ReviewSession": ...
    def presentation(self, index: int) -> dict[str, Any]: ...
    def save_answer(self, index: int, *, label: int, rationale: str, evidence: dict[str, list[str]]) -> dict[str, Any]: ...
```

- [ ] **Step 5: Run focused and inherited tests**

Run: `uv run pytest tests/test_benchmark_reviewer.py tests/test_benchmark_freeze.py tests/test_benchmark_protocol.py -q`

Expected: all pass.

- [ ] **Step 6: Commit the review model**

```bash
git add athanasor/benchmark/reviewer.py athanasor/benchmark/__init__.py tests/test_benchmark_reviewer.py
git commit -m "feat: add private adjudication review model"
```

---

### Task 2: Token-protected localhost interface and live launch

**Files:**
- Create: `scripts/serve_benchmark_adjudication.py`
- Create: `tests/test_benchmark_reviewer_server.py`
- Modify: `benchmarks/operations-decision-support-v1/README.md`

**Interfaces:**
- Consumes: `ReviewSession` and CLI paths `--private-gold`, `--source-dir`, `--benchmark-root`, `--repo-root`, plus optional `--port` and `--open`.
- Produces: loopback page `/<token>/`, `GET /api/<token>/presentation/<index>`, and `POST /api/<token>/presentation/<index>`.

- [ ] **Step 1: Write failing HTTP contract tests**

```python
def test_routes_require_session_token(live_reviewer: LiveReviewer) -> None:
    assert urlopen(live_reviewer.url).status == 200
    with pytest.raises(HTTPError) as error:
        urlopen(live_reviewer.origin + "/api/wrong/presentation/0")
    assert error.value.code == 404


def test_post_saves_and_get_reloads_answer(live_reviewer: LiveReviewer) -> None:
    view = get_json(live_reviewer.url + "api/presentation/0")
    post_json(live_reviewer.url + "api/presentation/0", {
        "label": 2,
        "rationale": "shared decision structure",
        "evidence": {
            "a": [view["paper_a"]["evidence"][0]],
            "b": [view["paper_b"]["evidence"][0]],
        },
    })
    assert get_json(live_reviewer.url + "api/presentation/0")["answer"]["label"] == 2
```

- [ ] **Step 2: Run tests and confirm missing-script failure**

Run: `uv run pytest tests/test_benchmark_reviewer_server.py -q`

Expected: tests fail because `scripts/serve_benchmark_adjudication.py` is absent.

- [ ] **Step 3: Implement the server and reviewer page**

Use `ThreadingHTTPServer(("127.0.0.1", port), Handler)`, `secrets.token_urlsafe(24)`,
bounded JSON request bodies, exact token routes, `Cache-Control: no-store`, and a
Content Security Policy allowing only same-origin scripts/styles. Return 400 for
answer validation, 404 for invalid token/routes, and 500 with generic text for
unexpected failures.

Embed a responsive, high-contrast HTML page with:

```html
<input type="radio" name="label" value="0" required>
<input type="checkbox" name="evidence-a">
<input type="checkbox" name="evidence-b">
<textarea id="rationale" required></textarea>
<button id="back">Back</button>
<button id="save">Save</button>
<button id="save-next">Save &amp; Next</button>
```

JavaScript must fetch only the current index, render all text with `textContent`,
disable saving during requests, show inline errors, reload exact prior answers,
and move forward only after a successful save. It must not place packet topology
or private paths into the DOM.

- [ ] **Step 4: Document the private launch command**

Add a README section using environment variables only:

```bash
uv run python scripts/serve_benchmark_adjudication.py \
  --private-gold "$AZOTH_P5_PRIVATE_ROOT/gold/operations-decision-support-v1.json" \
  --source-dir "$AZOTH_P5_PRIVATE_ROOT/sources" \
  --benchmark-root benchmarks/operations-decision-support-v1 \
  --repo-root . \
  --open
```

- [ ] **Step 5: Run complete verification**

Run: `uv run pytest tests/test_benchmark_reviewer.py tests/test_benchmark_reviewer_server.py tests/test_benchmark_check.py tests/test_benchmark_freeze.py tests/test_benchmark_protocol.py -q`

Expected: all pass.

Run: `uv run python -m compileall -q athanasor scripts tests && git diff --check && python3 athanasor/vigil/verify.py verify`

Expected: every command exits 0 and Vigil passes all gates.

- [ ] **Step 6: Launch against the real private packet and smoke-test without changing answers**

Start the documented command on an ephemeral port. Verify page 1 loads, shows
the already saved first answer, exposes no hidden metadata, and page 2 is blank.
Do not submit a smoke-test answer.

- [ ] **Step 7: Commit the server and documentation**

```bash
git add scripts/serve_benchmark_adjudication.py tests/test_benchmark_reviewer_server.py benchmarks/operations-decision-support-v1/README.md
git commit -m "feat: serve local benchmark adjudication reviewer"
```
