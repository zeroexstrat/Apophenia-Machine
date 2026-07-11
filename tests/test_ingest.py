"""Ingest skill edge cases: bad PDFs, duplicates, domain override, LLM failures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from athanasor.config import Config
from athanasor.llm import LLMUnavailableError
from athanasor.skills import ingest as ingest_module
from athanasor.skills.ingest import _extract_with_llm, ingest_path


MINIMAL_TEXT = (
    "Abstract\n"
    "We present a fixture paper that studies sparse attention routing for tests.\n"
    "We demonstrate that deterministic ingest fixtures behave predictably.\n"
    "The training objective is L = - sum_i log p(x_i | x_<i).\n"
)


def _write_pdf(path: Path, body: str) -> None:
    lines = [line.strip() for line in body.splitlines() if line.strip()] or [""]
    safe = [ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for ln in lines]
    ops = "\n".join(f"0 -14 Td\n({ln}) Tj" for ln in safe)
    stream = f"BT\n/F1 11 Tf\n72 760 Td\n{ops}\nET\n"
    pdf = (
        "%PDF-1.4\n"
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        "3 0 obj\n<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        "/MediaBox [0 0 612 792] /Contents 5 0 R >>\nendobj\n"
        "4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        f"5 0 obj\n<< /Length {len(stream.encode('utf-8'))} >>\nstream\n{stream}endstream\nendobj\n"
        "trailer\n<< /Size 6 /Root 1 0 R >>\n%%EOF\n"
    )
    path.write_bytes(pdf.encode("utf-8"))


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Config]:
    monkeypatch.setenv("AZOTH_SKIP_VIGIL", "1")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    (tmp_path / "nigredo" / "inbox").mkdir(parents=True)
    (tmp_path / "albedo" / "library").mkdir(parents=True)
    config = Config(
        llm={},
        embeddings={"store_path": "athanasor/embeddings.store", "model": "all-MiniLM-L6-v2"},
        paths={
            "project_root": str(tmp_path),
            "nigredo": "nigredo",
            "albedo": "albedo",
            "citrinitas": "citrinitas",
            "rubedo": "rubedo",
            "athanasor": "athanasor",
        },
        domains=["physics", "ML", "philosophy", "neuroscience", "mathematics", "unclassified", "biology"],
        exhaustion={},
        project_root=str(tmp_path),
    )
    return tmp_path, config


def _registry_entries(root: Path) -> list[dict[str, Any]]:
    path = root / "albedo" / "registry.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_extract_with_llm_raises_typed_error_on_non_dict(project: tuple[Path, Config]) -> None:
    class ListLLM:
        def complete(self, prompt: str, **kwargs: Any) -> Any:
            return ["not", "a", "dict"]

    with pytest.raises(LLMUnavailableError):
        _extract_with_llm(ListLLM(), {"full_text": "text", "filename": "x.pdf"}, {})


def test_ingest_records_skipped_unparseable_pdfs(project: tuple[Path, Config]) -> None:
    root, config = project
    inbox = root / "nigredo" / "inbox"
    _write_pdf(inbox / "good.pdf", MINIMAL_TEXT)
    encrypted = inbox / "encrypted.pdf"
    encrypted.write_bytes(b"%PDF-1.4 garbage not parseable as text\x00\x01")

    outputs = ingest_path(inbox, config=config, llm=None)

    ingested = [o for o in outputs if o.get("status") == "ingested_only"]
    skipped = [o for o in outputs if o.get("status") == "skipped"]
    assert len(ingested) == 1
    assert len(skipped) == 1
    assert skipped[0]["paper_id"] is None
    assert "encrypted.pdf" in skipped[0]["filename"]
    assert skipped[0]["skip_reason"]
    # Unparseable inputs stay in the inbox for human attention.
    assert encrypted.exists()


def test_ingest_continues_after_parser_crash(
    project: tuple[Path, Config], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, config = project
    inbox = root / "nigredo" / "inbox"
    _write_pdf(inbox / "aaa_crash.pdf", MINIMAL_TEXT)
    _write_pdf(inbox / "bbb_good.pdf", MINIMAL_TEXT)

    real_parse = ingest_module.parse_pdf

    def exploding_parse(path: Any) -> dict[str, Any]:
        if "aaa_crash" in str(path):
            raise RuntimeError("simulated parser crash")
        return real_parse(path)

    monkeypatch.setattr(ingest_module, "parse_pdf", exploding_parse)
    outputs = ingest_path(inbox, config=config, llm=None)

    statuses = sorted(str(o.get("status")) for o in outputs)
    assert statuses == ["ingested_only", "skipped"]
    entries = _registry_entries(root)
    assert len(entries) == 1


def test_ingest_dedupes_identical_content(project: tuple[Path, Config]) -> None:
    root, config = project
    inbox = root / "nigredo" / "inbox"
    _write_pdf(inbox / "paper.pdf", MINIMAL_TEXT)
    first = ingest_path(inbox, config=config, llm=None)
    assert len(first) == 1

    # The same content arrives again under the same name.
    _write_pdf(inbox / "paper.pdf", MINIMAL_TEXT)
    second = ingest_path(inbox, config=config, llm=None)

    entries = _registry_entries(root)
    assert len(entries) == 1, "duplicate content must not mint a second registry entry"
    dup_records = [o for o in second if o.get("status") == "skipped"]
    assert dup_records and "duplicate" in dup_records[0]["skip_reason"].lower()


def test_ingest_honors_custom_domain_from_config(project: tuple[Path, Config]) -> None:
    root, config = project
    inbox = root / "nigredo" / "inbox"
    _write_pdf(inbox / "bio.pdf", MINIMAL_TEXT)

    outputs = ingest_path(inbox, config=config, llm=None, domain_override="biology")

    assert len(outputs) == 1
    assert outputs[0]["domain"] == "biology"
    assert (root / "nigredo" / "biology" / "bio.pdf").exists()


def test_ingest_rejects_unknown_domain_override(project: tuple[Path, Config]) -> None:
    root, config = project
    inbox = root / "nigredo" / "inbox"
    _write_pdf(inbox / "odd.pdf", MINIMAL_TEXT)

    outputs = ingest_path(inbox, config=config, llm=None, domain_override="astrology")

    assert len(outputs) == 1
    assert outputs[0]["domain"] == "unclassified"


def test_ingest_survives_llm_payload_without_source(project: tuple[Path, Config]) -> None:
    root, config = project
    inbox = root / "nigredo" / "inbox"
    _write_pdf(inbox / "nosource.pdf", MINIMAL_TEXT)

    class NoSourceLLM:
        def complete(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
            if "Classify this paper" in prompt:
                return {"domain": "ML", "confidence": 0.9, "reasoning": "fixture"}
            return {"schema_version": 1, "claims": [], "tags": ["fixture"]}

    outputs = ingest_path(inbox, config=config, llm=NoSourceLLM())

    assert len(outputs) == 1
    assert outputs[0]["status"] == "ingested_only"
    library_file = root / outputs[0]["paths"]["library"]
    payload = yaml.safe_load(library_file.read_text(encoding="utf-8"))
    assert isinstance(payload["source"], dict)
    assert payload["source"]["title"]


def test_ingest_accepts_plain_text_files(project: tuple[Path, Config]) -> None:
    root, config = project
    inbox = root / "nigredo" / "inbox"
    (inbox / "notes.txt").write_text(MINIMAL_TEXT, encoding="utf-8")
    (inbox / "essay.md").write_text("# Essay\n\n" + MINIMAL_TEXT, encoding="utf-8")

    outputs = ingest_path(inbox, config=config, llm=None)

    ingested = [o for o in outputs if o.get("status") == "ingested_only"]
    assert len(ingested) == 2
    entries = _registry_entries(root)
    assert len(entries) == 2
