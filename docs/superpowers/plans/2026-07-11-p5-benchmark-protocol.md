# P5-T1 Frozen Benchmark Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze a source-backed 12-paper operations-decision-support benchmark, a public protocol and blinding contract, and Rafael's private 66-pair gold packet before any P6 runner or scorer implementation.

**Architecture:** Add a focused `athanasor.benchmark` library for canonical identities, validation, adjudication, and freeze commitments. Keep public source metadata, rubric, metric contracts, prompt, and commitment under one versioned benchmark directory; keep source bytes and gold labels outside Git and bind the private packet to the public tree with canonical SHA-256. A standalone audit script validates P5 without adding the P6 product CLI.

**Tech Stack:** Python 3.10-3.12, standard-library `dataclasses`, `hashlib`, `json`, `random`, `tempfile`, and `urllib`; PyYAML; pytest; existing Vigil and public-tree audits.

## Global Constraints

- Work only on `P5-T1 — Frozen benchmark protocol and gold-label packet` at Ultra effort.
- Use exactly 12 exact-version papers at 4/4/4 lane balance and exactly 66 unordered canonical pairs.
- Rafael is the sole final authority for 0-3 labels; labels 2-3 are relevant.
- Commit no third-party source bytes. Keep sources and gold under the explicit external root in `AZOTH_P5_PRIVATE_ROOT`.
- Public Git contains no gold labels, rationales, evidence spans, private paths, or source bytes before P7 locks outputs.
- Freeze sources, versions, hashes, selection decisions, rubric, metrics, thresholds, uncertainty, prompt, and blinding before P6.
- Any frozen-field change creates a new benchmark version; never overwrite `operations-decision-support-v1` in place.
- P5 implements validation and freeze mechanics only. Do not add generation, scoring, reporting, or performance claims.
- Synthetic fixtures validate contracts only and support no scientific claim.
- All private writes are atomic and fail closed.
- Preserve the clean public lineage and keep all generated research artifacts `pending_review`.

## File Map

- Create `athanasor/benchmark/__init__.py`: stable P5 exports.
- Create `athanasor/benchmark/protocol.py`: canonical JSON, IDs, pairs, public validation, and leakage checks.
- Create `athanasor/benchmark/freeze.py`: private adjudication, reconciliation, commitment, and atomic writes.
- Create `scripts/check_benchmark_protocol.py`: standalone P5 audit, not the P6 CLI.
- Create `benchmarks/operations-decision-support-v1/{README.md,sources.yaml,selection-log.yaml,protocol.yaml,blinded-packet-schema.yaml,generation-prompt.md,freeze-manifest.json}`.
- Create `benchmarks/operations-decision-support-v1/synthetic/{sources.yaml,blinded-packet.json}`.
- Create `tests/test_benchmark_protocol.py`, `tests/test_benchmark_freeze.py`, and `tests/test_benchmark_check.py`.
- Create `tests/benchmark_fixtures.py`: shared complete synthetic public/private benchmark builders for focused tests.
- Modify `scripts/check_public_tree.py`, `tests/test_public_tree.py`, `.github/workflows/hardening.yml`, `README.md`, and `PROJECT_ROADMAP.md`.

---

### Task 1: Canonical identities and 66-pair enumeration

**Files:**
- Create: `athanasor/benchmark/__init__.py`
- Create: `athanasor/benchmark/protocol.py`
- Create: `tests/test_benchmark_protocol.py`

**Interfaces:**
- Consumes: stable source identifier and exact version strings.
- Produces: `BenchmarkProtocolError`, `LANES`, `canonical_json_bytes(value) -> bytes`, `canonical_digest(value) -> str`, `paper_id(stable_identifier, exact_version) -> str`, `pair_id(first, second) -> str`, and `canonical_pairs(paper_ids) -> list[dict[str, str]]`.

- [ ] **Step 1: Write failing identity tests**

```python
import pytest

from athanasor.benchmark.protocol import (
    BenchmarkProtocolError,
    canonical_digest,
    canonical_pairs,
    paper_id,
    pair_id,
)


def test_paper_and_pair_ids_are_order_stable() -> None:
    first = paper_id("doi:10.3386/w23180", "nber-working-paper-23180-2017-02")
    second = paper_id("arxiv:1809.05504", "v1")
    assert first.startswith("paper_") and len(first) == 22
    assert pair_id(first, second) == pair_id(second, first)


def test_canonical_pairs_produce_exactly_66_unique_pairs() -> None:
    ids = [f"paper_{index:016x}" for index in range(12)]
    pairs = canonical_pairs(ids)
    assert len(pairs) == 66
    assert len({row["pair_id"] for row in pairs}) == 66
    assert all(row["paper_a_id"] < row["paper_b_id"] for row in pairs)


def test_canonical_pairs_reject_duplicates() -> None:
    with pytest.raises(BenchmarkProtocolError, match="12 unique paper IDs"):
        canonical_pairs(["paper_0000000000000000"] * 12)


def test_canonical_digest_ignores_mapping_order() -> None:
    assert canonical_digest({"b": 2, "a": 1}) == canonical_digest({"a": 1, "b": 2})
```

- [ ] **Step 2: Run the focused tests and confirm collection fails**

Run: `uv run pytest tests/test_benchmark_protocol.py -q`

Expected: `ModuleNotFoundError: No module named 'athanasor.benchmark'`.

- [ ] **Step 3: Implement the canonical primitives**

