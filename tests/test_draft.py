"""Draft artifact formatting and lookup errors."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from athanasor.config import Config
from athanasor.skills.draft import _frontmatter, _synthesize_draft, run_draft


def test_frontmatter_survives_colon_in_title() -> None:
    """The default no-LLM title contains a colon; frontmatter must stay valid YAML."""
    markdown = _synthesize_draft(Path("cluster_x.yaml"), {"summary": "s", "paper_ids": ["a"]}, llm=None)
    assert markdown.startswith("---\n")
    frontmatter_block = markdown.split("---\n")[1]
    parsed = yaml.safe_load(frontmatter_block)
    assert isinstance(parsed, dict)
    assert parsed["title"].startswith("Working note:")


def test_frontmatter_quotes_hostile_titles() -> None:
    block = _frontmatter("gap-1", ["p1", "p2"], 'Colons: and "quotes" and #hash')
    parsed = yaml.safe_load(block.strip().strip("-"))
    assert parsed["title"] == 'Colons: and "quotes" and #hash'
    assert "\\n" not in block


def test_run_draft_unknown_gap_id_raises(tmp_path: Path) -> None:
    (tmp_path / "rubedo" / "hypotheses").mkdir(parents=True)
    config = Config(
        llm={},
        embeddings={},
        paths={"project_root": str(tmp_path)},
        domains=["ML"],
        exhaustion={},
        project_root=str(tmp_path),
    )
    with pytest.raises(FileNotFoundError):
        run_draft(gap_id="ghost_cluster", config=config, llm=None)
