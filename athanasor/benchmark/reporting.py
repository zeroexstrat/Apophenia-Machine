from __future__ import annotations

from typing import Any

from athanasor.benchmark.artifacts import (
    SYNTHETIC_NOTICE,
    BenchmarkArtifactError,
    validate_score,
)


def _cell(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _number(value: Any) -> str:
    if value is None:
        return "undefined"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.6f}"


def _uncertainty(metric: dict[str, Any]) -> str:
    result = metric.get("uncertainty_result")
    if not isinstance(result, dict):
        return "not recorded"
    method = str(result.get("method", "not recorded"))
    lower = result.get("lower")
    upper = result.get("upper")
    if lower is None or upper is None:
        return f"{method}: undefined"
    extras: list[str] = []
    if result.get("seed") is not None:
        extras.append(f"seed {result['seed']}")
    if result.get("samples") is not None:
        extras.append(f"{result['samples']} samples")
    suffix = f" ({', '.join(extras)})" if extras else ""
    return f"{method}: {_number(lower)}–{_number(upper)}{suffix}"


def _threshold(metric: dict[str, Any]) -> str:
    threshold = metric.get("threshold")
    if not isinstance(threshold, dict):
        return "not recorded"
    operator = str(threshold.get("operator", "?"))
    target = _number(threshold.get("value"))
    outcome = metric.get("threshold_met")
    rendered = "undefined" if outcome is None else ("met" if outcome else "missed")
    return f"{operator} {target}: {rendered}"


def _provenance_lines(score: dict[str, Any]) -> list[str]:
    commitment = score.get("gold_commitment")
    gold_digest = commitment.get("private_gold_sha256") if isinstance(commitment, dict) else None
    calculation = score.get("calculation") if isinstance(score.get("calculation"), dict) else {}
    return [
        "## Provenance",
        "",
        f"- Benchmark: `{score['benchmark_id']}`",
        f"- Locked run SHA-256: `{score['run_sha256']}`",
        f"- Gold commitment SHA-256: `{gold_digest or 'not recorded'}`",
        f"- Human annotations SHA-256: `{score.get('annotation_sha256') or 'not supplied'}`",
        f"- Calculation version: `{calculation.get('version', 'not recorded')}`",
        f"- Bootstrap seed: `{calculation.get('bootstrap_seed', 'not recorded')}`",
        f"- Bootstrap samples: `{calculation.get('bootstrap_samples', 'not recorded')}`",
        "",
    ]


def _metric_table_lines(metrics: list[dict[str, Any]]) -> list[str]:
    lines = [
        "## Metrics",
        "",
        "| Metric | Value | Numerator | Denominator | Uncertainty | Threshold |",
        "|---|---:|---:|---:|---|---|",
    ]
    for metric in metrics:
        value = (
            f"undefined ({_number(metric.get('numerator'))}/{_number(metric.get('denominator'))})"
            if metric.get("value") is None
            else _number(metric.get("value"))
        )
        lines.append(
            "| "
            + " | ".join(
                _cell(item)
                for item in (
                    metric.get("name"),
                    value,
                    _number(metric.get("numerator")),
                    _number(metric.get("denominator")),
                    _uncertainty(metric),
                    _threshold(metric),
                )
            )
            + " |"
        )
    lines.append("")
    return lines


def _undefined_lines(metrics: list[dict[str, Any]]) -> list[str]:
    undefined = [metric for metric in metrics if metric.get("value") is None]
    lines = ["## Undefined metrics", ""]
    if not undefined:
        lines.extend(["None.", ""])
        return lines
    for metric in undefined:
        lines.append(
            f"- `{metric.get('name')}`: {metric.get('undefined_case', 'population unavailable')} "
            f"({_number(metric.get('numerator'))}/{_number(metric.get('denominator'))})."
        )
    lines.append("")
    return lines


def _failure_lines(metrics: list[dict[str, Any]]) -> list[str]:
    missed = [metric for metric in metrics if metric.get("threshold_met") is False]
    lines = ["## Threshold outcomes", ""]
    if not missed:
        lines.append("No defined metric in this artifact missed its frozen threshold.")
    else:
        lines.extend(
            f"- `{metric.get('name')}`: {_threshold(metric)}." for metric in missed
        )
    lines.append("")
    return lines


def _limitation_lines(score: dict[str, Any]) -> list[str]:
    lines = [
        "## Limitations",
        "",
        "- Metrics are limited to the locked run, exact gold commitment, and explicitly supplied human annotations named above.",
        "- Undefined populations are not imputed and carry no threshold outcome.",
        "- Scientific validity, novelty, and usefulness remain human judgments.",
    ]
    if score.get("synthetic") is True:
        lines.append("- This fictional fixture verifies software contracts only and is not evidence of benchmark or model quality.")
    return lines


def render_markdown(score: dict[str, Any]) -> str:
    errors = validate_score(score)
    if errors:
        raise BenchmarkArtifactError("invalid score artifact: " + "; ".join(errors))
    lines = [f"# Benchmark Report — {score['benchmark_id']}", ""]
    if score.get("synthetic") is True:
        lines.extend([f"> **{SYNTHETIC_NOTICE}**", ""])
    metrics = score["metrics"]
    lines.extend(_provenance_lines(score))
    lines.extend(_metric_table_lines(metrics))
    lines.extend(_undefined_lines(metrics))
    lines.extend(_failure_lines(metrics))
    lines.extend(_limitation_lines(score))
    if score.get("synthetic") is True:
        lines.extend(["", f"> **{SYNTHETIC_NOTICE}**"])
    return "\n".join(lines).rstrip() + "\n"