```python
from __future__ import annotations

import hashlib
import json
import re
from itertools import combinations
from typing import Any


LANES = (
    "operations_prescriptive_decision_support",
    "ml_data_science_planning",
    "human_organizational_decision_making",
)
PAPER_ID_PATTERN = re.compile(r"paper_[0-9a-f]{16}")


class BenchmarkProtocolError(ValueError):
    """A benchmark artifact violates the frozen P5 contract."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def paper_id(stable_identifier: str, exact_version: str) -> str:
    identity = {
        "stable_identifier": " ".join(stable_identifier.split()).casefold(),
        "exact_version": " ".join(exact_version.split()).casefold(),
    }
    if not all(identity.values()):
        raise BenchmarkProtocolError("paper identity requires stable_identifier and exact_version")
    return f"paper_{canonical_digest(identity)[:16]}"


def pair_id(first: str, second: str) -> str:
    papers = sorted((first, second))
    if papers[0] == papers[1] or not all(PAPER_ID_PATTERN.fullmatch(item) for item in papers):
        raise BenchmarkProtocolError("benchmark pair requires two distinct valid paper IDs")
    return f"pair_{canonical_digest(papers)[:16]}"


def canonical_pairs(paper_ids: list[str]) -> list[dict[str, str]]:
    unique = sorted(set(paper_ids))
    if len(paper_ids) != 12 or len(unique) != 12:
        raise BenchmarkProtocolError("benchmark requires exactly 12 unique paper IDs")
    if not all(PAPER_ID_PATTERN.fullmatch(item) for item in unique):
        raise BenchmarkProtocolError("benchmark contains an invalid paper ID")
    return [
        {"pair_id": pair_id(a, b), "paper_a_id": a, "paper_b_id": b}
        for a, b in combinations(unique, 2)
    ]
```

Export only the public names from `athanasor/benchmark/__init__.py`.

- [ ] **Step 4: Run tests and commit**

Run: `uv run pytest tests/test_benchmark_protocol.py -q`

Expected: Task 1 tests pass.

```bash
git add athanasor/benchmark tests/test_benchmark_protocol.py
git commit -m "feat: add canonical benchmark identities"
```

---

### Task 2: Public protocol and blinding validators

**Files:**
- Modify: `athanasor/benchmark/protocol.py`
- Modify: `athanasor/benchmark/__init__.py`
- Create: `tests/benchmark_fixtures.py`
- Modify: `tests/test_benchmark_protocol.py`

**Interfaces:**
- Consumes: source, protocol, blinded-schema, freeze-manifest, and generation-packet mappings.
- Produces: `EXPECTED_P5_THRESHOLDS`, `load_mapping`, `validate_sources`, `validate_source_directory`, `validate_protocol`, `validate_blinded_packet`, `validate_freeze_manifest`, and `validate_public_bundle`.

- [ ] **Step 1: Define shared complete fixtures**

```python
# tests/benchmark_fixtures.py
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from athanasor.benchmark.protocol import EXPECTED_P5_THRESHOLDS, LANES, paper_id


def synthetic_source_bytes(stable_identifier: str, exact_version: str) -> bytes:
    return f"Synthetic source for {stable_identifier} at {exact_version}.\n".encode("utf-8")


def source_manifest_fixture() -> dict[str, Any]:
    sources = []
    for lane_index, lane in enumerate(LANES):
        for item_index in range(4):
            stable = f"doi:10.0000/synthetic.{lane_index}.{item_index}"
            version = "v1"
            source_bytes = synthetic_source_bytes(stable, version)
            sources.append({
                "paper_id": paper_id(stable, version),
                "title": f"Synthetic decision paper {lane_index}-{item_index}",
                "authors": ["Synthetic Author"],
                "lane": lane,
                "stable_identifier": stable,
                "exact_version": version,
                "publication_date": "2026-01-01",
                "canonical_url": f"https://example.invalid/source/{lane_index}/{item_index}",
                "download_url": f"https://example.invalid/download/{lane_index}/{item_index}",
                "access_date": "2026-07-11",
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
                "license": "synthetic-test-only",
                "license_evidence_url": "https://example.invalid/license",
                "redistribution_status": "fetch_only",
                "retrieval": {"method": "https_get", "redirect_policy": "record_exact_chain"},
                "source_text_quality": "born_digital_synthetic",
            })
    return {"schema_version": 1, "benchmark_id": "operations-decision-support-v1", "sources": sources}


def write_private_source_fixture(root: Path, payload: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for source in payload["sources"]:
        (root / f"{source['paper_id']}.pdf").write_bytes(
            synthetic_source_bytes(source["stable_identifier"], source["exact_version"])
        )
        (root / f"{source['paper_id']}.retrieval.json").write_text(json.dumps({
            "requested_url": source["download_url"],
            "redirect_chain": [source["download_url"]],
            "final_url": source["download_url"],
            "media_type": "application/pdf",
            "access_date": source["access_date"],
            "exact_version": source["exact_version"],
            "license_evidence_url": source["license_evidence_url"],
            "sha256": source["sha256"],
        }, sort_keys=True), encoding="utf-8")


def protocol_fixture() -> dict[str, Any]:
    metrics = []
    for name, threshold in EXPECTED_P5_THRESHOLDS.items():
        metrics.append({
            "name": name,
            "population": "synthetic evaluation records",
            "numerator": "records meeting the named criterion",
            "denominator": "all eligible records",
            "averaging": "contract-defined",
            "undefined_case": "report null and denominator zero",
            "uncertainty": "Wilson 95% interval or paired bootstrap seed 5607",
            "future_artifact": "P7 locked report",
            "comparison": threshold["operator"],
            "threshold": threshold,
        })
    return {
        "schema_version": 1,
        "benchmark_id": "operations-decision-support-v1",
        "rubric_version": "pair-relevance-v1",
        "rubric": {"scale": {0: "none", 1: "topical", 2: "structural", 3: "transferable"}, "relevant_labels": [2, 3]},
        "adjudication": {"final_authority": "Rafael", "canonical_pair_count": 66, "presentation_seed": 5607, "repeated_anchor_count": 4},
        "metrics": metrics,
        "no_retuning": True,
    }
```

`EXPECTED_P5_THRESHOLDS` is a mapping from each of the 13 names to
`{"operator": ">=", "value": 0.80}`-style objects, using `==` for unsafe OOD
and `<=` for redundancy and unsupported derived items. Export it from
`athanasor.benchmark.protocol` so fixtures, validators, and later P6 code share
one immutable contract.

- [ ] **Step 2: Add failing validator tests**

