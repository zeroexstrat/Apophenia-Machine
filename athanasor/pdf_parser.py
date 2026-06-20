"""PDF parser with lightweight heuristic structure extraction."""

from __future__ import annotations

import re
from collections import defaultdict
import shutil
import subprocess
from pathlib import Path
from statistics import median
from typing import Any

try:
    import fitz
except Exception:  # pragma: no cover
    fitz = None


def parse_pdf(path: str | Path) -> dict[str, Any]:
    pdf_path = Path(path).expanduser().resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    text_chunks: list[tuple[int, str]] = []
    sections: list[dict[str, Any]] = []
    references: list[str] = []
    equations: list[dict[str, str]] = []
    full_lines: list[str] = []
    parse_warnings: list[str] = []
    abstract: str | None = None

    if fitz is None:
        fallback_text = _extract_with_pdftotext(pdf_path)
        if fallback_text is None:
            parse_warnings.append(
                "PyMuPDF unavailable and pdftotext fallback unavailable; skipping PDF parsing."
            )
            return {
                "path": str(pdf_path),
                "filename": pdf_path.name,
                "page_count": 0,
                "full_text": "",
                "sections": [],
                "references": [],
                "equations": [],
                "abstract": None,
                "parse_warnings": parse_warnings,
                "encrypted": False,
                "image_only": True,
            }

        parse_warnings.append("Parsed PDF via pdftotext fallback (PyMuPDF unavailable).")
        lines = fallback_text.splitlines()
        text_chunks.append((1, fallback_text))
        full_lines.extend(lines)
        sections.extend(_detect_section_headers(lines, 1))
        for line in lines[:60]:
            normalized = line.strip()
            if not normalized:
                continue
            if abstract is None and len(normalized) > 30 and _looks_like_abstract(normalized):
                abstract = normalized
                break
        full_text = "\n".join(line.strip() for line in lines if line.strip())

        lower_text = full_text.lower()
        references_start = None
        for marker in ("references", "bibliography"):
            idx = lower_text.find(f"\n{marker}")
            if idx != -1:
                references_start = idx
                break
        if references_start is not None:
            ref_text = full_text[references_start:]
            for line in ref_text.splitlines():
                if line.strip():
                    references.append(line.strip())
        equations = _extract_equation_lines(full_text)

        return {
            "path": str(pdf_path),
            "filename": pdf_path.name,
            "page_count": 1,
            "full_text": full_text,
            "sections": _merge_sections(sections),
            "references": [item for item in references if item.strip()],
            "equations": equations,
            "abstract": abstract,
            "parse_warnings": parse_warnings,
            "encrypted": False,
            "image_only": len(full_text.strip()) == 0,
        }

    doc = fitz.open(str(pdf_path))
    if doc.needs_pass:
        parse_warnings.append("PDF is encrypted and could not be opened.")
        return {
            "path": str(pdf_path),
            "filename": pdf_path.name,
            "page_count": len(doc),
            "full_text": "",
            "sections": [],
            "references": [],
            "equations": [],
            "abstract": None,
            "parse_warnings": parse_warnings,
            "encrypted": True,
            "image_only": False,
        }

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        raw = page.get_text("text")
        blocks = page.get_text("dict")["blocks"]
        if not raw.strip():
            parse_warnings.append(f"Page {page_idx + 1} is empty.")
            continue

        lines = raw.splitlines()
        full_lines.extend(lines)
        text_chunks.append((page_idx + 1, raw))

        # Multi-column heuristic: detect strongly separated x-ranges and merge in y-order.
        if blocks:
            x_positions = []
            for block in blocks:
                if block.get("type") != 0:
                    continue
                bbox = block.get("bbox", [0, 0, 0, 0])
                x0 = bbox[0]
                x_positions.append(x0)
            if x_positions:
                unique_x = sorted(set(int(x) for x in x_positions))
                if len(unique_x) >= 2:
                    # If two dominant column bands exist, preserve by band order.
                    threshold = max(1, median(unique_x))
                    left_blocks = []
                    right_blocks = []
                    for block in blocks:
                        if block.get("type") != 0:
                            continue
                        text = "\n".join(line["text"] for line in block.get("lines", []) for line in line.get("spans", []))
                        bbox = block.get("bbox", [0, 0, 0, 0])
                        bucket = left_blocks if bbox[0] < threshold else right_blocks
                        if text.strip():
                            bucket.append((bbox[1], text.strip()))
                    if left_blocks and right_blocks:
                        interleaved = "\n".join(item[1] for item in sorted(left_blocks + right_blocks))
                        # Replace current page text with ordered estimate.
                        lines = interleaved.splitlines()

        candidate_sections = _detect_section_headers(lines, page_idx + 1)
        sections.extend(candidate_sections)

        # Collect abstract if likely near top and before first heading.
        for line in lines[:60]:
            normalized = line.strip()
            if not normalized:
                continue
            if abstract is None and len(normalized) > 30 and _looks_like_abstract(normalized):
                abstract = normalized
                break

    full_text = "\n".join(chunk for _, chunk in text_chunks)
    lower_text = full_text.lower()
    references_start = None
    for marker in ("references", "bibliography"):
        idx = lower_text.find(f"\n{marker}")
        if idx != -1:
            references_start = idx
            break
    if references_start is not None:
        ref_text = full_text[references_start:]
        for line in ref_text.splitlines():
            if line.strip():
                references.append(line.strip())
    equations = _extract_equation_lines(full_text)

    return {
        "path": str(pdf_path),
        "filename": pdf_path.name,
        "page_count": len(doc),
        "full_text": full_text.strip(),
        "sections": _merge_sections(sections),
        "references": [item for item in references if item.strip()],
        "equations": equations,
        "abstract": abstract,
        "parse_warnings": parse_warnings,
        "encrypted": False,
        "image_only": len(full_lines) == 0,
    }


