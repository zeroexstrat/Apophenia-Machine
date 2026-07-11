"""Ouroboros URL safety and download bounds."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest

from athanasor.skills import ouroboros as ouroboros_module
from athanasor.skills.ouroboros import _download_pdf, resolve_source_url


def test_resolve_source_url_accepts_http_pdf_and_arxiv() -> None:
    assert (
        resolve_source_url("https://arxiv.org/abs/2604.12946v1")
        == "https://arxiv.org/pdf/2604.12946v1.pdf"
    )
    assert (
        resolve_source_url("https://example.org/p/x.pdf")
        == "https://example.org/p/x.pdf"
    )


def test_resolve_source_url_rejects_non_http_schemes() -> None:
    assert resolve_source_url("ftp://example.org/p/x.pdf") is None
    assert resolve_source_url("file:///etc/passwd.pdf") is None
    assert resolve_source_url("javascript:alert(1).pdf") is None


class _FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, content_type: str = "application/pdf") -> None:
        super().__init__(body)
        self.headers = {"Content-Type": content_type}

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: Any) -> None:
        return None


def test_download_pdf_enforces_size_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ouroboros_module, "MAX_DOWNLOAD_BYTES", 1024)
    monkeypatch.setattr(ouroboros_module, "_assert_public_host", lambda url: None)
    body = b"%PDF-1.4" + b"x" * 4096

    monkeypatch.setattr(
        ouroboros_module.urllib.request,
        "urlopen",
        lambda request, timeout=None: _FakeResponse(body),
    )
    with pytest.raises(RuntimeError, match="size"):
        _download_pdf("https://example.org/big.pdf", tmp_path / "big.pdf", timeout=5)
    assert not (tmp_path / "big.pdf").exists()


def test_download_pdf_writes_within_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    body = b"%PDF-1.4 fixture"
    monkeypatch.setattr(ouroboros_module, "_assert_public_host", lambda url: None)
    monkeypatch.setattr(
        ouroboros_module.urllib.request,
        "urlopen",
        lambda request, timeout=None: _FakeResponse(body),
    )
    result = _download_pdf("https://example.org/ok.pdf", tmp_path / "ok.pdf", timeout=5)
    assert result["ok"] is True
    assert (tmp_path / "ok.pdf").read_bytes() == body


def test_download_pdf_requires_magic_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A .pdf URL serving non-PDF content must be rejected (no extension trust)."""
    body = b"<html>not a pdf</html>"
    monkeypatch.setattr(
        ouroboros_module.urllib.request,
        "urlopen",
        lambda request, timeout=None: _FakeResponse(body, content_type="application/pdf"),
    )
    monkeypatch.setattr(ouroboros_module, "_assert_public_host", lambda url: None)
    with pytest.raises(RuntimeError, match="PDF"):
        _download_pdf("https://example.org/fake.pdf", tmp_path / "fake.pdf", timeout=5)
    assert not (tmp_path / "fake.pdf").exists()


def test_download_pdf_rejects_private_hosts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))]

    monkeypatch.setattr(ouroboros_module.socket, "getaddrinfo", fake_getaddrinfo)
    called = {"n": 0}
    monkeypatch.setattr(
        ouroboros_module.urllib.request,
        "urlopen",
        lambda *a, **k: called.__setitem__("n", called["n"] + 1),
    )
    with pytest.raises(RuntimeError, match="private|loopback|internal"):
        _download_pdf("https://internal.corp/doc.pdf", tmp_path / "doc.pdf", timeout=5)
    assert called["n"] == 0  # rejected before any network fetch
