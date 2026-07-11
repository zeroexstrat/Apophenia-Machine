"""PII title scrubber: detect and replace personal-data-shaped titles."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def _mod():
    spec = importlib.util.spec_from_file_location(
        "scrub_pii_under_test", REPO_ROOT / "scripts" / "scrub_pii_titles.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Synthetic PII only — never the real corpus strings.
PII_TITLES = [
    "1 Independent Researcher, 12345 Faketown, Nowhere",
    "ORCID: 0000-0001-2345-6789",
    "contact the author at nobody@example.com",
    "A R T I C L E   I N F O",
    "Smith et al.",
    "Edited By",
]
CLEAN_TITLES = [
    "Sparse Attention for Long Documents",
    "Bioelectric Signaling in Regeneration",
    "A Theory of Looped Transformers",
]


def test_detects_synthetic_pii_titles() -> None:
    scrub = _mod()
    for title in PII_TITLES:
        assert scrub.title_is_pii(title), title


def test_leaves_clean_titles_alone() -> None:
    scrub = _mod()
    for title in CLEAN_TITLES:
        assert not scrub.title_is_pii(title), title


def test_placeholder_is_stable_and_not_pii() -> None:
    scrub = _mod()
    a = scrub.placeholder("orcid0000_123456789", "biology")
    b = scrub.placeholder("orcid0000_123456789", "biology")
    assert a == b  # deterministic
    assert not scrub.title_is_pii(a)  # idempotent — a scrubbed title is never re-flagged
    assert "0000" not in a  # no PII fragment leaks from the id into the placeholder


def test_redact_spans_removes_pii_but_keeps_text() -> None:
    scrub = _mod()
    out = scrub.redact_spans("We thank 0000-0001-2345-6789 and mail nobody@example.com now.")
    assert "0000-0001-2345-6789" not in out
    assert "nobody@example.com" not in out
    assert "We thank" in out and "now." in out
    assert "[redacted]" in out


def _seed(root: Path, paper_id: str, title: str, domain: str = "unclassified", claim: str = "A claim.") -> None:
    (root / "albedo" / "library").mkdir(parents=True, exist_ok=True)
    (root / "albedo" / "exhaust").mkdir(parents=True, exist_ok=True)
    (root / "albedo" / "library" / f"{paper_id}.yaml").write_text(
        yaml.safe_dump({"id": paper_id, "source": {"title": title}, "claims": [{"statement": claim}]}),
        encoding="utf-8",
    )
    (root / "albedo" / "exhaust" / f"{paper_id}_exhaust.yaml").write_text(
        yaml.safe_dump({"schema_version": 2, "exhaustion": {"paper_id": paper_id, "paper_title": title}}),
        encoding="utf-8",
    )
    with open(root / "albedo" / "registry.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"paper_id": paper_id, "title": title, "domain": domain, "status": "exhausted",
                            "source": {"title": title}, "paths": {}}) + "\n")


def test_scrub_replaces_pii_titles_everywhere_and_is_idempotent(tmp_path: Path) -> None:
    scrub = _mod()
    _seed(tmp_path, "pii_1", "ORCID: 0000-0001-2345-6789", domain="biology",
          claim="Address 0000-0001-2345-6789 leaked into a claim.")
    _seed(tmp_path, "clean_1", "Sparse Attention for Long Documents", domain="ML")

    report = scrub.scrub(tmp_path, apply=True)
    assert report["titles_scrubbed"] >= 1

    reg = {json.loads(l)["paper_id"]: json.loads(l)
           for l in (tmp_path / "albedo" / "registry.jsonl").read_text().splitlines() if l.strip()}
    assert not scrub.title_is_pii(reg["pii_1"]["title"])
    assert not scrub.title_is_pii(reg["pii_1"]["source"]["title"])
    assert reg["clean_1"]["title"] == "Sparse Attention for Long Documents"  # untouched

    lib = yaml.safe_load((tmp_path / "albedo" / "library" / "pii_1.yaml").read_text())
    assert not scrub.title_is_pii(lib["source"]["title"])
    assert "0000-0001-2345-6789" not in lib["claims"][0]["statement"]  # claim PII redacted

    exh = yaml.safe_load((tmp_path / "albedo" / "exhaust" / "pii_1_exhaust.yaml").read_text())
    assert not scrub.title_is_pii(exh["exhaustion"]["paper_title"])

    # Idempotent: a second pass changes nothing.
    report2 = scrub.scrub(tmp_path, apply=True)
    assert report2["titles_scrubbed"] == 0


def test_report_mode_does_not_mutate(tmp_path: Path) -> None:
    scrub = _mod()
    _seed(tmp_path, "pii_2", "ORCID: 0000-0001-2345-6789")
    before = (tmp_path / "albedo" / "registry.jsonl").read_text()
    report = scrub.scrub(tmp_path, apply=False)
    assert report["titles_scrubbed"] >= 1  # would scrub
    assert (tmp_path / "albedo" / "registry.jsonl").read_text() == before  # but didn't


def test_redact_spans_removes_street_addresses() -> None:
    scrub = _mod()
    for pii, keep in [
        ("Based at 77 Massachusetts Avenue, we show X.", "we show X."),
        ("Author at 23 Rue des Lavandieres studied Y.", "studied Y."),
        ("Lab in Cambridge, MA 02139 reports Z.", "reports Z."),
    ]:
        out = scrub.redact_spans(pii)
        assert "[redacted]" in out
        assert keep in out
        # Residual must no longer look like an address.
        assert not scrub.PII_RULES[2][1].search(out.replace("[redacted]", ""))


def test_detects_city_state_zip_titles() -> None:
    scrub = _mod()
    # "Place, ST 02139" order — missed by a naive ZIP-first rule.
    assert scrub.title_is_pii("Cambridge, MA 02139")
    assert scrub.title_is_pii("Some Lab, Cambridge, MA 02139 USA")
    # title_is_pii must be a superset of the strict span verifier.
    assert scrub.title_is_pii("Massachusetts Avenue building")