```python
def test_source_manifest_requires_12_papers_at_four_per_lane() -> None:
    payload = source_manifest_fixture()
    payload["sources"].pop()
    errors = validate_sources(payload)
    assert "/sources: expected exactly 12 records" in errors
    assert any("lane balance" in error for error in errors)


@pytest.mark.parametrize("field", ["gold_label", "gold_rationale", "gold_evidence_spans", "adjudication_notes"])
def test_blinded_packet_rejects_gold_fields_at_any_depth(field: str) -> None:
    packet = {"records": [{"metadata": {field: 2}}]}
    assert any(field in error for error in validate_blinded_packet(packet))


def test_metric_contract_requires_denominator_and_undefined_rule() -> None:
    payload = protocol_fixture()
    del payload["metrics"][0]["denominator"]
    assert any("/metrics/0/denominator" in error for error in validate_protocol(payload))


def test_private_source_directory_detects_byte_and_retrieval_drift(tmp_path: Path) -> None:
    payload = source_manifest_fixture()
    write_private_source_fixture(tmp_path, payload)
    first = payload["sources"][0]
    (tmp_path / f"{first['paper_id']}.pdf").write_bytes(b"changed")
    errors = validate_source_directory(payload, tmp_path)
    assert any("sha256 mismatch" in error for error in errors)
```

- [ ] **Step 3: Run tests and confirm missing imports fail**

Run: `uv run pytest tests/test_benchmark_protocol.py -q`

Expected: import errors for the new validator names.

- [ ] **Step 4: Implement deterministic loading and recursive gold-field detection**

```python
REQUIRED_SOURCE_FIELDS = (
    "paper_id", "title", "authors", "lane", "stable_identifier", "exact_version",
    "publication_date", "canonical_url", "download_url", "access_date", "sha256",
    "license", "license_evidence_url", "redistribution_status", "retrieval",
    "source_text_quality",
)
FORBIDDEN_GOLD_FIELDS = frozenset({
    "gold_label", "gold_rationale", "gold_evidence_spans", "adjudication_notes",
    "adjudication_confidence", "relevance_class", "positive_degree",
    "target_thresholds", "benchmark_acceptance",
})


def load_mapping(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8")) if path.suffix == ".json" else yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise BenchmarkProtocolError(f"cannot read {path.name}: {exc}") from None
    if not isinstance(value, dict):
        raise BenchmarkProtocolError(f"{path.name}: expected top-level object")
    return value


def _walk_fields(value: Any, path: str = "/") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path.rstrip('/')}/{key}"
            found.append((child_path, str(key)))
            found.extend(_walk_fields(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_walk_fields(child, f"{path.rstrip('/')}/{index}"))
    return found


def validate_blinded_packet(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["/: expected object"]
    return [f"{path}: forbidden gold field {field}" for path, field in _walk_fields(payload) if field in FORBIDDEN_GOLD_FIELDS]
```

`validate_sources` enforces benchmark ID, exactly 12 records, 4/4/4 lanes, unique IDs, recomputed paper IDs, HTTPS routes, lowercase SHA-256, nonempty rights evidence, `fetch_only`, and no paths. `validate_source_directory` requires private `<paper_id>.pdf` and `<paper_id>.retrieval.json` files, hashes the bytes, and verifies the recorded final URL, redirect chain, access date, exact version, media type, and license-evidence URL against the public record. `validate_protocol` enforces the 0-3 rubric, Rafael authority, 66 pairs, 13 exact metrics, exact thresholds, and complete population/numerator/denominator/averaging/undefined/uncertainty fields. `validate_freeze_manifest(payload, *, source_digest, protocol_digest, prompt_digest)` binds all three public surfaces. It accepts `pending_human_adjudication` only with `private_gold_commitment: null`, and accepts `frozen` only with the complete commitment shape; it never accepts gold content. `validate_public_bundle` loads the required public artifacts plus prompt bytes and returns a combined error list.

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/test_benchmark_protocol.py -q`

Expected: all validator tests pass.

```bash
git add athanasor/benchmark tests/benchmark_fixtures.py tests/test_benchmark_protocol.py
git commit -m "feat: validate frozen benchmark contracts"
```

---

### Task 3: Exact 12-source dossier

**Files:**
- Create: `benchmarks/operations-decision-support-v1/README.md`
- Create: `benchmarks/operations-decision-support-v1/sources.yaml`
- Create: `benchmarks/operations-decision-support-v1/selection-log.yaml`
- Modify: `tests/test_benchmark_protocol.py`

**Interfaces:**
- Consumes: primary source records and bytes under `$AZOTH_P5_PRIVATE_ROOT/sources`.
- Produces: one valid 12-source public manifest whose canonical digest becomes part of the gold identity.

- [ ] **Step 1: Start Vigil and create the external source directory**

Run: `uv run python athanasor/vigil/verify.py start && test -n "$AZOTH_P5_PRIVATE_ROOT" && mkdir -p "$AZOTH_P5_PRIVATE_ROOT/sources" && chmod 700 "$AZOTH_P5_PRIVATE_ROOT" "$AZOTH_P5_PRIVATE_ROOT/sources"`

Expected: Vigil passes seven gates and the private directories are outside the repository.

- [ ] **Step 2: Verify and retrieve the approved slate**

| Lane | Stable source identity | Exact work | Primary starting point |
|---|---|---|---|
| operations | arXiv:1402.5481; DOI 10.1287/mnsc.2018.3253 | Bertsimas and Kallus, “From Predictive to Prescriptive Analytics” | `https://arxiv.org/abs/1402.5481` |
| operations | arXiv:1710.08005; DOI 10.1287/mnsc.2020.3922 | Elmachtoub and Grigas, “Smart Predict, then Optimize” | `https://arxiv.org/abs/1710.08005` |
| operations | arXiv:1809.05504; DOI 10.1609/aaai.v33i01.33011658 | Wilder, Dilkina, and Tambe, “Melding the Data-Decisions Pipeline” | `https://arxiv.org/abs/1809.05504` |
| operations | DOI 10.3386/w23180 | Kleinberg et al., “Human Decisions and Machine Predictions” | `https://www.nber.org/papers/w23180` |
| ML planning | NIPS 2015 proceedings | Sculley et al., “Hidden Technical Debt in Machine Learning Systems” | `https://research.google/pubs/hidden-technical-debt-in-machine-learning-systems/` |
| ML planning | IEEE Big Data 2017 | Breck et al., “The ML Test Score” | `https://research.google/pubs/the-ml-test-score-a-rubric-for-ml-production-readiness-and-technical-debt-reduction/` |
| ML planning | arXiv:1803.09010; DOI 10.1145/3458723 | Gebru et al., “Datasheets for Datasets” | `https://arxiv.org/abs/1803.09010` |
| ML planning | arXiv:1810.03993; DOI 10.1145/3287560.3287596 | Mitchell et al., “Model Cards for Model Reporting” | `https://arxiv.org/abs/1810.03993` |
| human/organizational | DOI 10.1037/xge0000033 | Dietvorst, Simmons, and Massey, “Algorithm Aversion” | `https://repository.upenn.edu/bitstreams/4d24c079-228b-47bd-ba8c-166eeddee8de/download` |
| human/organizational | HBS WP 17-086; DOI 10.1016/j.obhdp.2018.12.005 | Logg, Minson, and Moore, “Algorithm Appreciation” | `https://www.hbs.edu/ris/download.aspx?name=17-086.pdf` |
| human/organizational | DOI 10.1518/hfes.46.1.50_30392 | Lee and See, “Trust in Automation” | `https://user.engineering.uiowa.edu/~csl/publications/pdf/leesee04.pdf` |
| human/organizational | arXiv:2006.14779; DOI 10.1145/3411764.3445717 | Bansal et al., “Does the Whole Exceed its Parts?” | `https://arxiv.org/abs/2006.14779` |

