"""Exhaust skill: generate structured candidate items from Albedo records."""

from __future__ import annotations

import argparse
import subprocess
from collections import Counter, deque
from pathlib import Path
from typing import Any

import yaml

from ..config import Config, load_config
from ..embeddings import EmbeddingStore
from ..llm import LLMClient, LLMUnavailableError
from ..registry import Registry
from ..schemas import validate as validate_schema
from ..skills.common import ensure_dir, now_iso, write_yaml


EXHAUST_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "EXHAUST_SCHEMA.yaml"


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Exhaust ingested papers.")
    parser.add_argument("paper_id", nargs="?", help="Single paper id.")
    parser.add_argument("--domain", dest="domain", default=None, help="Exhaust a domain bucket.")
    parser.add_argument("--all", action="store_true", help="Exhaust all eligible papers.")
    parser.add_argument("--depth", type=int, default=3, choices=[1, 2, 3, 4, 5])
    parser.add_argument("--count", type=int, default=0, help="Limit count for --all or --domain")
    parser.add_argument("--reprocess", action="store_true", help="Allow re-processing already exhausted papers")
    return parser


def _run_vigil(root: Path, phase: str) -> tuple[int, str]:
    result = subprocess.run(
        ["python3", str(root / "athanasor" / "vigil" / "verify.py"), phase],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    return result.returncode, (result.stdout + result.stderr)


def run_exhaust(
    target: str | None = None,
    *,
    config: Config | None = None,
    llm: LLMClient | None = None,
    depth: int = 3,
    domain: str | None = None,
    all_scope: bool = False,
    count: int = 0,
    reprocess: bool = False,
) -> list[dict[str, Any]]:
    config = config or load_config()
    root = Path(config.project_root).expanduser().resolve()
    paths = config.resolved_paths
    registry = Registry(root / "albedo" / "registry.jsonl")
    store = EmbeddingStore(
        root / config.embeddings["store_path"],
        model_name=config.embeddings.get("model", "all-MiniLM-L6-v2"),
    )
    schema = _load_schema()

    entries = _select_entries(
        registry=registry,
        target=target,
        domain=domain,
        all_scope=all_scope,
        depth=depth,
        reprocess=reprocess,
    )
    if not entries:
        return []

    if count > 0:
        entries = entries[:count]

    _run_vigil(root, "start")
    exhausted: list[dict[str, Any]] = []

    for entry in entries:
        paper_id = str(entry.get("paper_id") or "")
        if not paper_id:
            continue

        result = _process_one(
            paper_id=paper_id,
            registry_entry=entry,
            library_root=paths["albedo"] / "library",
            exhaust_root=paths["albedo"] / "exhaust",
            depth=depth,
            llm=llm,
            schema=schema,
            store=store,
            config=config,
            registry=registry,
        )
        if result is not None:
            exhausted.append(result)

    store.save()
    _run_vigil(root, "verify")
    return exhausted


def _select_entries(
    *,
    registry: Registry,
    target: str | None,
    domain: str | None,
    all_scope: bool,
    depth: int,
    reprocess: bool,
) -> list[dict[str, Any]]:
    if target:
        entry = registry.get(target)
        if not isinstance(entry, dict):
            return []
        prev_depth = int(entry.get("exhausted_at_depth") or 0)
        if entry.get("status") == "exhausted" and prev_depth >= depth and not reprocess:
            return []
        return [entry]

    if all_scope:
        candidates = [
            entry
            for entry in registry.list()
            if entry.get("status") in {"pending", "ingested_only", "exhausted"}
        ]
    elif domain:
        candidates = [
            entry
            for entry in registry.list_by_domain(domain)
            if entry.get("status") in {"pending", "ingested_only", "exhausted"}
        ]
    else:
        return []

    if reprocess:
        return candidates

    selected: list[dict[str, Any]] = []
    for entry in candidates:
        current_depth = int(entry.get("exhausted_at_depth") or 0)
        if entry.get("status") == "exhausted" and current_depth >= depth:
            continue
        selected.append(entry)
    return selected


def _compute_max_items(entry: dict[str, Any], depth: int, config: Config) -> int:
    page_count = 0
    source = entry.get("source")
    if isinstance(source, dict):
        page_count = int(source.get("page_count") or 0)
    if page_count <= 0:
        # Conservative defaults when source metadata is incomplete.
        page_count = 12

    multipliers = config.exhaustion.get("depth_multipliers", {})
    multiplier = int(multipliers.get(str(depth), multipliers.get(depth, 6)))
    if multiplier <= 0:
        multiplier = 6
    return max(1, page_count * multiplier)


def _process_one(
    *,
    paper_id: str,
    registry_entry: dict[str, Any],
    library_root: Path,
    exhaust_root: Path,
    depth: int,
    llm: LLMClient | None,
    schema: dict[str, Any],
    store: EmbeddingStore,
    config: Config,
    registry: Registry,
) -> dict[str, Any] | None:
    library_path = library_root / f"{paper_id}.yaml"
    if not library_path.exists():
        return None

    with open(library_path, "r", encoding="utf-8") as f:
        record = yaml.safe_load(f) or {}
    if not isinstance(record, dict):
        return None

    claims = record.get("claims", [])
    methods = record.get("methods", [])
    techniques = record.get("techniques", [])
    tags = record.get("tags", [])
    title = str((record.get("source") or {}).get("title") or paper_id)
    domain = str(registry_entry.get("domain") or "unclassified")

    strategy = _domain_strategy(domain)
    all_items = {
        "derivations": [],
        "exercises": [],
        "missing_angles": [],
        "open_questions": [],
        "unstated_assumptions": [],
        "experiments": [],
        "necessary_connections": [],
    }

    max_items = _compute_max_items(registry_entry, depth, config)
    batch_size = int(config.exhaustion.get("batch_size", 3))
    redundancy_threshold = float(config.exhaustion.get("redundancy_threshold", 0.85))
    speculative_stop_count = int(config.exhaustion.get("speculative_stop_count", 5))
    redundancy_stop_threshold = int(config.exhaustion.get("redundancy_stop_threshold", 3))

    strategy_notes = _strategy_text(depth=depth, domain=domain)
    claim_count = max(1, len(claims))
    method_count = max(1, len(methods))
    technique_count = max(1, len(techniques))

    buckets_terms = {
        "derivations": "statements, corollaries, or formal consequences",
        "exercises": "implied exercises and sanity checks",
        "missing_angles": "unstudied or neglected perspectives",
        "open_questions": "explicit follow-up questions",
        "unstated_assumptions": "hidden assumptions and boundary conditions",
        "experiments": "empirical tests and falsification designs",
        "necessary_connections": "cross-field work that this paper should connect to",
    }

    recent_redundant = deque(maxlen=5)
    recent_speculative = deque(maxlen=5)
    terminal_reason = "completed"
    iteration_guard = 0

    while _non_redundant_count(all_items) < max_items and iteration_guard < 100:
        iteration_guard += 1

        context = _build_context(
            title=title,
            claims=claims,
            methods=methods,
            techniques=techniques,
            tags=tags,
            strategy=f"{strategy} {strategy_notes}",
            depth=depth,
            buckets_terms=buckets_terms,
            budget=max(3, max_items // max(batch_size, 1)),
            prior_count=_non_redundant_count(all_items),
            domain=domain,
            claim_count=claim_count,
            method_count=method_count,
            technique_count=technique_count,
        )
        generated = _generate_batch(context, llm, batch_size)
        if not generated:
            terminal_reason = "completed"
            break

        added_this_batch = False
        for bucket, raw_items in generated.items():
            if bucket not in all_items:
                continue
            if not isinstance(raw_items, list):
                continue

            for raw in raw_items:
                if not isinstance(raw, dict):
                    continue

                payload = _normalize_item(bucket, raw)
                text = _item_text(bucket, payload)
                if not text:
                    continue

                redundant = _redundancy_score(text, store, paper_id) >= redundancy_threshold
                payload["redundant"] = bool(redundant)
                payload["source_claim"] = _coerce_source_claim(payload.get("source_claim"))
                all_items[bucket].append(payload)
                added_this_batch = True

                if bucket == "derivations":
                    payload.setdefault("follows_from", "claim_1")
                if bucket == "open_questions":
                    payload.setdefault("closable", False)
                if bucket == "exercises":
                    payload.setdefault("solution", "To be validated in future work.")

                if not redundant:
                    store.add(f"{paper_id}_exhaust_{_item_key(bucket, payload)}", text)

                recent_redundant.append(int(redundant))
                conf = str(payload.get("confidence", "")).strip().lower()
                recent_speculative.append(1 if conf == "speculative" else 0)

            if not added_this_batch:
                terminal_reason = "completed"
                break

        if _non_redundant_count(all_items) >= max_items:
            terminal_reason = "hard_cap"
            break

        if sum(recent_redundant) >= redundancy_stop_threshold and len(recent_redundant) >= 5:
            terminal_reason = "redundancy"
            break

        if len(recent_speculative) >= speculative_stop_count and sum(recent_speculative) == speculative_stop_count:
            terminal_reason = "speculative_ceiling"
            break

    non_redundant_total = _non_redundant_count(all_items)
    deeper_available = _can_go_deeper(registry_entry, depth)

    payload = {
        "schema_version": 2,
        "exhaustion": {
            "paper_id": paper_id,
            "paper_title": title,
            "domain": domain,
            "paper_type": _infer_paper_type(tags, methods, techniques),
            "exhaustion_depth": depth,
            "schema_version": 2,
            "agent": "azoth-exhaust",
            "date": now_iso(),
            "termination": {
                "criterion": terminal_reason,
                "detail": (
                    f"non_redundant={non_redundant_total} / max={max_items}; "
                    f"redundant_window={list(recent_redundant)}; "
                    f"speculative_window={list(recent_speculative)}"
                ),
                "deeper_available": deeper_available,
            },
        },
    }

    payload.update(all_items)

    ok, errors, fixed, _ = validate_schema(payload, schema, path="/", fix=True)
    if not ok:
        fixed["_schema_errors"] = errors
    payload = fixed

    out_path = exhaust_root / f"{paper_id}_exhaust.yaml"
    write_yaml(out_path, payload)

    registry.update(
        paper_id,
        {
            "status": "exhausted",
            "exhausted_at_depth": max(int(registry_entry.get("exhausted_at_depth") or 0), depth),
            "paths": {
                **(registry_entry.get("paths") or {}),
                "exhaust": str(out_path.relative_to(Path(config.project_root))),
            },
        },
    )

    return payload


def _strategy_text(*, depth: int, domain: str) -> str:
    if depth >= 4:
        base = "include cross-domain speculative links and transfer opportunities"
    else:
        base = "prioritize directly supported, high-evidence inferences"
    return f"Depth {depth} mode, with emphasis on {base}."


def _infer_paper_type(tags: list[Any], methods: list[dict[str, Any]], techniques: list[dict[str, Any]]) -> str:
    text = " ".join([str(tag) for tag in tags or []]).lower()
    if "review" in text:
        return "review"
    if "textbook" in text:
        return "textbook"
    if "monograph" in text:
        return "monograph"
    if "essay" in text or "philosophy" in text:
        return "essay"
    if "lecture" in text or any("lecture" in str(method.get("name", "")).lower() for method in methods):
        return "lecture_notes"
    if methods or techniques:
        return "paper"
    return "commentary"


def _can_go_deeper(registry_entry: dict[str, Any], current_depth: int) -> bool:
    if current_depth >= 5:
        return False
    exhausted_depth = int(registry_entry.get("exhausted_at_depth") or 0)
    return exhausted_depth <= current_depth


def _non_redundant_count(items: dict[str, list[dict[str, Any]]]) -> int:
    return sum(1 for bucket in items.values() for item in bucket if not item.get("redundant"))


def _coerce_source_claim(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "claim_1"


def _coerce_confidence(value: Any, allowed: list[str], fallback: str = "likely") -> str:
    v = str(value or "").strip().lower()
    if v in allowed:
        return v
    return fallback


def _normalize_item(bucket: str, payload: dict[str, Any]) -> dict[str, Any]:
    if bucket == "derivations":
        return {
            "statement": str(payload.get("statement", "")).strip(),
            "follows_from": str(payload.get("follows_from", "claim_1")).strip(),
            "confidence": _coerce_confidence(payload.get("confidence"), ["derived", "likely", "speculative"]),
            "item_type": payload.get("item_type"),
            "source_claim": payload.get("source_claim"),
            **({"source_claim": payload.get("source_claim")} if "source_claim" in payload else {}),
        }
    if bucket == "exercises":
        return {
            "problem": str(payload.get("problem", "")).strip(),
            "solution": str(payload.get("solution", payload.get("approach", "") or "To be validated.")),
            "difficulty": payload.get("difficulty") or None,
            "source_claim": _coerce_source_claim(payload.get("source_claim")),
        }
    if bucket == "missing_angles":
        return {
            "angle": str(payload.get("angle", "")).strip(),
            "why_missed": payload.get("why_missed"),
            "where_it_lands": str(payload.get("where_it_lands", "")).strip() or "Pending domain-specific synthesis.",
            "item_type": payload.get("item_type"),
            "source_claim": _coerce_source_claim(payload.get("source_claim")),
        }
    if bucket == "open_questions":
        return {
            "question": str(payload.get("question", "")).strip(),
            "closable": bool(payload.get("closable", False)),
            "how_to_close": payload.get("how_to_close"),
            "source_claim": _coerce_source_claim(payload.get("source_claim")),
        }
    if bucket == "unstated_assumptions":
        return {
            "assumption": str(payload.get("assumption", "")).strip(),
            "impacts_claim": payload.get("impacts_claim"),
            "source_claim": _coerce_source_claim(payload.get("source_claim")),
        }
    if bucket == "experiments":
        return {
            "hypothesis": str(payload.get("hypothesis", "")).strip(),
            "design": str(payload.get("design", "")).strip() or "Design not specified.",
            "predicted_true": str(payload.get("predicted_true", "")).strip() or "Pending.",
            "predicted_false": str(payload.get("predicted_false", "")).strip() or "Pending.",
            "source_claim": _coerce_source_claim(payload.get("source_claim")),
        }
    if bucket == "necessary_connections":
        return {
            "work": str(payload.get("work", "")).strip(),
            "why_necessary": str(payload.get("why_necessary", "")).strip() or "Needs explicit rationale.",
            "impact": str(payload.get("impact", "")).strip() or "Potentially significant integration.",
            "source_claim": _coerce_source_claim(payload.get("source_claim")),
        }
    return {}


def _build_context(
    *,
    title: str,
    claims: list[dict[str, Any]],
    methods: list[dict[str, Any]],
    techniques: list[dict[str, Any]],
    tags: list[Any],
    strategy: str,
    depth: int,
    buckets_terms: dict[str, str],
    budget: int,
    prior_count: int,
    domain: str,
    claim_count: int,
    method_count: int,
    technique_count: int,
) -> str:
    claim_lines = [str(item.get("statement", "")) for item in claims[:8] if str(item.get("statement", "")).strip()]
    method_lines = [f"{item.get('name', '')}: {item.get('description', '')}" for item in methods[:6] if str(item.get("name", "")).strip()]
    technique_lines = [f"{item.get('name', '')}: {item.get('description', '')}" for item in techniques[:6] if str(item.get("name", "")).strip()]
    tags_text = ", ".join(str(t) for t in (tags or [])[:12])

    bucket_lines = "\n".join(
        f"- {name}: {desc}" for name, desc in buckets_terms.items()
    )

    return (
        "Produce bounded exhaustion items for this paper.\n\n"
        f"Title: {title}\n"
        f"Domain: {domain}\n"
        f"Depth: {depth}\n"
        f"Budget: {budget} new non-redundant items max in this pass\n"
        f"Generated so far: {prior_count}\n"
        f"Counts: claims={claim_count}, methods={method_count}, techniques={technique_count}\n"
        f"Tags: {tags_text}\n\n"
        f"Strategy: {strategy}\n\n"
        f"Claims:\n- {'\n- '.join(claim_lines) if claim_lines else 'none'}\n\n"
        f"Methods:\n- {'\n- '.join(method_lines) if method_lines else 'none'}\n\n"
        f"Techniques:\n- {'\n- '.join(technique_lines) if technique_lines else 'none'}\n\n"
        "Target buckets: derivations, exercises, missing_angles, open_questions, unstated_assumptions, experiments, necessary_connections.\n"
        f"Bucket focus:\n{bucket_lines}\n\n"
        "Respond as JSON with exactly these top-level keys: derivations, exercises, missing_angles, open_questions, unstated_assumptions, experiments, necessary_connections. "
        "Confidence fields must be one of derived|likely|speculative. Return only items that are directly grounded where possible."
    )


def _generate_batch(context: str, llm: LLMClient | None, batch_size: int) -> dict[str, list[dict[str, Any]]]:
    if llm is None:
        return {}

    prompt = (
        f"{context}\n\n"
        f"Generate up to {batch_size} new items across buckets."
    )
    result = llm.complete(
        prompt,
        structured=True,
        schema={"type": "object"},
        temperature=0.35,
        max_tokens=4096,
    )
    if not isinstance(result, dict):
        return {}
    bucketized = {k: result.get(k, []) for k in [
        "derivations",
        "exercises",
        "missing_angles",
        "open_questions",
        "unstated_assumptions",
        "experiments",
        "necessary_connections",
    ]}
    return {k: [item for item in v if isinstance(item, dict)] for k, v in bucketized.items()}


def _item_text(bucket: str, item: dict[str, Any]) -> str:
    if bucket == "derivations":
        return str(item.get("statement", "")).strip()
    if bucket == "exercises":
        return str(item.get("problem", "")).strip()
    if bucket == "missing_angles":
        return str(item.get("angle", "")).strip()
    if bucket == "open_questions":
        return str(item.get("question", "")).strip()
    if bucket == "unstated_assumptions":
        return str(item.get("assumption", "")).strip()
    if bucket == "experiments":
        return str(item.get("hypothesis", "")).strip()
    if bucket == "necessary_connections":
        return str(item.get("work", "")).strip()
    return ""


def _item_key(bucket: str, item: dict[str, Any]) -> str:
    base = _item_text(bucket, item)
    if not base:
        return f"{bucket}_{len(item)}"
    return str(abs(hash(base)) % (10**8))


def _redundancy_score(text: str, store: EmbeddingStore, paper_id: str) -> float:
    if not text.strip() or store.size == 0:
        return 0.0
    results = store.search(text, top_k=25)
    for candidate_id, score in results:
        if str(candidate_id).startswith(f"{paper_id}_exhaust_"):
            return float(score)
    return 0.0


def _domain_strategy(domain: str) -> str:
    if domain in {"physics", "mathematics"}:
        return "prioritize theorem-like implications, boundary conditions, and formal consequences"
    if domain == "ML":
        return "prioritize architectural tradeoffs, ablations, reproducibility edges, and failure modes"
    if domain == "philosophy":
        return "prioritize argument structure, counterfactual implications, and unstated premises"
    if domain == "neuroscience":
        return "prioritize computational predictions, causal claims, and falsifiable experimental hypotheses"
    return "prioritize domain-anchored and evidence-respectful inferences"


def _load_schema() -> dict[str, Any]:
    with open(EXHAUST_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
