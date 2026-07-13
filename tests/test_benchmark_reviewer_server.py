from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from athanasor.benchmark.reviewer import ReviewerError
from scripts.serve_benchmark_adjudication import create_server


class _FakeSession:
    def __init__(self) -> None:
        self.saved: dict[str, Any] | None = None

    def presentation(self, index: int) -> dict[str, Any]:
        if index != 0:
            raise ReviewerError("presentation index is out of range")
        return {
            "position": 1,
            "total": 70,
            "completed": int(self.saved is not None),
            "paper_a": {
                "title": "Fictional source A",
                "authors": ["Ada Example"],
                "evidence": ["Evidence sentence A."],
            },
            "paper_b": {
                "title": "Fictional source B",
                "authors": ["Benoit Example"],
                "evidence": ["Evidence sentence B."],
            },
            "answer": self.saved
            or {"label": None, "rationale": "", "evidence": {"a": [], "b": []}},
        }

    def save_answer(self, index: int, **payload: Any) -> dict[str, Any]:
        if index != 0:
            raise ReviewerError("presentation index is out of range")
        if not payload.get("rationale"):
            raise ReviewerError("rationale is required")
        self.saved = {
            "label": payload["label"],
            "rationale": payload["rationale"],
            "evidence": payload["evidence"],
        }
        return self.presentation(index)


@dataclass
class _LiveReviewer:
    origin: str
    token: str
    session: _FakeSession

    @property
    def url(self) -> str:
        return f"{self.origin}/{self.token}/"


@contextmanager
def _live_reviewer() -> Iterator[_LiveReviewer]:
    session = _FakeSession()
    token = "test-token"
    server = create_server(session=session, token=token, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    assert host == "127.0.0.1"
    try:
        yield _LiveReviewer(f"http://{host}:{port}", token, session)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _get_json(url: str) -> tuple[dict[str, Any], Any]:
    with urlopen(url) as response:
        return json.loads(response.read()), response.headers


def _post_json(url: str, payload: dict[str, Any]) -> tuple[dict[str, Any], Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request) as response:
        return json.loads(response.read()), response.headers


def test_page_has_review_controls_and_private_headers() -> None:
    with _live_reviewer() as live:
        with urlopen(live.url) as response:
            html = response.read().decode()
            assert response.headers["Cache-Control"] == "no-store"
            assert "default-src 'none'" in response.headers["Content-Security-Policy"]
        assert 'id="label-0"' in html
        assert 'id="label-3"' in html
        assert 'id="rationale"' in html
        assert 'id="save-next"' in html
        assert "Save &amp; next" in html


def test_routes_require_exact_session_token() -> None:
    with _live_reviewer() as live:
        with pytest.raises(HTTPError) as error:
            urlopen(f"{live.origin}/api/wrong/presentation/0")
        assert error.value.code == 404


def test_get_returns_only_visible_presentation_fields() -> None:
    with _live_reviewer() as live:
        view, headers = _get_json(live.url + "api/presentation/0")
        assert view["paper_a"]["title"] == "Fictional source A"
        serialized = json.dumps(view)
        assert "pair_id" not in serialized
        assert "anchor" not in serialized
        assert headers["Cache-Control"] == "no-store"


def test_post_saves_and_get_reloads_answer() -> None:
    with _live_reviewer() as live:
        payload = {
            "label": 2,
            "rationale": "shared decision structure",
            "evidence": {
                "a": ["Evidence sentence A."],
                "b": ["Evidence sentence B."],
            },
        }
        saved, _headers = _post_json(live.url + "api/presentation/0", payload)
        assert saved["answer"] == payload
        reloaded, _headers = _get_json(live.url + "api/presentation/0")
        assert reloaded["answer"] == payload


def test_validation_error_is_json_400_without_private_details() -> None:
    with _live_reviewer() as live:
        with pytest.raises(HTTPError) as error:
            _post_json(
                live.url + "api/presentation/0",
                {"label": 2, "rationale": "", "evidence": {"a": [], "b": []}},
            )
        assert error.value.code == 400
        body = json.loads(error.value.read())
        assert body == {"error": "rationale is required"}