For each source, save exact bytes as `<paper_id>.pdf` and normalized retrieval evidence as `<paper_id>.retrieval.json` under the private source directory. The JSON records requested URL, complete redirect chain, final URL, response media type, access date, exact source version, license evidence URL, and SHA-256. Use `curl --proto '=https' --tlsv1.2 --fail --location` with a descriptive user agent. Commit none of those files.

- [ ] **Step 3: Apply the controlled replacement gate**

Allowed exclusion reasons are `rights_failure`, `no_stable_public_route`, `version_ambiguity`, `duplicate_construct`, `excessive_citation_leakage`, `weak_lane_fit`, `extraction_failure`, and `unstable_source`. A replacement stays in the same lane and must improve causal intervention, learning to defer, feedback/performativity, robust uncertainty, institutional discretion, or organizational data work. Stop for user review if the final title list changes.

- [ ] **Step 4: Write and test the manifest**

Each record contains all required validator fields plus category fit, decision-problem specification, evidence type, citation role, hard-negative role, and selection rationale. Set every `redistribution_status` to `fetch_only`; record exact declared license terms and evidence URLs; include no local path.

```python
BENCHMARK_ROOT = Path(__file__).resolve().parents[1] / "benchmarks" / "operations-decision-support-v1"


def test_live_source_manifest_is_valid_and_balanced() -> None:
    payload = load_mapping(BENCHMARK_ROOT / "sources.yaml")
    assert validate_sources(payload) == []
    assert len(payload["sources"]) == 12
    assert len(canonical_pairs([row["paper_id"] for row in payload["sources"]])) == 66
    assert {row["redistribution_status"] for row in payload["sources"]} == {"fetch_only"}
```

- [ ] **Step 5: Validate and commit**

Run: `uv run pytest tests/test_benchmark_protocol.py -q && uv run python -c 'import os; from pathlib import Path; from athanasor.benchmark.protocol import load_mapping, validate_source_directory; root=Path("benchmarks/operations-decision-support-v1"); errors=validate_source_directory(load_mapping(root/"sources.yaml"), Path(os.environ["AZOTH_P5_PRIVATE_ROOT"])/"sources"); assert not errors, errors' && uv run python scripts/check_public_tree.py && git diff --check`

Expected: all focused checks pass and no source byte or private path is tracked.

```bash
git add benchmarks/operations-decision-support-v1 tests/test_benchmark_protocol.py
git commit -m "docs: freeze benchmark source slate"
```

---

### Task 4: Freeze rubric, metrics, prompt, and blinded schema

**Files:**
- Create: `benchmarks/operations-decision-support-v1/protocol.yaml`
- Create: `benchmarks/operations-decision-support-v1/blinded-packet-schema.yaml`
- Create: `benchmarks/operations-decision-support-v1/generation-prompt.md`
- Create: `benchmarks/operations-decision-support-v1/freeze-manifest.json`
- Modify: `tests/test_benchmark_protocol.py`

**Interfaces:**
- Consumes: the source manifest and approved P5 spec.
- Produces: exact adjudication and generation contracts used unchanged by P6-P7.

- [ ] **Step 1: Add failing live-contract tests**

```python
def test_live_protocol_is_valid_and_keeps_human_authority() -> None:
    payload = load_mapping(BENCHMARK_ROOT / "protocol.yaml")
    assert validate_protocol(payload) == []
    assert payload["adjudication"]["final_authority"] == "Rafael"
    assert payload["rubric"]["relevant_labels"] == [2, 3]


def test_live_blinded_schema_contains_no_gold_fields() -> None:
    payload = load_mapping(BENCHMARK_ROOT / "blinded-packet-schema.yaml")
    assert validate_blinded_packet(payload) == []


def test_metric_thresholds_match_preregistration() -> None:
    payload = load_mapping(BENCHMARK_ROOT / "protocol.yaml")
    assert {row["name"]: row["threshold"] for row in payload["metrics"]} == EXPECTED_P5_THRESHOLDS
```

- [ ] **Step 2: Run tests and confirm missing-file failures**

Run: `uv run pytest tests/test_benchmark_protocol.py -q`

Expected: the live-contract tests fail because their files are absent.

- [ ] **Step 3: Write the exact adjudication contract**

```yaml
rubric:
  scale:
    0: no meaningful structural relationship for this benchmark
    1: topical or lexical overlap without an actionable structural relation
    2: meaningful shared mechanism, method, or decision structure
    3: strong structural relation with a concrete transferable implication
  relevant_labels: [2, 3]
  nonforcing_evidence: [direct_citation, shared_authorship, shared_venue, shared_vocabulary, shared_dataset]
adjudication:
  final_authority: Rafael
  canonical_pair_count: 66
  presentation_seed: 5607
  repeated_anchor_count: 4
  require_anchor_reconciliation: true
  hide_lane_labels: true
  hide_selection_notes: true
```

