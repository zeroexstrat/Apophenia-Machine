"""Draft skill: generate candidate research notes from hypotheses."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

from ..config import Config, load_config
from ..llm import LLMClient
from ..registry import Registry
from ..skills.common import now_iso, write_yaml


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Draft candidate research note from a hypothesis.")
    parser.add_argument("gap_id", nargs="?", help="Hypothesis file id (without extension).")
    parser.add_argument("--top", type=int, default=1, help="Draft top N pending hypotheses.")
    return parser


def _run_vigil(root: Path, phase: str) -> tuple[int, str]:
    result = subprocess.run(
        ["python3", str(root / "athanasor" / "vigil" / "verify.py"), phase],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "Vigil check failed with no details.").strip()
        raise RuntimeError(f"Vigil {phase} failed for draft: {message}")
    return result.returncode, (result.stdout + result.stderr)


def run_draft(
    gap_id: str | None = None,
    *,
    top: int = 1,
    config: Config | None = None,
    llm: LLMClient | None = None,
) -> list[Path]:
    cfg = config or load_config()
    root = Path(cfg.project_root).expanduser().resolve()
    _run_vigil(root, "start")

    hyps_root = root / "rubedo" / "hypotheses"
    if not hyps_root.exists():
        return []

    candidates: list[Path] = []
    if gap_id:
        explicit = root / "rubedo" / "hypotheses" / f"{gap_id}.yaml"
        if explicit.exists():
            candidates = [explicit]
    else:
        candidates = sorted(hyps_root.glob("*.yaml"))
        if top and top > 0:
            candidates = candidates[:top]

    registry = Registry(root / "albedo" / "registry.jsonl")
    outputs: list[Path] = []
    for path in candidates:
        payload = _load_yaml(path)
        if not payload:
            continue
        draft = _synthesize_draft(path, payload, llm)
        slug = _slug(path.stem)
        out_path = root / "rubedo" / "drafts" / f"{slug}.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(draft)
        outputs.append(out_path)

        for paper_id in payload.get("paper_ids", []):
            if not isinstance(paper_id, str):
                continue
            try:
                registry.update(paper_id, {"drafted": True})
            except Exception:
                pass
        _append_draft_reference(root / "rubedo" / "drafts" / "index.md", out_path, payload)

    _run_vigil(root, "verify")
    return outputs


def _load_yaml(path: Path) -> dict[str, Any] | None:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else None


def _synthesize_draft(path: Path, hypothesis: dict[str, Any], llm: LLMClient | None) -> str:
    gap_payload = hypothesis.get("gaps", [])
    top_gap = gap_payload[0] if gap_payload and isinstance(gap_payload, list) else {}
    papers = [pid for pid in hypothesis.get("paper_ids", []) if isinstance(pid, str)]
    gap_type = top_gap.get("gap_type", "unexplored_question") if isinstance(top_gap, dict) else "unexplored_question"
    description = top_gap.get("description", "No specific gap found.") if isinstance(top_gap, dict) else "No gap description."
    approach = top_gap.get("suggested_approach", "Define a targeted follow-up experiment.") if isinstance(top_gap, dict) else ""

    if llm is None:
        title = f"Working note: {path.stem}"
        body = (
            f"## Title\\n{title}\\n\\n"
            f"## Context\\n{hypothesis.get('summary', 'No summary available.')}\\n\\n"
            f"## The Gap\\n{description}\\n\\n"
            "## Proposed Direction\\n"
            f"{approach}\\n\\n"
            "## Open Questions\\n"
            "- Feasibility is unverified.\\n- Evidence strength remains candidate-level.\\n\\n"
            f"## References\\n{', '.join(papers)}\\n"
        )
        return _frontmatter(path.stem, papers, title) + body

    prompt = (
        "You are drafting a 2-page candidate research note. Use hedge language and references.\n\n"
        f"Cluster summary: {hypothesis.get('summary', '')}\n"
        f"Gap type: {gap_type}\nGap description: {description}\nApproach: {approach}\n\n"
        f"Supporting papers: {papers}\n"
    )
    result = llm.complete(prompt, temperature=0.3, max_tokens=1400)
    if not isinstance(result, str):
        result = str(result)
    title = f"Working note: {path.stem}"
    for line in result.splitlines():
        if line.strip().startswith("#"):
            title = line.strip().lstrip("# ").strip()[:120]
            break
    if "## Title" not in result:
        result = (
            f"## Title\\n{title}\\n\\n"
            "## Context\\n"
            f"{hypothesis.get('summary', '')}\\n\\n"
            "## The Gap\\n"
            f"{description}\\n\\n"
            "## Proposed Direction\\n"
            f"{approach}\\n\\n"
            "## Open Questions\\n- If feasible, validate with follow-up work.\\n- Measure transferability across domains.\\n\\n"
            f"## References\\n{', '.join(papers)}\\n"
        )
    return _frontmatter(path.stem, papers, title) + result.strip() + "\n"


def _frontmatter(gap_id: str, papers: list[str], title: str) -> str:
    date = now_iso().split("T")[0]
    return (
        "---\\n"
        f"gap_id: {gap_id}\\n"
        f"title: {title}\\n"
        f"date: {date}\\n"
        "status: pending_review\\n"
        f"papers: [{', '.join(papers)}]\\n"
        "---\\n\\n"
    )


def _append_draft_reference(index_path: Path, draft_path: Path, payload: dict[str, Any]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "a", encoding="utf-8") as f:
        f.write(
            f"- {now_iso()} | {draft_path.name} | gap:{payload.get('cluster_id')} | "
            f"papers:{','.join(str(p) for p in payload.get('paper_ids', []))}\\n"
        )


def _slug(value: str) -> str:
    lowered = re.sub(r"[^a-z0-9]+", "-", value.lower())
    return lowered.strip("-")[:70] or "azoth-draft"
