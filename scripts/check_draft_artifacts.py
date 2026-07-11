#!/usr/bin/env python3
"""Focused checks for Rubedo draft Markdown formatting."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from athanasor.skills.draft import _append_draft_reference, _frontmatter, _synthesize_draft


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"check failed: {message}")
    print(f"[ok] {message}")


def main() -> int:
    hypothesis = {
        "cluster_id": "cluster_example",
        "summary": "A concrete cluster summary.",
        "paper_ids": ["paper_a", "paper_b"],
        "gaps": [
            {
                "gap_type": "missing_experiment",
                "description": "A specific experiment is missing.",
                "suggested_approach": "Run a small controlled ablation.",
            }
        ],
    }

    markdown = _synthesize_draft(Path("cluster_example.yaml"), hypothesis, llm=None)
    _assert("\\n" not in markdown[:500], "draft markdown uses real newlines near frontmatter")
    _assert(markdown.startswith("---\n"), "draft frontmatter starts on its own line")
    _assert("\n## Title\n" in markdown, "draft body has markdown section newlines")
    _assert(len(markdown.splitlines()) > 10, "draft markdown spans multiple physical lines")

    frontmatter = _frontmatter("cluster_example", ["paper_a"], "Example")
    _assert("\\n" not in frontmatter, "frontmatter helper does not emit literal newline escapes")

    with tempfile.TemporaryDirectory(prefix="azoth-draft-index-") as tmp:
        index_path = Path(tmp) / "index.md"
        _append_draft_reference(index_path, Path("draft.md"), hypothesis)
        raw = index_path.read_text(encoding="utf-8")
        _assert("\\n" not in raw, "draft index uses real newline terminator")
        _assert(raw.endswith("\n"), "draft index entry ends with a real newline")

    print("\nAll draft artifact checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