Add fictional boundary examples distinguishing 1 from 2 and 2 from 3. State that direct citation is evidence of explicit relation but does not force a relevant label.

- [ ] **Step 4: Freeze all 13 metric contracts**

Use exactly: `macro_f1 >= 0.80`, `unsafe_ood_assignment == 0.00`, `claim_precision >= 0.90`, `reference_recall >= 0.70`, `candidate_recall >= 0.90`, `workload_reduction >= 0.50`, `precision_at_5 >= 0.60`, `ndcg_at_10 >= 0.65`, `evidence_support >= 0.90`, `supported_items >= 0.85`, `useful_items >= 0.60`, `redundancy <= 0.15`, and `unsupported_derived_items <= 0.05`.

Each record defines `population`, `numerator`, `denominator`, `averaging`, `undefined_case`, `uncertainty`, `future_artifact`, `comparison`, and `threshold`. Mark metrics not computable from the 66 labels alone. Use Wilson 95% intervals for binomial proportions and paired bootstrap seed `5607` for ranking and workload comparisons.

- [ ] **Step 5: Freeze the generation-visible schema and prompt**

Allow source identity, bibliographic metadata, abstract or extracted record, claims, methods, caveats, tags, explicit citations, pair ID, and paper IDs. Deny exactly `FORBIDDEN_GOLD_FIELDS`. The prompt instructs 5.6 Sol to assess structural relation, cite visible evidence, emit `pending_review`, and avoid claims of truth or novelty. It contains no thresholds, expected positive pairs, selection notes, or gold terminology.

Write `freeze-manifest.json` with exact source, protocol, prompt, and blinded-schema digests, pair count 66, authority Rafael, `status: pending_human_adjudication`, `private_gold_commitment: null`, and `no_retuning: true`. This is an auditable pre-freeze state, not P5 completion.

- [ ] **Step 6: Validate and commit**

Run: `uv run pytest tests/test_benchmark_protocol.py -q && uv run python scripts/check_public_tree.py && git diff --check`

Expected: all checks pass.

```bash
git add benchmarks/operations-decision-support-v1 tests/test_benchmark_protocol.py
git commit -m "docs: freeze benchmark rubric and metrics"
```

---

### Task 5: Private adjudication and freeze mechanics

**Files:**
- Create: `athanasor/benchmark/freeze.py`
- Modify: `athanasor/benchmark/__init__.py`
- Modify: `tests/benchmark_fixtures.py`
- Create: `tests/test_benchmark_freeze.py`

**Interfaces:**
- Consumes: validated sources, protocol, and an explicit output path outside the repo.
- Produces: `ensure_outside_repository(path, repo_root) -> Path`, `build_adjudication_packet`, `reconcile_gold_packet`, `validate_gold_packet`, `gold_commitment`, and `atomic_write_private`.

- [ ] **Step 1: Write failing construction and boundary tests**

```python
def test_packet_has_66_pairs_plus_four_repeats() -> None:
    packet = build_adjudication_packet(source_manifest_fixture(), protocol_fixture())
    assert len(packet["canonical_pairs"]) == 66
    assert len(packet["presentations"]) == 70
    assert len({row["pair_id"] for row in packet["canonical_pairs"]}) == 66


def test_reconcile_refuses_inconsistent_anchors() -> None:
    packet = completed_packet_fixture(inconsistent_anchor=True)
    with pytest.raises(BenchmarkProtocolError, match="anchor ratings disagree"):
        reconcile_gold_packet(packet)


def test_commitment_changes_when_one_label_changes() -> None:
    original = reconciled_packet_fixture()
    changed = deepcopy(original)
    changed["gold_pairs"][0]["label"] = 3
    assert gold_commitment(original) != gold_commitment(changed)


def test_private_write_refuses_repo_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(BenchmarkProtocolError, match="outside the repository"):
        atomic_write_private(repo / "gold.json", {}, repo)
```

Add these shared helpers after `build_adjudication_packet` exists:

```python
def completed_packet_fixture(*, inconsistent_anchor: bool = False) -> dict[str, Any]:
    packet = build_adjudication_packet(source_manifest_fixture(), protocol_fixture())
    seen: dict[str, int] = {}
    for presentation in packet["presentations"]:
        pair = presentation["pair_id"]
        seen[pair] = seen.get(pair, 0) + 1
        presentation["label"] = 2
        presentation["rationale"] = "Synthetic structural relation for contract testing."
        presentation["evidence_spans"] = [
            {"paper_role": "a", "text": "Synthetic evidence A."},
            {"paper_role": "b", "text": "Synthetic evidence B."},
        ]
        if inconsistent_anchor and pair in packet["anchor_pair_ids"] and seen[pair] == 2:
            presentation["label"] = 1
            break
    return packet


def reconciled_packet_fixture() -> dict[str, Any]:
    return reconcile_gold_packet(completed_packet_fixture())
```

- [ ] **Step 2: Run tests and confirm the missing-module failure**

Run: `uv run pytest tests/test_benchmark_freeze.py -q`

Expected: `ModuleNotFoundError` for `athanasor.benchmark.freeze`.

- [ ] **Step 3: Implement deterministic presentation construction**

```python
def build_adjudication_packet(sources: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    errors = validate_sources(sources) + validate_protocol(protocol)
    if errors:
        raise BenchmarkProtocolError("cannot build adjudication packet: " + "; ".join(errors))
    pairs = canonical_pairs([row["paper_id"] for row in sources["sources"]])
    seed = int(protocol["adjudication"]["presentation_seed"])
    repeat_count = int(protocol["adjudication"]["repeated_anchor_count"])
    anchor_ids = sorted(row["pair_id"] for row in pairs)[:repeat_count]
    presentation_ids = [row["pair_id"] for row in pairs] + anchor_ids
    random.Random(seed).shuffle(presentation_ids)
    return {
        "schema_version": 1,
        "artifact_type": "azoth_private_adjudication",
        "benchmark_id": sources["benchmark_id"],
        "source_manifest_sha256": canonical_digest(sources),
        "rubric_version": protocol["rubric_version"],
        "final_authority": "Rafael",
        "canonical_pairs": pairs,
        "anchor_pair_ids": anchor_ids,
        "presentations": [
            {"presentation_id": f"presentation_{index + 1:03d}", "pair_id": value, "label": None, "rationale": "", "evidence_spans": []}
            for index, value in enumerate(presentation_ids)
        ],
        "gold_pairs": [],
        "freeze": None,
    }
```

