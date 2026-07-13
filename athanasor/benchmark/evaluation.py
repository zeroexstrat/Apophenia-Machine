from __future__ import annotations

from pathlib import Path
from typing import Any

from athanasor.benchmark.artifacts import (
    BenchmarkArtifactError,
    artifact_digest,
    validate_run,
    validate_score,
)
from athanasor.benchmark.execution import (
    execution_manifest_digest,
    validate_execution_manifest,
)
from athanasor.benchmark.locking import verify_lock_manifest
from athanasor.benchmark.protocol import BENCHMARK_ID, EXPECTED_P5_METRIC_CONTRACTS


ANNOTATION_TYPE = "azoth_benchmark_human_annotations"
_ANNOTATION_FIELDS = {
    "schema_version",
    "artifact_type",
    "benchmark_id",
    "run_sha256",
    "lock_manifest_sha256",
    "execution_manifest_sha256",
    "authority",
    "ood_assignments",
    "claims",
    "evidence_spans",
    "items",
    "status",
}


def _model_items(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for result in run.get("results", [])
        if isinstance(result, dict)
        for item in result.get("items", [])
        if isinstance(item, dict)
    ]


def _lock_run_record(run: dict[str, Any], lock: dict[str, Any]) -> dict[str, Any] | None:
    run_digest = artifact_digest(run)
    records = lock.get("runs") if isinstance(lock, dict) else None
    if not isinstance(records, list):
        return None
    matches = [
        record
        for record in records
        if isinstance(record, dict) and record.get("artifact_sha256") == run_digest
    ]
    return matches[0] if len(matches) == 1 else None


def build_annotation_template(
    run: dict[str, Any], lock: dict[str, Any]
) -> dict[str, Any]:
    run_errors = validate_run(run)
    if run_errors:
        raise BenchmarkArtifactError("invalid run artifact: " + "; ".join(run_errors))
    record = _lock_run_record(run, lock)
    if record is None or record.get("run_id") != "model_5_6_sol":
        raise BenchmarkArtifactError("annotation template requires the locked model run")
    backend = run.get("backend")
    if not isinstance(backend, dict) or backend.get("run_id") != "model_5_6_sol":
        raise BenchmarkArtifactError("annotation template requires model backend identity")
    if backend.get("execution_manifest_sha256") != lock.get("execution_manifest_sha256"):
        raise BenchmarkArtifactError("annotation template execution manifest mismatch")
    items = _model_items(run)
    claims = []
    spans = []
    item_rows = []
    for item in sorted(items, key=lambda row: str(row.get("item_id"))):
        item_id = item.get("item_id")
        claim_id = item.get("claim_id")
        if not isinstance(item_id, str) or not item_id:
            raise BenchmarkArtifactError("model item requires item_id")
        if not isinstance(claim_id, str) or not claim_id:
            raise BenchmarkArtifactError(f"model item {item_id} requires claim_id")
        claims.append({"claim_id": claim_id, "supported": None, "rationale": ""})
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise BenchmarkArtifactError(f"model item {item_id} requires evidence spans")
        for span in evidence:
            span_id = span.get("span_id") if isinstance(span, dict) else None
            if not isinstance(span_id, str) or not span_id:
                raise BenchmarkArtifactError(f"model item {item_id} has invalid span_id")
            spans.append({"span_id": span_id, "supported": None, "rationale": ""})
        confidence = item.get("confidence")
        if confidence not in {"derived", "likely", "speculative"}:
            raise BenchmarkArtifactError(f"model item {item_id} has invalid confidence")
        item_rows.append(
            {
                "item_id": item_id,
                "supported": None,
                "useful": None,
                "redundant": None,
                "confidence": confidence,
                "rationale": "",
            }
        )
    payload = {
        "schema_version": 1,
        "artifact_type": ANNOTATION_TYPE,
        "benchmark_id": BENCHMARK_ID,
        "run_sha256": artifact_digest(run),
        "lock_manifest_sha256": artifact_digest(lock),
        "execution_manifest_sha256": lock.get("execution_manifest_sha256"),
        "authority": "Rafael",
        "ood_assignments": [],
        "claims": sorted(claims, key=lambda row: row["claim_id"]),
        "evidence_spans": sorted(spans, key=lambda row: row["span_id"]),
        "items": item_rows,
        "status": "pending_review",
    }
    errors = validate_annotation_packet(payload, run, lock, require_complete=False)
    if errors:
        raise BenchmarkArtifactError("invalid annotation template: " + "; ".join(errors))
    return payload


