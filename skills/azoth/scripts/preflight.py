#!/usr/bin/env python3
"""Azoth skill preflight — verify the environment before any pipeline run.

Runs three checks and prints a READY / NOT READY verdict:

  1. The ``azoth`` package (``athanasor``) is importable.
  2. PDF text extraction is available (PyMuPDF or the ``pdftotext`` binary).
  3. The configured LLM backend answers one small probe call.

Why this exists: with a dead LLM backend, ``azoth`` silently falls back to
heuristic extraction. A heuristic "exhaustion" still writes artifacts and bumps
``exhausted_at_depth`` — so a degraded run looks successful while producing junk.
Preflight makes that failure loud *before* a batch, not invisible after it.

Exit codes:
  0  READY (LLM reachable, or --allow-no-llm passed for a deliberate offline run)
  3  azoth is not installed
  4  LLM backend required but unreachable
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

PINNED_INSTALL = "pip install 'git+https://github.com/zeroexstrat/Apophenia-Machine@v0.2.0'"


def _install_hint() -> str:
    """Prefer an editable install from the bundled repo so skill and code match."""
    # skills/azoth/scripts/preflight.py -> repo root is three parents up.
    root = Path(__file__).resolve().parents[3]
    if (root / "pyproject.toml").exists() and (root / "athanasor").is_dir():
        return f"pip install -e {root}"
    return PINNED_INSTALL


INSTALL_HINT = _install_hint()


def _check_pdf_extraction() -> str:
    try:
        import fitz  # noqa: F401  (PyMuPDF)

        return "PyMuPDF"
    except Exception:
        pass
    if shutil.which("pdftotext"):
        return "pdftotext"
    return ""


def _probe_llm(project_root: Path) -> tuple[bool, str]:
    """Make one tiny real call through the configured backend."""
    os.environ.setdefault("AZOTH_PROJECT_ROOT", str(project_root))
    try:
        from athanasor.config import load_config
        from athanasor.llm import LLMClient, LLMUnavailableError
    except Exception as exc:  # pragma: no cover - import guarded by caller
        return False, f"could not import azoth runtime: {exc}"

    cfg = load_config()
    provider = cfg.llm.get("provider")
    model = cfg.llm.get("model")
    client = LLMClient(cfg)
    if client.client is None:
        return False, f"no client for provider '{provider}' (check config/credentials)"

    try:
        client.complete("Reply with the single word OK.", max_tokens=8, retries=1)
    except LLMUnavailableError as exc:
        return False, f"provider '{provider}' model '{model}' did not answer: {exc}"
    except Exception as exc:  # network, auth, etc.
        return False, f"probe call failed: {exc}"
    return True, f"provider '{provider}' model '{model}' answered"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preflight the Azoth environment.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--allow-no-llm",
        action="store_true",
        help="Treat an unreachable LLM as acceptable (deliberate heuristic/offline run).",
    )
    args = parser.parse_args(argv)

    print("Azoth preflight")
    print("===============")

    try:
        import athanasor  # noqa: F401
    except Exception:
        print("[FAIL] azoth is not installed.")
        print("       Install the pinned release:")
        print(f"         {INSTALL_HINT}")
        return 3
    print("[ ok ] azoth package importable")

    extractor = _check_pdf_extraction()
    if extractor:
        print(f"[ ok ] PDF extraction available ({extractor})")
    else:
        print("[warn] No PDF extractor found. PDFs will be skipped; .txt/.md still work.")
        print("       Install PyMuPDF (pip install pymupdf) or poppler (pdftotext).")

    ready, detail = _probe_llm(args.project_root.resolve())
    if ready:
        print(f"[ ok ] LLM backend reachable — {detail}")
        print("\nREADY: full LLM-quality run is available.")
        return 0

    print(f"[FAIL] LLM backend unreachable — {detail}")
    if args.allow_no_llm:
        print("\nREADY (heuristic only): --allow-no-llm set. Extraction/exhaustion will be")
        print("        heuristic; tell the user their results are low-fidelity candidates.")
        return 0
    print("\nNOT READY: start/point to an LLM backend, or re-run with --allow-no-llm for a")
    print("           deliberate offline pass. Do NOT run exhaust/connect/detect on a dead")
    print("           backend — it will burn exhausted_at_depth on empty artifacts.")
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