- [ ] **Step 4: Implement reconciliation and atomic freeze**

Require every presentation to have integer label 0-3, nonempty rationale, and evidence spans covering both papers. Repeated anchors must agree; never average or choose one silently. Produce 66 sorted gold pairs. `gold_commitment` hashes benchmark ID, source digest, rubric version, authority, sorted gold pairs, and UTC freeze time, excluding paths and presentation order. `ensure_outside_repository` resolves both inputs, rejects equality or any `path.is_relative_to(repo_root)` result, and returns the resolved safe path. `atomic_write_private` calls that helper, creates a mode-`0700` parent, writes a mode-`0600` same-directory temporary file, `fsync`s it, and atomically replaces the destination.

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/test_benchmark_freeze.py -q`

Expected: all freeze tests pass.

```bash
git add athanasor/benchmark tests/benchmark_fixtures.py tests/test_benchmark_freeze.py
git commit -m "feat: add private benchmark freeze mechanics"
```

---

### Task 6: Standalone audit and synthetic fixtures

**Files:**
- Create: `scripts/check_benchmark_protocol.py`
- Modify: `tests/benchmark_fixtures.py`
- Create: `tests/test_benchmark_check.py`
- Create: `benchmarks/operations-decision-support-v1/synthetic/sources.yaml`
- Create: `benchmarks/operations-decision-support-v1/synthetic/blinded-packet.json`

**Interfaces:**
- Consumes: `--benchmark-root`, optional paired `--private-gold` and `--source-dir`, and `--repo-root`.
- Produces: exit 0 for valid inputs, 1 for findings, and 2 for unreadable or unsafe inputs.

- [ ] **Step 1: Add subprocess and frozen-bundle helpers**

```python
def run_check(*arguments: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    root = Path(__file__).resolve().parents[1]
    return subprocess.run(
        [sys.executable, str(root / "scripts" / "check_benchmark_protocol.py"), *arguments],
        cwd=cwd or root,
        text=True,
        capture_output=True,
        check=False,
    )


def write_valid_public_bundle(root: Path) -> Path:
    benchmark = root / "benchmarks" / "operations-decision-support-v1"
    benchmark.mkdir(parents=True)
    sources = source_manifest_fixture()
    protocol = protocol_fixture()
    (benchmark / "sources.yaml").write_text(yaml.safe_dump(sources, sort_keys=False), encoding="utf-8")
    (benchmark / "protocol.yaml").write_text(yaml.safe_dump(protocol, sort_keys=False), encoding="utf-8")
    (benchmark / "blinded-packet-schema.yaml").write_text(yaml.safe_dump({"schema_version": 1, "allowed_fields": ["paper_id", "pair_id", "status"]}), encoding="utf-8")
    prompt_bytes = b"Synthetic frozen generation prompt.\n"
    (benchmark / "generation-prompt.md").write_bytes(prompt_bytes)
    (benchmark / "freeze-manifest.json").write_text(json.dumps({
        "schema_version": 1,
        "artifact_type": "azoth_benchmark_freeze",
        "benchmark_id": "operations-decision-support-v1",
        "status": "frozen",
        "source_manifest_sha256": canonical_digest(sources),
        "protocol_sha256": canonical_digest(protocol),
        "prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
        "pair_count": 66,
        "label_authority": "Rafael",
        "private_gold_commitment": {"algorithm": "sha256-canonical-json-v1", "private_gold_sha256": "1" * 64, "schema_version": 1, "freeze_time": "2026-07-11T12:00:00Z"},
        "no_retuning": True,
    }, sort_keys=True), encoding="utf-8")
    return benchmark


def write_frozen_bundle(root: Path) -> tuple[Path, Path, Path, Path]:
    repo = root / "repo"
    benchmark = write_valid_public_bundle(repo)
    private = root / "private"
    private.mkdir()
    source_dir = private / "sources"
    write_private_source_fixture(source_dir, source_manifest_fixture())
    gold = private / "gold.json"
    packet = reconciled_packet_fixture()
    gold.write_bytes(canonical_json_bytes(packet))
    freeze = json.loads((benchmark / "freeze-manifest.json").read_text(encoding="utf-8"))
    freeze["private_gold_commitment"] = gold_commitment(packet)
    (benchmark / "freeze-manifest.json").write_text(json.dumps(freeze, sort_keys=True), encoding="utf-8")
    return benchmark, gold, source_dir, repo
```

Import `json`, `subprocess`, `sys`, `canonical_digest`, `canonical_json_bytes`,
`gold_commitment`, and `reconciled_packet_fixture` explicitly in the helper
module. The test bundle uses synthetic-only identities and never a real label.

- [ ] **Step 2: Write failing CLI tests**

```python
def test_public_audit_passes_without_private_gold(tmp_path: Path) -> None:
    root = write_valid_public_bundle(tmp_path)
    result = run_check("--benchmark-root", str(root), "--repo-root", str(tmp_path))
    assert result.returncode == 0
    assert "PASS mode=public" in result.stdout


def test_private_audit_rejects_commitment_mismatch(tmp_path: Path) -> None:
    root, gold, source_dir, repo = write_frozen_bundle(tmp_path)
    payload = json.loads(gold.read_text())
    payload["gold_pairs"][0]["label"] = 3
    gold.write_text(json.dumps(payload), encoding="utf-8")
    result = run_check("--benchmark-root", str(root), "--private-gold", str(gold), "--source-dir", str(source_dir), "--repo-root", str(repo))
    assert result.returncode == 1
    assert "digest does not match" in result.stdout
```

- [ ] **Step 3: Run tests and confirm the script is missing**

Run: `uv run pytest tests/test_benchmark_check.py -q`

Expected: subprocess tests fail because the script is absent.

- [ ] **Step 4: Implement the standalone audit**

```python
def main() -> int:
    args = build_parser().parse_args()
    try:
        errors = validate_public_bundle(args.benchmark_root)
        mode = "public"
        if args.private_gold is not None:
            ensure_outside_repository(args.private_gold, args.repo_root)
            if args.source_dir is None:
                raise BenchmarkProtocolError("--source-dir is required with --private-gold")
            ensure_outside_repository(args.source_dir, args.repo_root)
            sources = load_mapping(args.benchmark_root / "sources.yaml")
            protocol = load_mapping(args.benchmark_root / "protocol.yaml")
            gold = load_mapping(args.private_gold)
            errors.extend(validate_source_directory(sources, args.source_dir))
            errors.extend(validate_gold_packet(gold, sources, protocol))
            public = load_mapping(args.benchmark_root / "freeze-manifest.json")
            if gold_commitment(gold) != public["private_gold_commitment"]:
                errors.append("/private_gold_commitment: private gold digest does not match public commitment")
            mode = "public+private"
    except BenchmarkProtocolError as exc:
        print(f"Benchmark protocol audit: ERROR: {exc}")
        return 2
    if errors:
        print(f"Benchmark protocol audit: FAIL mode={mode}")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Benchmark protocol audit: PASS mode={mode}")
    return 0
```

- [ ] **Step 5: Add fictional fixtures, verify, and commit**

Create exactly six newly authored fictional sources, two per lane. Their titles, identifiers, hashes, claims, and evidence explicitly say `synthetic` and transform no real paper. The blinded packet contains only generation-visible fields and `status: pending_review`.

Run: `uv run pytest tests/test_benchmark_check.py tests/test_benchmark_protocol.py tests/test_benchmark_freeze.py -q && uv run python scripts/check_benchmark_protocol.py --benchmark-root benchmarks/operations-decision-support-v1 --repo-root .`

Expected: tests pass and the audit prints `PASS mode=public`.

```bash
git add scripts/check_benchmark_protocol.py tests/benchmark_fixtures.py tests/test_benchmark_check.py benchmarks/operations-decision-support-v1/synthetic
git commit -m "feat: audit benchmark freeze protocol"
```

---

### Task 7: Human adjudication and public freeze commitment

**Files:**
- Create outside Git: `$AZOTH_P5_PRIVATE_ROOT/gold/operations-decision-support-v1.json`
- Modify: `benchmarks/operations-decision-support-v1/freeze-manifest.json`
- Modify: `benchmarks/operations-decision-support-v1/README.md`
- Modify: `tests/test_benchmark_protocol.py`

**Interfaces:**
- Consumes: sources, protocol, and Rafael's 70 blinded presentation ratings.
- Produces: reconciled private 66-pair gold plus a matching public digest commitment.

- [ ] **Step 1: Generate the private packet outside Git**

Run:

```bash
test -n "$AZOTH_P5_PRIVATE_ROOT"
uv run python - <<'PY'
import os
from pathlib import Path
from athanasor.benchmark.freeze import atomic_write_private, build_adjudication_packet
from athanasor.benchmark.protocol import load_mapping

repo = Path.cwd().resolve()
root = repo / "benchmarks" / "operations-decision-support-v1"
private = Path(os.environ["AZOTH_P5_PRIVATE_ROOT"]).expanduser().resolve()
packet = build_adjudication_packet(load_mapping(root / "sources.yaml"), load_mapping(root / "protocol.yaml"))
target = private / "gold" / "operations-decision-support-v1.json"
atomic_write_private(target, packet, repo)
print(target)
PY
```

Expected: one mode-`0600` packet outside the repo with 66 canonical pairs, 70 presentations, four repeats, and no ratings.

- [ ] **Step 2: Stop for Rafael's blinded adjudication**

Present one randomized entry at a time without lane, selection, graph, or anchor metadata. Rafael supplies every 0-3 label, rationale, and evidence span. Do not infer or autofill labels. P5 remains in progress until all 70 presentations are complete.

- [ ] **Step 3: Reconcile anchors with explicit human resolution**

Run `reconcile_gold_packet`. If two anchor ratings differ, show Rafael both ratings and the rubric boundary and require one explicit final label and rationale. Never average or silently select. Re-run until exactly 66 reconciled gold pairs validate.

- [ ] **Step 4: Freeze privately and write the public commitment**

Atomically replace the completed private packet. Write `freeze-manifest.json` with schema version 1, artifact type `azoth_benchmark_freeze`, benchmark ID, `status: frozen`, canonical source, protocol, and blinded-schema digests, prompt byte digest, pair count 66, label authority Rafael, gold algorithm `sha256-canonical-json-v1`, private gold digest, private schema version, UTC freeze time, and `no_retuning: true`. Compute every digest from the final bytes or canonical payload; the committed JSON contains no instructional prose, path, label, or evidence.

- [ ] **Step 5: Add the live freeze regression**

```python
def test_live_freeze_matches_public_digests() -> None:
    sources = load_mapping(BENCHMARK_ROOT / "sources.yaml")
    protocol = load_mapping(BENCHMARK_ROOT / "protocol.yaml")
    freeze = load_mapping(BENCHMARK_ROOT / "freeze-manifest.json")
    assert validate_freeze_manifest(
        freeze,
        source_digest=canonical_digest(sources),
        protocol_digest=canonical_digest(protocol),
        prompt_digest=hashlib.sha256((BENCHMARK_ROOT / "generation-prompt.md").read_bytes()).hexdigest(),
    ) == []
    assert freeze["pair_count"] == 66
    assert freeze["label_authority"] == "Rafael"
```

- [ ] **Step 6: Run the public-plus-private audit and commit only public files**

Run: `uv run python scripts/check_benchmark_protocol.py --benchmark-root benchmarks/operations-decision-support-v1 --private-gold "$AZOTH_P5_PRIVATE_ROOT/gold/operations-decision-support-v1.json" --source-dir "$AZOTH_P5_PRIVATE_ROOT/sources" --repo-root .`

Expected: `Benchmark protocol audit: PASS mode=public+private`.

Run: `git add benchmarks/operations-decision-support-v1/freeze-manifest.json benchmarks/operations-decision-support-v1/README.md tests/test_benchmark_protocol.py && git diff --cached --check && git diff --cached | rg -n "gold_label|gold_rationale|evidence_spans|AZOTH_P5_PRIVATE_ROOT|/Users/|\.pdf"`

Expected: diff check passes. Inspect every scan match; abort on any real label, private path, source filename, or evidence. Generic contract wording alone is allowed.

```bash
git commit -m "docs: freeze P5 benchmark commitment"
```

---

### Task 8: Public-tree and hosted-CI enforcement

**Files:**
- Modify: `scripts/check_public_tree.py`
- Modify: `tests/test_public_tree.py`
- Modify: `.github/workflows/hardening.yml`

**Interfaces:**
- Consumes: tracked public paths and bytes.
- Produces: hard failures for source archives, real gold material, or private benchmark paths; public protocol audit on Python 3.10-3.12.

- [ ] **Step 1: Write failing public-tree tests**

```python
def test_audit_rejects_real_gold_and_source_archives() -> None:
    blobs = {
        "benchmarks/operations-decision-support-v1/gold.json": b'{"gold_pairs":[{"label":3}]}',
        "benchmarks/operations-decision-support-v1/source.txt": b"third-party paper body",
        "benchmarks/operations-decision-support-v1/source.zip": b"PK\x03\x04",
    }
    findings = audit_paths(sorted(blobs), blobs.__getitem__)
    assert any("benchmark gold material" in item for item in findings)
    assert any("benchmark source text" in item for item in findings)
    assert any("benchmark source archive" in item for item in findings)


def test_audit_allows_synthetic_fixture_and_freeze_digest() -> None:
    blobs = {
        "benchmarks/operations-decision-support-v1/synthetic/blinded-packet.json": b'{"status":"pending_review"}',
        "benchmarks/operations-decision-support-v1/freeze-manifest.json": b'{"private_gold_sha256":"' + b"0" * 64 + b'"}',
    }
    assert audit_paths(sorted(blobs), blobs.__getitem__) == []
```

- [ ] **Step 2: Run tests and confirm the new rejection test fails**

Run: `uv run pytest tests/test_public_tree.py -q`

Expected: the P5-specific finding assertions fail.

- [ ] **Step 3: Implement narrow benchmark rules**

Reject `.pdf`, `.zip`, `.tar`, `.gz`, `.docx`, full-text `.txt`, and files named `gold.*` below a real benchmark directory. Reject JSON/YAML keys `gold_pairs`, `gold_label`, `gold_rationale`, and `gold_evidence_spans` outside `/synthetic/`. Allow freeze digest field names and generic protocol documentation. Exempt only literal-bearing test/plan files, never the benchmark directory.

- [ ] **Step 4: Add public-only P5 audit to CI**

```yaml
      - name: Verify frozen benchmark protocol
        run: |
          python3 scripts/check_benchmark_protocol.py --benchmark-root benchmarks/operations-decision-support-v1 --repo-root .
```

CI never receives private gold.

- [ ] **Step 5: Verify and commit**

Run: `uv run pytest tests/test_public_tree.py tests/test_benchmark_check.py -q && uv run pytest -q && uv run python scripts/check_public_tree.py && uv run python scripts/check_benchmark_protocol.py --benchmark-root benchmarks/operations-decision-support-v1 --repo-root .`

Expected: all tests and both audits pass.

```bash
git add scripts/check_public_tree.py tests/test_public_tree.py .github/workflows/hardening.yml
git commit -m "ci: enforce frozen benchmark boundaries"
```

---

### Task 9: Documentation, roadmap evidence, and P5 closeout

**Files:**
- Modify: `README.md`
- Modify: `PROJECT_ROADMAP.md`

**Interfaces:**
- Consumes: exact source proof, completed 66-label packet, audits, full tests, and Vigil.
- Produces: honest P5 completion record and exactly one next task, P6-T1.

- [ ] **Step 1: Document the benchmark without results claims**

State that P5 freezes 12 papers and 66 pairs at 4/4/4 balance; sources are fetch-only; Rafael is final label authority; gold stays private until locked P7 outputs and is committed by digest; synthetic fixtures prove contracts only; no performance result exists; P6 builds tooling and P7 runs it.

- [ ] **Step 2: Run the full P5 verification bundle**

Run:

```bash
uv run python -m compileall athanasor scripts
uv run pytest -q
uv run python scripts/check_benchmark_protocol.py --benchmark-root benchmarks/operations-decision-support-v1 --private-gold "$AZOTH_P5_PRIVATE_ROOT/gold/operations-decision-support-v1.json" --source-dir "$AZOTH_P5_PRIVATE_ROOT/sources" --repo-root .
uv run python scripts/check_public_tree.py
uv run python scripts/hardening_audit.py --project-root .
uv run python athanasor/vigil/verify.py verify
git diff --check
git status --short
```

Then run every maintained `scripts/check_*.py` script except `check_benchmark_protocol.py`, which the explicit private command already covered. Remove ignored build/runtime products before the final status check.

Expected: compile succeeds; full tests and maintained checks pass; benchmark audit passes `mode=public+private`; public-tree, hardening, and all seven Vigil gates pass.

- [ ] **Step 3: Update the canonical roadmap from direct evidence**

Mark P5 complete only when all 12 sources have exact versions, rights evidence, and hashes; the private packet has 66 reconciled labels; its digest matches the public commitment; metrics and prompt are frozen; and every check passes. Record counts, public digests, label authority, commands, branch, and implementation SHA, but no private path or label. Set exactly one next task: `P6-T1 — Benchmark CLI, scorer, report, and synthetic fixtures`.

- [ ] **Step 4: Commit and close**

Run: `git add README.md PROJECT_ROADMAP.md && git diff --cached --check && git commit -m "docs: close P5 benchmark freeze" && uv run python athanasor/vigil/verify.py close && git status --short --branch`

Expected: close passes seven gates and the worktree is clean. If Vigil close mutates a tracked file, inspect and commit only that explicit file as `chore: record P5 close state`.

- [ ] **Step 5: Perform the completion audit**

Check every P5 spec acceptance item against current artifacts and command output. P5 remains in progress if source rights are indirect, a hash is unverified, a label is inferred, an anchor is unresolved, digests differ, gold or source bytes are tracked, a metric contract is incomplete, a check is red, or the roadmap names more than one next task. Do not begin P6 until every item has direct evidence.