def _row_errors(
    rows: Any,
    *,
    path: str,
    id_field: str,
    expected_ids: set[str] | None,
    boolean_fields: tuple[str, ...],
    allowed_fields: set[str],
    require_complete: bool,
) -> tuple[list[str], set[str]]:
    if not isinstance(rows, list):
        return [f"/{path}: expected array"], set()
    errors: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        base = f"/{path}/{index}"
        if not isinstance(row, dict):
            errors.append(f"{base}: expected object")
            continue
        for field in sorted(set(row) - allowed_fields):
            errors.append(f"{base}/{field}: unexpected field")
        identifier = row.get(id_field)
        if not isinstance(identifier, str) or not identifier:
            errors.append(f"{base}/{id_field}: expected nonempty string")
        elif identifier in seen:
            errors.append(f"{base}/{id_field}: duplicate")
        else:
            seen.add(identifier)
        for field in boolean_fields:
            value = row.get(field)
            if require_complete and not isinstance(value, bool):
                errors.append(f"{base}/{field}: expected boolean")
            elif not require_complete and value is not None and not isinstance(value, bool):
                errors.append(f"{base}/{field}: expected boolean or null")
        rationale = row.get("rationale")
        if require_complete and (not isinstance(rationale, str) or not rationale.strip()):
            errors.append(f"{base}/rationale: expected nonempty string")
        elif not require_complete and not isinstance(rationale, str):
            errors.append(f"{base}/rationale: expected string")
    if expected_ids is not None and seen != expected_ids:
        noun = {"items": "item", "claims": "claim", "evidence_spans": "evidence span"}[path]
        errors.append(f"/{path}: exact {noun} coverage required")
    return errors, seen


