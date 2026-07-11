"""Shared helper edge cases."""

from __future__ import annotations

from pathlib import Path

from athanasor.skills.common import move_to_domain, slugify


def test_move_to_domain_preserves_all_colliding_files(tmp_path: Path) -> None:
    """Repeated name collisions must never silently overwrite an earlier file."""
    domain = tmp_path / "domain"
    contents = [b"first", b"second", b"third"]
    for idx, body in enumerate(contents):
        src_dir = tmp_path / f"src{idx}"
        src_dir.mkdir()
        src = src_dir / "paper.pdf"
        src.write_bytes(body)
        move_to_domain(src, domain)

    stored = sorted(p.read_bytes() for p in domain.glob("*.pdf"))
    assert stored == sorted(contents)


def test_slugify_falls_back_for_non_ascii() -> None:
    assert slugify("量子力学") == "item"
    assert slugify("Hello, World!") == "hello-world"