def _looks_like_abstract(text: str) -> bool:
    lowered = text.lower()
    return "this paper" in lowered or "we present" in lowered or "we study" in lowered


def _detect_section_headers(lines: list[str], page_no: int) -> list[dict[str, Any]]:
    headers = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^\d+(\.\d+)*\s+.+", stripped):
            headers.append(
                {
                    "title": stripped,
                    "text": "",
                    "start_page": page_no,
                }
            )
        elif len(stripped) < 90 and stripped.isupper():
            headers.append(
                {
                    "title": stripped.title(),
                    "text": "",
                    "start_page": page_no,
                }
            )
    return headers


def _merge_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not sections:
        return []
    by_title = defaultdict(list)
    for item in sections:
        by_title[item["title"]].append(item["start_page"])
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in sections:
        title = item["title"]
        if title in seen:
            continue
        seen.add(title)
        merged.append(item)
    return merged


def _extract_equation_lines(text: str) -> list[dict[str, str]]:
    equations: list[dict[str, str]] = []
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    equation_pattern = re.compile(r"([A-Za-z0-9_{}^<>|()\\/\[\]\s.,:+\-*]+=[^.;\n]{2,})")
    for idx, line in enumerate(lines):
        if len(line) > 240:
            continue
        if not any(symbol in line for symbol in ("=", "\u2211", "\\sum", "\\int", "\u2264", ">=", "<=", "->", "\u2192")):
            continue
        match = equation_pattern.search(line)
        expression = (match.group(1) if match else line).strip()
        if len(expression) < 5:
            continue
        context_parts = []
        if idx > 0:
            context_parts.append(lines[idx - 1])
        context_parts.append(line)
        if idx + 1 < len(lines):
            context_parts.append(lines[idx + 1])
        equations.append(
            {
                "label": f"equation_{len(equations) + 1}",
                "expression": expression[:240],
                "context": " ".join(context_parts)[:500],
            }
        )
        if len(equations) >= 12:
            break
    return equations


def _extract_with_pdftotext(path: Path) -> str | None:
    executable = shutil.which("pdftotext")
    if not executable:
        return None

    try:
        result = subprocess.run(
            [executable, "-layout", str(path), "-"],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except Exception:
        return None

    if result.returncode != 0:
        return None
    return result.stdout