def validate_annotation_packet(
    payload: Any,
    run: dict[str, Any],
    lock: dict[str, Any],
    *,
    require_complete: bool,
) -> list[str]:
    if not isinstance(payload, dict):
        return ["/: expected annotation object"]
    errors: list[str] = []
    for field in sorted(set(payload) - _ANNOTATION_FIELDS):
        errors.append(f"/{field}: unexpected field")
    expected = {
        "schema_version": 1,
        "artifact_type": ANNOTATION_TYPE,
        "benchmark_id": BENCHMARK_ID,
        "run_sha256": artifact_digest(run),
        "lock_manifest_sha256": artifact_digest(lock),
        "execution_manifest_sha256": lock.get("execution_manifest_sha256"),
        "authority": "Rafael",
        "status": "completed" if require_complete else payload.get("status"),
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            errors.append(f"/{field}: expected {value!r}")
    if not require_complete and payload.get("status") not in {"pending_review", "completed"}:
        errors.append("/status: expected pending_review or completed")
    if _lock_run_record(run, lock) is None:
        errors.append("/lock_manifest_sha256: lock does not contain exact run")

    items = _model_items(run)
    expected_items = {str(item["item_id"]) for item in items}
    expected_claims = {str(item["claim_id"]) for item in items}
    expected_spans = {
        str(span["span_id"])
        for item in items
        for span in item.get("evidence", [])
        if isinstance(span, dict) and isinstance(span.get("span_id"), str)
    }
    row_specs = (
        (
            "ood_assignments",
            "decision_id",
            None,
            ("unsafe",),
            {"decision_id", "unsafe", "rationale"},
        ),
        (
            "claims",
            "claim_id",
            expected_claims,
            ("supported",),
            {"claim_id", "supported", "rationale"},
        ),
        (
            "evidence_spans",
            "span_id",
            expected_spans,
            ("supported",),
            {"span_id", "supported", "rationale"},
        ),
        (
            "items",
            "item_id",
            expected_items,
            ("supported", "useful", "redundant"),
            {"item_id", "supported", "useful", "redundant", "confidence", "rationale"},
        ),
    )
    for path, id_field, expected_ids, booleans, allowed in row_specs:
        row_errors, _ = _row_errors(
            payload.get(path),
            path=path,
            id_field=id_field,
            expected_ids=expected_ids,
            boolean_fields=booleans,
            allowed_fields=allowed,
            require_complete=require_complete,
        )
        errors.extend(row_errors)
    expected_confidence = {str(item["item_id"]): item.get("confidence") for item in items}
    if isinstance(payload.get("items"), list):
        for index, row in enumerate(payload["items"]):
            if isinstance(row, dict) and row.get("confidence") != expected_confidence.get(
                str(row.get("item_id"))
            ):
                errors.append(f"/items/{index}/confidence: does not match locked item")
    return sorted(set(errors))


def verify_p7_score_lock(
    run: dict[str, Any],
    *,
    benchmark_root: Path,
    verified_lock: dict[str, Any] | None,
    lock_private_root: Path | None,
    execution_manifest: dict[str, Any] | None,
    expected_git_sha: str | None,
) -> dict[str, str] | None:
    backend = run.get("backend")
    execution_digest = backend.get("execution_manifest_sha256") if isinstance(backend, dict) else None
    if execution_digest is None:
        return None
    if verified_lock is None or lock_private_root is None or execution_manifest is None:
        raise BenchmarkArtifactError(
            "P7 run requires a verified P7 lock, private lock root, and execution manifest"
        )
    manifest_errors = validate_execution_manifest(execution_manifest, Path(benchmark_root))
    if manifest_errors:
        raise BenchmarkArtifactError("invalid execution manifest: " + "; ".join(manifest_errors))
    expected_execution_digest = execution_manifest_digest(execution_manifest, Path(benchmark_root))
    if execution_digest != expected_execution_digest:
        raise BenchmarkArtifactError("P7 run execution manifest digest mismatch")
    lock_errors = verify_lock_manifest(
        verified_lock,
        private_root=Path(lock_private_root),
        benchmark_root=Path(benchmark_root),
        expected_git_sha=expected_git_sha,
    )
    if lock_errors:
        raise BenchmarkArtifactError("invalid verified P7 lock: " + "; ".join(lock_errors))
    if verified_lock.get("execution_manifest_sha256") != expected_execution_digest:
        raise BenchmarkArtifactError("P7 lock execution manifest digest mismatch")
    record = _lock_run_record(run, verified_lock)
    if record is None:
        raise BenchmarkArtifactError("verified P7 lock does not contain exact run")
    if not isinstance(backend, dict) or record.get("run_id") != backend.get("run_id"):
        raise BenchmarkArtifactError("verified P7 lock run identity mismatch")
    return {
        "execution_manifest_sha256": expected_execution_digest,
        "lock_manifest_sha256": artifact_digest(verified_lock),
    }


def build_comparison(
    lock: dict[str, Any], scores: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    expected_run_ids = [
        row.get("run_id")
        for row in lock.get("runs", [])
        if isinstance(row, dict)
    ]
    if len(expected_run_ids) != 7 or set(scores) != set(expected_run_ids):
        raise BenchmarkArtifactError("comparison requires exact seven run IDs")
    expected_metrics = list(EXPECTED_P5_METRIC_CONTRACTS)
    lock_digest = artifact_digest(lock)
    execution_digest = lock.get("execution_manifest_sha256")
    run_records = {
        row["run_id"]: row for row in lock["runs"] if isinstance(row, dict)
    }
    comparison_runs: list[dict[str, Any]] = []
    synthetic_values: set[bool] = set()
    for run_id in expected_run_ids:
        score = scores[run_id]
        errors = validate_score(score)
        if errors:
            raise BenchmarkArtifactError(f"invalid score {run_id}: " + "; ".join(errors))
        if score.get("lock_manifest_sha256") != lock_digest:
            raise BenchmarkArtifactError(f"score {run_id}: lock manifest digest mismatch")
        if score.get("execution_manifest_sha256") != execution_digest:
            raise BenchmarkArtifactError(f"score {run_id}: execution manifest digest mismatch")
        if score.get("run_sha256") != run_records[run_id].get("artifact_sha256"):
            raise BenchmarkArtifactError(f"score {run_id}: run digest mismatch")
        metrics = score.get("metrics")
        actual_names = [row.get("name") for row in metrics] if isinstance(metrics, list) else []
        if actual_names != expected_metrics:
            raise BenchmarkArtifactError(f"score {run_id}: exact 13 frozen metrics required")
        synthetic_values.add(score.get("synthetic") is True)
        comparison_runs.append(
            {
                "run_id": run_id,
                "run_sha256": score["run_sha256"],
                "score_sha256": artifact_digest(score),
                "metrics": metrics,
            }
        )
    if len(synthetic_values) != 1:
        raise BenchmarkArtifactError("comparison scores must share one synthetic boundary")
    return {
        "schema_version": 1,
        "artifact_type": "azoth_benchmark_comparison",
        "benchmark_id": BENCHMARK_ID,
        "synthetic": synthetic_values.pop(),
        "lock_manifest_sha256": lock_digest,
        "execution_manifest_sha256": execution_digest,
        "runs": comparison_runs,
        "status": "compared",
    }


def build_failure_analysis(
    lock: dict[str, Any],
    runs: dict[str, dict[str, Any]],
    scores: dict[str, dict[str, Any]],
    gold: dict[str, Any],
    annotations: dict[str, Any] | None,
) -> dict[str, Any]:
    comparison = build_comparison(lock, scores)
    expected_run_ids = [row["run_id"] for row in lock["runs"]]
    if set(runs) != set(expected_run_ids):
        raise BenchmarkArtifactError("failure analysis requires exact seven run IDs")
    gold_rows = gold.get("gold_pairs") if isinstance(gold, dict) else None
    if not isinstance(gold_rows, list):
        raise BenchmarkArtifactError("failure analysis requires gold_pairs")
    gold_by_pair = {
        row.get("pair_id"): row
        for row in gold_rows
        if isinstance(row, dict) and isinstance(row.get("pair_id"), str)
    }
    analyses: list[dict[str, Any]] = []
    for run_id in expected_run_ids:
        run = runs[run_id]
        errors = validate_run(run)
        if errors:
            raise BenchmarkArtifactError(f"invalid run {run_id}: " + "; ".join(errors))
        if artifact_digest(run) != next(
            row["artifact_sha256"] for row in lock["runs"] if row["run_id"] == run_id
        ):
            raise BenchmarkArtifactError(f"run {run_id}: lock digest mismatch")
        run_rows = run.get("results")
        if not isinstance(run_rows, list) or {
            row.get("pair_id") for row in run_rows if isinstance(row, dict)
        } != set(gold_by_pair):
            raise BenchmarkArtifactError(f"run {run_id}: exact gold pair coverage required")
        false_positives: list[str] = []
        false_negatives: list[str] = []
        ranking_misses: list[str] = []
        confusion: dict[str, int] = {}
        for row in sorted(run_rows, key=lambda value: value["pair_id"]):
            pair_identifier = row["pair_id"]
            gold_label = int(gold_by_pair[pair_identifier]["label"])
            predicted = int(row["predicted_label"])
            confusion_key = f"{gold_label}->{predicted}"
            confusion[confusion_key] = confusion.get(confusion_key, 0) + 1
            if gold_label < 2 and predicted >= 2:
                false_positives.append(pair_identifier)
            if gold_label >= 2 and predicted < 2:
                false_negatives.append(pair_identifier)
            if gold_label >= 2 and int(row["rank_a"]) > 5 and int(row["rank_b"]) > 5:
                ranking_misses.append(pair_identifier)
        score = scores[run_id]
        threshold_misses = [
            metric["name"] for metric in score["metrics"] if metric.get("threshold_met") is False
        ]
        undefined_metrics = [
            metric["name"]
            for metric in score["metrics"]
            if metric.get("value") is None and metric.get("denominator") == 0
        ]
        analyses.append(
            {
                "run_id": run_id,
                "false_positive_pair_ids": false_positives,
                "false_negative_pair_ids": false_negatives,
                "ranking_miss_pair_ids": ranking_misses,
                "label_confusion": dict(sorted(confusion.items())),
                "threshold_misses": threshold_misses,
                "undefined_metrics": undefined_metrics,
            }
        )

    item_findings = {
        "unsupported_item_ids": [],
        "unhelpful_item_ids": [],
        "redundant_item_ids": [],
    }
    if isinstance(annotations, dict) and isinstance(annotations.get("items"), list):
        for row in annotations["items"]:
            if not isinstance(row, dict) or not isinstance(row.get("item_id"), str):
                continue
            item_id = row["item_id"]
            if row.get("supported") is False:
                item_findings["unsupported_item_ids"].append(item_id)
            if row.get("useful") is False:
                item_findings["unhelpful_item_ids"].append(item_id)
            if row.get("redundant") is True:
                item_findings["redundant_item_ids"].append(item_id)
    for values in item_findings.values():
        values.sort()
    return {
        "schema_version": 1,
        "artifact_type": "azoth_benchmark_failure_analysis",
        "benchmark_id": BENCHMARK_ID,
        "synthetic": comparison["synthetic"],
        "lock_manifest_sha256": comparison["lock_manifest_sha256"],
        "execution_manifest_sha256": comparison["execution_manifest_sha256"],
        "runs": analyses,
        "model_item_findings": item_findings,
        "status": "analyzed",
    }


def _format_value(value: Any) -> str:
    if value is None:
        return "undefined"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render_public_summary(
    comparison: dict[str, Any], failure_analysis: dict[str, Any]
) -> str:
    if comparison.get("lock_manifest_sha256") != failure_analysis.get(
        "lock_manifest_sha256"
    ):
        raise BenchmarkArtifactError("public summary lock manifest mismatch")
    if comparison.get("execution_manifest_sha256") != failure_analysis.get(
        "execution_manifest_sha256"
    ):
        raise BenchmarkArtifactError("public summary execution manifest mismatch")
    lines = [
        "# Operations Decision Support v1 — Locked Results",
        "",
        "This is a bounded 12-paper benchmark. Candidate validity and novelty remain human-reviewed.",
        "The declared 5.6 Sol backend label is frozen, but provider model identity was not exposed by the runtime and is not independently verified.",
        "",
        f"- Lock manifest SHA-256: `{comparison['lock_manifest_sha256']}`",
        f"- Execution manifest SHA-256: `{comparison['execution_manifest_sha256']}`",
        "",
        "| Run | Metric | Value | Numerator / denominator | Uncertainty | Result |",
        "|---|---|---:|---:|---|---|",
    ]
    for run in comparison.get("runs", []):
        for metric in run.get("metrics", []):
            uncertainty = metric.get("uncertainty_result")
            if isinstance(uncertainty, dict):
                lower = _format_value(uncertainty.get("lower"))
                upper = _format_value(uncertainty.get("upper"))
                interval = f"{lower}–{upper}"
            else:
                interval = "undefined"
            threshold = metric.get("threshold_met")
            status = "threshold met" if threshold is True else (
                "threshold not met" if threshold is False else "undefined"
            )
            lines.append(
                "| {run} | {metric} | {value} | {numerator} / {denominator} | {interval} | {status} |".format(
                    run=run["run_id"],
                    metric=metric["name"],
                    value=_format_value(metric.get("value")),
                    numerator=_format_value(metric.get("numerator")),
                    denominator=_format_value(metric.get("denominator")),
                    interval=interval,
                    status=status,
                )
            )
    lines.extend(["", "## Failure counts", ""])
    for run in failure_analysis.get("runs", []):
        lines.append(
            "- {run}: {fp} false positives; {fn} false negatives; {rank} ranking misses; "
            "{missed} thresholds not met; {undefined} undefined metrics.".format(
                run=run["run_id"],
                fp=len(run["false_positive_pair_ids"]),
                fn=len(run["false_negative_pair_ids"]),
                rank=len(run["ranking_miss_pair_ids"]),
                missed=len(run["threshold_misses"]),
                undefined=len(run["undefined_metrics"]),
            )
        )
    lines.extend(
        [
            "",
            "Missed thresholds were retained without retuning. Undefined populations were not imputed.",
            "",
        ]
    )
    return "\n".join(lines)
