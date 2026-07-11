#!/usr/bin/env python3
"""Command-line entrypoint for Azoth."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import click

from .config import Config, load_config, save_config
from .llm import LLMClient
from .registry import VALID_STATUSES, Registry
from .skills import connect as connect_skill
from .skills import detect as detect_skill
from .skills import draft as draft_skill
from .skills import experiment as experiment_skill
from .skills import exhaust as exhaust_skill
from .skills import export_signals as export_signals_skill
from .skills import ingest as ingest_skill
from .skills import ouroboros as ouroboros_skill
from .skills import promote as promote_skill
from .skills import reclassify as reclassify_skill
from .skills import review as review_skill
from .skills import triage as triage_skill
from .session.commands import persist_checkpoint
from .workspace import WorkspaceConflictError, initialize_workspace


def _is_auto_checkpoint_enabled() -> bool:
    raw = os.getenv("AZOTH_AUTO_CHECKPOINT", "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def _summarize_slice_outputs(command: str, outputs: Any) -> list[str]:
    findings = [f"{command}: slice completed"]
    if isinstance(outputs, list):
        findings.append(f"Produced {len(outputs)} output artifact(s).")
        for item in outputs[:3]:
            if not isinstance(item, dict):
                continue
            ident = _output_identifier(item)
            if ident is None:
                continue
            summary = _output_detail_summary(item)
            findings.append(f"- {ident}" + (f" | {summary}" if summary else ""))
            direction = _output_direction(item)
            if direction:
                findings.append(f"  Direction: {direction}")
        if len(outputs) > 3:
            findings.append(f"- ... {len(outputs)-3} more")
    return findings


def _output_identifier(item: dict[str, Any]) -> Any:
    nested_exhaustion = item.get("exhaustion")
    if isinstance(nested_exhaustion, dict):
        return nested_exhaustion.get("paper_id")
    return item.get("paper_id") or item.get("cluster_id") or item.get("gap_id") or item.get("file")


def _output_detail_summary(item: dict[str, Any]) -> str:
    bucket_names = (
        "derivations",
        "exercises",
        "missing_angles",
        "open_questions",
        "unstated_assumptions",
        "experiments",
        "necessary_connections",
    )
    parts: list[str] = []
    for name in bucket_names:
        value = item.get(name)
        if isinstance(value, list):
            parts.append(f"{name}={len(value)}")
    if parts:
        return " ".join(parts)
    status = item.get("status")
    domain = item.get("domain")
    return " ".join(str(part) for part in (domain, status) if part)


def _output_direction(item: dict[str, Any]) -> str:
    candidates = (
        ("experiments", ("hypothesis", "design")),
        ("open_questions", ("question", "how_to_close")),
        ("missing_angles", ("angle", "where_it_lands")),
        ("necessary_connections", ("work", "why_necessary")),
        ("derivations", ("statement", "follows_from")),
    )
    for bucket, keys in candidates:
        values = item.get(bucket)
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, dict):
                continue
            text = " - ".join(str(value.get(key, "")).strip() for key in keys if str(value.get(key, "")).strip())
            if text:
                return text[:300]
    return ""


def _persist_auto_checkpoint(command: str, outputs: Any, *, disable: bool) -> None:
    if disable or not _is_auto_checkpoint_enabled():
        return
    findings = _summarize_slice_outputs(command, outputs)
    memory_path = persist_checkpoint(command=command, findings=findings)
    click.echo(f"Auto checkpoint persisted to {memory_path}", err=True)


def _run_with_command_context(
    command: str, fn: Callable[[], Any], *, checkpoint: Callable[[Any], None] | None = None
) -> Any:
    try:
        result = fn()
    except click.ClickException:
        raise
    except FileNotFoundError as exc:
        raise click.ClickException(f"{command}: {exc}") from None
    except (ValueError, KeyError) as exc:
        message = str(exc).strip().strip("'\"") or exc.__class__.__name__
        raise click.ClickException(f"{command}: {message}") from None
    except RuntimeError as exc:
        message = str(exc).strip() or "unknown runtime failure"
        if message.lower().startswith("vigil"):
            raise click.ClickException(f"{command} blocked by gate check: {message}") from None
        raise click.ClickException(f"{command} failed: {message}") from None
    except Exception as exc:  # pragma: no cover
        raise click.ClickException(f"{command} failed unexpectedly: {exc}") from None
    if checkpoint is not None:
        checkpoint(result)
    return result


@click.group()
def main() -> None:
    """Azoth CLI."""


def _load_skill_config(no_llm: bool) -> tuple[Config, LLMClient | None]:
    cfg = load_config()
    if no_llm:
        return cfg, None

    client = LLMClient(cfg)
    if client.client is None:
        click.echo(
            "LLM backend unavailable; continuing with local classification/extraction fallback."
        )
        return cfg, None
    return cfg, client


def _emit(results: list[dict[str, Any]], json_output: bool) -> None:
    if json_output:
        click.echo(json.dumps(results, indent=2, sort_keys=True))
        return

    for idx, item in enumerate(results, start=1):
        ident = (
            item.get("paper_id")
            or item.get("pair_id")
            or item.get("cluster_id")
            or item.get("gap_id")
        )
        if ident is None and isinstance(item, dict):
            ident = item.get("file")
        if ident is None:
            ident = f"result-{idx}"
        click.echo(f"  - {ident}")


def _load_assignments(path: Path) -> list[dict[str, Any]]:
    """Parse an agent-produced assignments file: a JSON array, or {"assignments": [...]}."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise click.ClickException(f"Could not read assignments JSON {path}: {exc}") from None
    if isinstance(payload, dict) and isinstance(payload.get("assignments"), list):
        payload = payload["assignments"]
    if not isinstance(payload, list):
        raise click.ClickException(
            "Assignments must be a JSON array of {paper_id, domain, ...} objects "
            'or an object with an "assignments" array.'
        )
    return [item for item in payload if isinstance(item, dict)]


def _load_exhaust_records(path: Path) -> list[dict[str, Any]]:
    """Parse agent-produced exhaustion records: a JSON array, or {"exhaustion": [...]}."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise click.ClickException(f"Could not read exhaust records JSON {path}: {exc}") from None
    if isinstance(payload, dict):
        for key in ("exhaustion", "records", "papers"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    if not isinstance(payload, list):
        raise click.ClickException(
            "Exhaust records must be a JSON array of {paper_id, <buckets>...} objects "
            'or an object with an "exhaustion" array.'
        )
    return [item for item in payload if isinstance(item, dict)]


def _coerce_config_value(raw: str) -> Any:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        lowered = raw.lower()
        if lowered in {"true", "false", "null", "none"}:
            if lowered == "true":
                return True
            if lowered == "false":
                return False
            return None
        return raw


def _set_nested(payload: dict[str, Any], key: str, value: Any) -> None:
    target = payload
    parts = key.split(".")
    for part in parts[:-1]:
        current = target.get(part)
        if current is None:
            target[part] = {}
            current = target[part]
        if not isinstance(current, dict):
            raise click.ClickException(
                f"Cannot set '{key}': '{part}' is not a mapping (lists have no dotted keys; "
                f"pass a JSON value for the whole field instead)."
            )
        target = current
    last = parts[-1]
    existing = target.get(last)
    if isinstance(existing, list) and not isinstance(value, list):
        raise click.ClickException(
            f"Cannot replace list '{key}' with a scalar; pass a JSON list, e.g. '[\"a\", \"b\"]'."
        )
    target[last] = value


def _status_snapshot(registry: Registry, domain: str | None, status_filter: str | None) -> dict[str, Any]:
    entries = registry.list()
    if domain is not None:
        entries = [entry for entry in entries if entry.get("domain") == domain]
    if status_filter is not None:
        entries = [entry for entry in entries if entry.get("status") == status_filter]

    return {
        "total": len(entries),
        "status_counts": Counter(entry.get("status") for entry in entries),
        "domain_counts": Counter(entry.get("domain") for entry in entries),
        "entries": entries,
    }


def _status_lines(payload: dict[str, Any]) -> list[str]:
    lines: list[str] = [f"Registry entries: {payload['total']}"]
    if payload["status_counts"]:
        lines.append("By status:")
        for status, count in sorted(payload["status_counts"].items()):
            lines.append(f"- {status}: {count}")
    if payload["domain_counts"]:
        lines.append("By domain:")
        for domain, count in sorted(payload["domain_counts"].items()):
            lines.append(f"- {domain}: {count}")

    if payload["entries"]:
        lines.append("Entries:")
        for entry in payload["entries"][:20]:
            lines.append(
                f"- {entry.get('paper_id', 'unknown')} | {entry.get('status', 'unknown')} | {entry.get('domain', 'unknown')} | {entry.get('title', 'untitled')}"
            )
    return lines


@main.command("init")
@click.argument("directory", type=click.Path(path_type=Path))
def cmd_init(directory: Path) -> None:
    """Create or repair an empty Azoth workspace."""
    try:
        root = initialize_workspace(directory)
    except WorkspaceConflictError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(f"Initialized Azoth workspace: {root}")


@main.command("ingest")
@click.argument("paths", nargs=-1, type=click.Path(exists=True, path_type=Path), required=True)
@click.option("--reprocess", is_flag=True, help="Reprocess files already in registry.")
@click.option("--domain-override", default=None, help="Force domain label for classification.")
@click.option("--no-llm", is_flag=True, help="Disable LLM extraction (fallback mode).")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON")
@click.option("--no-auto-checkpoint", is_flag=True, help="Skip automatic post-slice memory checkpoint.")
def cmd_ingest(
    paths: tuple[Path, ...],
    reprocess: bool,
    domain_override: str | None,
    no_llm: bool,
    json_output: bool,
    no_auto_checkpoint: bool,
) -> None:
    """Ingest PDFs from one or more paths into Albedo."""
    def _run() -> list[dict[str, Any]]:
        cfg, llm = _load_skill_config(no_llm)
        outputs: list[dict[str, Any]] = []

        for path in paths:
            outputs.extend(
                ingest_skill.ingest_path(
                    target=path,
                    config=cfg,
                    llm=llm,
                    reprocess=reprocess,
                    domain_override=domain_override,
                )
            )
        return outputs

    outputs = _run_with_command_context(
        "azoth ingest",
        _run,
        checkpoint=lambda result: _persist_auto_checkpoint(
            "azoth ingest", result, disable=no_auto_checkpoint
        ),
    )

    if json_output:
        click.echo(json.dumps(outputs, indent=2, sort_keys=True))
    else:
        skipped = [item for item in outputs if item.get("status") == "skipped"]
        ingested = [item for item in outputs if item.get("status") != "skipped"]
        message = f"Ingested {len(ingested)} paper(s)."
        if skipped:
            message += f" Skipped {len(skipped)} file(s)."
        click.echo(message)
        _emit(ingested, json_output=False)
        for item in skipped:
            click.echo(f"  - skipped {item.get('filename')}: {item.get('skip_reason')}")


@main.command("reclassify")
@click.option("--scope", default="unclassified", show_default=True, help="'unclassified', 'all', or a domain name.")
@click.option("--min-confidence", default=0.6, type=click.FloatRange(0.0, 1.0), show_default=True)
@click.option(
    "--allow-new-domains/--no-allow-new-domains",
    default=True,
    show_default=True,
    help="Let the model adopt a confident new domain outside the current taxonomy.",
)
@click.option(
    "--apply/--dry-run",
    "apply",
    default=True,
    show_default=True,
    help="Move files and update the registry, or only report intended changes.",
)
@click.option(
    "--assignments",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="JSON of agent-produced domain decisions ([{paper_id, domain, confidence?, proposed?}]). "
    "When the driving agent classifies the papers itself, no LLM backend is needed.",
)
@click.option("--no-llm", is_flag=True, help="Use heuristic classification only (ignored with --assignments).")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON")
@click.option("--no-auto-checkpoint", is_flag=True, help="Skip automatic post-slice memory checkpoint.")
def cmd_reclassify(
    scope: str,
    min_confidence: float,
    allow_new_domains: bool,
    apply: bool,
    assignments: Path | None,
    no_llm: bool,
    json_output: bool,
    no_auto_checkpoint: bool,
) -> None:
    """Re-file already-ingested papers into (possibly new) domains.

    Default: re-run classification (configured LLM backend or heuristics).
    With --assignments: apply domain decisions the driving agent produced by
    reading the papers itself — the agent is the classifier, no backend required.
    """
    def _run() -> list[dict[str, Any]]:
        parsed_assignments = _load_assignments(assignments) if assignments is not None else None
        # Assignments carry their own decisions; skip building an LLM client.
        cfg, llm = _load_skill_config(no_llm or parsed_assignments is not None)
        return reclassify_skill.run_reclassify(
            config=cfg,
            llm=llm,
            scope=scope,
            allow_new_domains=allow_new_domains,
            min_confidence=min_confidence,
            apply=apply,
            assignments=parsed_assignments,
        )

    outputs = _run_with_command_context(
        "azoth reclassify",
        _run,
        checkpoint=lambda result: _persist_auto_checkpoint(
            "azoth reclassify", result, disable=no_auto_checkpoint
        ),
    )

    if json_output:
        click.echo(json.dumps(outputs, indent=2, sort_keys=True))
        return

    moved = [item for item in outputs if item.get("action") in {"reassigned", "would_reassign"}]
    verb = "Would reassign" if not apply else "Reassigned"
    click.echo(f"Reviewed {len(outputs)} paper(s); {verb.lower()} {len(moved)}.")
    for item in moved:
        marker = " (new domain)" if item.get("proposed") else ""
        click.echo(
            f"  - {item['paper_id']}: {item['old_domain']} -> {item['new_domain']}"
            f"{marker} [conf {item['confidence']}]"
        )


@main.command("awaken")
@click.argument("domain", required=False)
@click.option("--all", "all_scope", is_flag=True, help="Exhaust all domains.")
@click.option("--depth", default=3, type=click.IntRange(1, 5), show_default=True)
@click.option("--count", default=3, help="Max papers per domain in --all or --domain mode.")
@click.option("--reprocess", is_flag=True, help="Allow reprocessing exhausted papers.")
@click.option("--no-llm", is_flag=True, help="Disable LLM exhaustion prompts.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON")
@click.option("--no-auto-checkpoint", is_flag=True, help="Skip automatic post-slice memory checkpoint.")
def cmd_awaken(
    domain: str | None,
    all_scope: bool,
    depth: int,
    count: int,
    reprocess: bool,
    no_llm: bool,
    json_output: bool,
    no_auto_checkpoint: bool,
) -> None:
    """Activate domain subagents (`/awaken`) for one domain or all domains."""
    if not domain and not all_scope:
        raise click.ClickException("Provide domain or --all.")
    if domain and all_scope:
        raise click.ClickException("Use either a domain or --all, not both.")

    def _run() -> list[dict[str, Any]]:
        cfg, llm = _load_skill_config(no_llm)
        outputs: list[dict[str, Any]] = []

        if all_scope:
            for target_domain in cfg.domains:
                outputs.extend(
                    exhaust_skill.run_exhaust(
                        config=cfg,
                        llm=llm,
                        domain=target_domain,
                        all_scope=False,
                        depth=depth,
                        count=count,
                        reprocess=reprocess,
                    )
                )
        else:
            outputs = exhaust_skill.run_exhaust(
                config=cfg,
                llm=llm,
                domain=domain,
                all_scope=False,
                depth=depth,
                count=count,
                reprocess=reprocess,
            )
        return outputs

    outputs = _run_with_command_context(
        "azoth awaken",
        _run,
        checkpoint=lambda result: _persist_auto_checkpoint(
            "azoth awaken", result, disable=no_auto_checkpoint
        ),
    )

    if json_output:
        click.echo(json.dumps(outputs, indent=2, sort_keys=True))
    else:
        if all_scope:
            click.echo(f"Awakened all domains. Exhausted {len(outputs)} paper(s).")
        else:
            click.echo(f"Awakened {domain}. Exhausted {len(outputs)} paper(s).")
        _emit(outputs, json_output=False)


@main.command("exhaust")
@click.argument("paper_id", required=False)
@click.option("--domain", default=None, help="Exhaust a specific domain bucket.")
@click.option("--all", "all_scope", is_flag=True, help="Exhaust all eligible papers.")
@click.option("--depth", default=3, type=click.IntRange(1, 5), show_default=True)
@click.option("--count", default=0, help="Max papers in --all or --domain mode.")
@click.option("--reprocess", is_flag=True, help="Allow reprocessing exhausted papers.")
@click.option(
    "--from-file",
    "from_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="JSON of exhaustion records the driving agent produced ([{paper_id, derivations, "
    "missing_angles, ...}]). The agent is the exhauster — no LLM backend contacted.",
)
@click.option("--no-llm", is_flag=True, help="Disable LLM exhaustion prompts.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON")
@click.option("--no-auto-checkpoint", is_flag=True, help="Skip automatic post-slice memory checkpoint.")
def cmd_exhaust(
    paper_id: str | None,
    domain: str | None,
    all_scope: bool,
    depth: int,
    count: int,
    reprocess: bool,
    from_file: Path | None,
    no_llm: bool,
    json_output: bool,
    no_auto_checkpoint: bool,
) -> None:
    """Generate structured exhaust output for one or many papers.

    Default: azoth's configured LLM backend generates the exhaustion.
    With --from-file: apply exhaustion records the driving agent produced by reading
    the papers itself — the agent is the generator (enables cross-model comparison).
    """
    if not from_file and not paper_id and not domain and not all_scope:
        raise click.ClickException("Provide paper_id, --domain, --all, or --from-file.")

    def _run() -> list[dict[str, Any]]:
        if from_file is not None:
            records = _load_exhaust_records(from_file)
            cfg = load_config()
            return exhaust_skill.apply_agent_exhaust(records, config=cfg)
        cfg, llm = _load_skill_config(no_llm)
        return exhaust_skill.run_exhaust(
            target=paper_id,
            config=cfg,
            llm=llm,
            depth=depth,
            domain=domain,
            all_scope=all_scope,
            count=count,
            reprocess=reprocess,
        )

    outputs = _run_with_command_context(
        "azoth exhaust",
        _run,
        checkpoint=lambda result: _persist_auto_checkpoint(
            "azoth exhaust", result, disable=no_auto_checkpoint
        ),
    )
    if json_output:
        click.echo(json.dumps(outputs, indent=2, sort_keys=True))
    else:
        click.echo(f"Exhausted {len(outputs)} paper(s).")
        _emit(outputs, json_output=False)


@main.command("status")
@click.option("--domain", default=None, help="Filter by domain.")
@click.option(
    "--status",
    "status_filter",
    type=click.Choice(sorted(VALID_STATUSES), case_sensitive=False),
    default=None,
    help="Filter by registry status.",
)
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON")
def cmd_status(domain: str | None, status_filter: str | None, json_output: bool) -> None:
    """Show registry progress and filtered entries."""
    cfg = load_config()
    registry = Registry(Path(cfg.project_root) / "albedo" / "registry.jsonl")
    payload = _status_snapshot(registry, domain, status_filter)

    if json_output:
        payload["status_counts"] = dict(payload["status_counts"])
        payload["domain_counts"] = dict(payload["domain_counts"])
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for line in _status_lines(payload):
            click.echo(line)


@main.command("export")
@click.option("--signals", is_flag=True, help="Export bounded candidate signals.")
@click.option("--max", "max_signals", default=3, type=click.IntRange(min=1), show_default=True)
@click.option("--out", "output_path", required=True, type=click.Path(path_type=Path), help="Output JSON path.")
def cmd_export(signals: bool, max_signals: int, output_path: Path) -> None:
    """Export bounded Azoth signals for external staging."""
    if not signals:
        raise click.ClickException("Only signal export is supported; pass --signals.")

    def _run() -> Path:
        cfg = load_config()
        return export_signals_skill.write_export(
            Path(cfg.project_root),
            output_path,
            max_signals=max_signals,
        )

    path = _run_with_command_context("azoth export", _run)
    click.echo(f"  - {path}")


@main.command("config")
@click.option("--show", is_flag=True, help="Show current resolved config.")
@click.option(
    "--set",
    "set_kv",
    nargs=2,
    type=str,
    metavar="KEY VALUE",
    help="Set config value via dot notation, e.g. `--set llm.model gpt-4`.",
)
def cmd_config(show: bool, set_kv: tuple[str, str] | None) -> None:
    """Inspect or update `azoth.config.yaml`."""
    cfg = load_config()
    config_path = Path(cfg.project_root) / "azoth.config.yaml"

    if show and set_kv:
        raise click.ClickException("Choose either --show or --set.")
    if not show and not set_kv:
        show = True

    payload = {
        "llm": dict(cfg.llm),
        "embeddings": dict(cfg.embeddings),
        "paths": dict(cfg.paths),
        "domains": list(cfg.domains),
        "exhaustion": dict(cfg.exhaustion),
    }

    if set_kv is not None:
        key, raw_value = set_kv
        payload_value = _coerce_config_value(raw_value)
        _set_nested(payload, key, payload_value)

        normalized = Config(
            llm=payload["llm"],
            paths=payload["paths"],
            domains=list(payload["domains"]),
            embeddings=payload["embeddings"],
            exhaustion=payload["exhaustion"],
            project_root=str(cfg.project_root),
        )
        save_config(normalized, path=config_path)
        click.echo(f"Updated {config_path}: {key} = {payload_value}")
        if show:
            show = False

    if show:
        click.echo(json.dumps(payload, indent=2, sort_keys=True))


@main.command("connect")
@click.option("--within", required=False, help="Domain to run within-domain pass.")
@click.option("--cross", nargs=2, metavar="D1 D2", required=False, help="Domain pair for cross-domain pass.")
@click.option("--paper", "paper_id", help="Single paper id sweep.")
@click.option("--all", "all_scope", is_flag=True, help="Run all candidate pairs.")
@click.option(
    "--from-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Import agent-produced connection records from JSON.",
)
@click.option(
    "--reanalyze-depth-upgrades",
    is_flag=True,
    help="Re-run previously analyzed pairs when either paper was exhausted at a deeper depth.",
)
@click.option("--no-llm", is_flag=True, help="Disable LLM pair assessment.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON")
@click.option("--no-auto-checkpoint", is_flag=True, help="Skip automatic post-slice memory checkpoint.")
def cmd_connect(
    within: str | None,
    cross: tuple[str, str] | None,
    paper_id: str | None,
    all_scope: bool,
    from_file: Path | None,
    reanalyze_depth_upgrades: bool,
    no_llm: bool,
    json_output: bool,
    no_auto_checkpoint: bool,
) -> None:
    """Discover connection candidates between paper pairs."""
    modes = [within, cross, paper_id, all_scope, from_file]
    if not any(modes):
        raise click.ClickException("Provide --within, --cross, --paper, --all, or --from-file.")

    if sum(bool(value) for value in modes) != 1:
        raise click.ClickException(
            "Use exactly one mode: --within, --cross, --paper, --all, or --from-file."
        )
    if from_file is not None and (no_llm or reanalyze_depth_upgrades):
        raise click.ClickException(
            "--from-file cannot be combined with --no-llm or --reanalyze-depth-upgrades."
        )

    def _run() -> list[dict[str, Any]]:
        if from_file is not None:
            records = connect_skill.load_agent_connections(from_file)
            return connect_skill.apply_agent_connections(records, config=load_config())
        cfg, llm = _load_skill_config(no_llm)
        return connect_skill.connect(
            config=cfg,
            llm=llm,
            within=within,
            cross=cross,
            paper_id=paper_id,
            all_scope=all_scope,
            reanalyze_depth_upgrades=reanalyze_depth_upgrades,
        )

    outputs = _run_with_command_context(
        "azoth connect",
        _run,
        checkpoint=lambda result: _persist_auto_checkpoint(
            "azoth connect", result, disable=no_auto_checkpoint
        ),
    )
    if json_output:
        click.echo(json.dumps(outputs, indent=2, sort_keys=True))
    else:
        retrieval_only = bool(outputs) and all(
            item.get("artifact_type") == "retrieval_candidate"
            for item in outputs
            if isinstance(item, dict)
        )
        label = "retrieval candidate(s)" if retrieval_only else "connection(s)"
        click.echo(f"Generated {len(outputs)} {label}.")
        _emit(outputs, json_output=False)


@main.command("detect")
@click.option("--domain", default=None, help="Limit to within-domain clusters.")
@click.option("--cross", nargs=2, metavar="D1 D2", required=False, help="Limit to cross-domain pairs.")
@click.option("--cluster", "cluster", required=False, help="Force an existing hypothesis id.")
@click.option("--all", "all_scope", is_flag=True, help="Scan all connection artifacts.")
@click.option(
    "--from-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Import agent-produced hypothesis records from JSON.",
)
@click.option("--no-llm", is_flag=True, help="Disable LLM cluster synthesis.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON")
@click.option("--no-auto-checkpoint", is_flag=True, help="Skip automatic post-slice memory checkpoint.")
def cmd_detect(
    domain: str | None,
    cross: tuple[str, str] | None,
    cluster: str | None,
    all_scope: bool,
    from_file: Path | None,
    no_llm: bool,
    json_output: bool,
    no_auto_checkpoint: bool,
) -> None:
    """Synthesize gap hypotheses from connection clusters."""
    modes = [domain, cross, cluster, all_scope, from_file]
    if not any(modes):
        raise click.ClickException("Provide --domain, --cross, --cluster, --all, or --from-file.")
    if sum(bool(value) for value in modes) != 1:
        raise click.ClickException(
            "Use exactly one mode: --domain, --cross, --cluster, --all, or --from-file."
        )
    if from_file is not None and no_llm:
        raise click.ClickException("--from-file cannot be combined with --no-llm.")

    def _run() -> list[dict[str, Any]]:
        if from_file is not None:
            records = detect_skill.load_agent_hypotheses(from_file)
            return detect_skill.apply_agent_hypotheses(records, config=load_config())
        cfg, llm = _load_skill_config(no_llm)
        return detect_skill.detect(
            config=cfg,
            llm=llm,
            domain=domain,
            cross=cross,
            all_scope=all_scope,
            cluster=cluster,
        )

    outputs = _run_with_command_context(
        "azoth detect",
        _run,
        checkpoint=lambda result: _persist_auto_checkpoint(
            "azoth detect", result, disable=no_auto_checkpoint
        ),
    )
    if json_output:
        click.echo(json.dumps(outputs, indent=2, sort_keys=True))
    else:
        click.echo(f"Generated {len(outputs)} hypothesis cluster(s).")
        if no_llm and not outputs:
            click.echo("No substantive synthesis was attempted; provide agent output with detect --from-file.")
        _emit(outputs, json_output=False)


@main.command("draft")
@click.argument("gap_id", required=False)
@click.option("--top", default=1, type=click.IntRange(min=1), show_default=True, help="Top N pending hypotheses.")
@click.option("--no-llm", is_flag=True, help="Disable LLM drafting")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON")
@click.option("--no-auto-checkpoint", is_flag=True, help="Skip automatic post-slice memory checkpoint.")
def cmd_draft(
    gap_id: str | None,
    top: int,
    no_llm: bool,
    json_output: bool,
    no_auto_checkpoint: bool,
) -> None:
    """Draft rubedo notes from hypothesis files."""
    def _run() -> list[Path]:
        cfg, llm = _load_skill_config(no_llm)
        return draft_skill.run_draft(
            gap_id=gap_id,
            top=top,
            config=cfg,
            llm=llm,
        )

    paths = _run_with_command_context(
        "azoth draft",
        _run,
        checkpoint=lambda result: _persist_auto_checkpoint(
            "azoth draft", [str(path) for path in result], disable=no_auto_checkpoint
        ),
    )

    if json_output:
        click.echo(json.dumps([str(path) for path in paths], indent=2))
    else:
        for path in paths:
            click.echo(f"  - {path}")
        click.echo(f"Generated {len(paths)} draft file(s).")


@main.command("triage")
@click.argument("cluster_id")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON")
@click.option("--no-auto-checkpoint", is_flag=True, help="Skip automatic post-slice memory checkpoint.")
def cmd_triage(cluster_id: str, json_output: bool, no_auto_checkpoint: bool) -> None:
    """Build a human review packet for one Rubedo hypothesis."""
    def _run() -> Path:
        cfg = load_config()
        return triage_skill.run_triage(cluster_id, config=cfg)

    path = _run_with_command_context(
        "azoth triage",
        _run,
        checkpoint=lambda result: _persist_auto_checkpoint(
            "azoth triage", [str(result)], disable=no_auto_checkpoint
        ),
    )
    _emit_path(path, json_output)


@main.command("review")
@click.argument("cluster_id")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON")
@click.option("--no-auto-checkpoint", is_flag=True, help="Skip automatic post-slice memory checkpoint.")
def cmd_review(cluster_id: str, json_output: bool, no_auto_checkpoint: bool) -> None:
    """Run deterministic gate review for one Rubedo hypothesis."""
    def _run() -> Path:
        cfg = load_config()
        return review_skill.run_review(cluster_id, config=cfg)

    path = _run_with_command_context(
        "azoth review",
        _run,
        checkpoint=lambda result: _persist_auto_checkpoint(
            "azoth review", [str(result)], disable=no_auto_checkpoint
        ),
    )
    _emit_path(path, json_output)


@main.command("experiment")
@click.argument("cluster_id")
@click.option("--gap-rank", default=1, type=click.IntRange(min=1), show_default=True, help="Ranked gap to convert.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON")
@click.option("--no-auto-checkpoint", is_flag=True, help="Skip automatic post-slice memory checkpoint.")
def cmd_experiment(cluster_id: str, gap_rank: int, json_output: bool, no_auto_checkpoint: bool) -> None:
    """Generate a concrete pilot experiment spec from a Rubedo gap."""
    def _run() -> Path:
        cfg = load_config()
        return experiment_skill.run_experiment(cluster_id, gap_rank=gap_rank, config=cfg)

    path = _run_with_command_context(
        "azoth experiment",
        _run,
        checkpoint=lambda result: _persist_auto_checkpoint(
            "azoth experiment", [str(result)], disable=no_auto_checkpoint
        ),
    )
    _emit_path(path, json_output)


@main.command("promote")
@click.argument("cluster_id")
@click.option("--decision", type=click.Choice(sorted(promote_skill.VALID_DECISIONS)), required=True)
@click.option("--reviewer", required=True, help="Human reviewer name or handle.")
@click.option("--note", required=True, help="Decision rationale.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON")
@click.option("--no-auto-checkpoint", is_flag=True, help="Skip automatic post-slice memory checkpoint.")
def cmd_promote(
    cluster_id: str,
    decision: str,
    reviewer: str,
    note: str,
    json_output: bool,
    no_auto_checkpoint: bool,
) -> None:
    """Record a human decision for one Rubedo hypothesis."""
    def _run() -> Path:
        cfg = load_config()
        return promote_skill.run_promote(
            cluster_id,
            decision=decision,
            reviewer=reviewer,
            note=note,
            config=cfg,
        )

    path = _run_with_command_context(
        "azoth promote",
        _run,
        checkpoint=lambda result: _persist_auto_checkpoint(
            "azoth promote", [str(result)], disable=no_auto_checkpoint
        ),
    )
    _emit_path(path, json_output)


@main.command("ouroboros")
@click.argument("cluster_id")
@click.option("--download/--no-download", default=True, show_default=True, help="Download safe PDF sources into Nigredo inbox.")
@click.option("--include-impact", multiple=True, help="Prior-art impact label to include. Repeatable.")
@click.option("--max-sources", default=8, type=click.IntRange(min=1), show_default=True, help="Maximum source rows to queue.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON")
@click.option("--no-auto-checkpoint", is_flag=True, help="Skip automatic post-slice memory checkpoint.")
def cmd_ouroboros(
    cluster_id: str,
    download: bool,
    include_impact: tuple[str, ...],
    max_sources: int,
    json_output: bool,
    no_auto_checkpoint: bool,
) -> None:
    """Expand rejected prior art back into Nigredo."""
    def _run() -> Path:
        cfg = load_config()
        impacts = list(include_impact) if include_impact else None
        return ouroboros_skill.run_ouroboros(
            cluster_id,
            config=cfg,
            download=download,
            include_impacts=impacts,
            max_sources=max_sources,
        )

    path = _run_with_command_context(
        "azoth ouroboros",
        _run,
        checkpoint=lambda result: _persist_auto_checkpoint(
            "azoth ouroboros", [str(result)], disable=no_auto_checkpoint
        ),
    )
    _emit_path(path, json_output)


def _emit_path(path: Path, json_output: bool) -> None:
    if json_output:
        click.echo(json.dumps(str(path), indent=2))
        return
    click.echo(f"  - {path}")


def _run_python_module(module_name: str, argv: list[str], *, root: Path) -> int:
    cmd = [sys.executable, "-m", module_name, *argv]
    env = os.environ.copy()
    env["AZOTH_PROJECT_ROOT"] = str(root.resolve())
    try:
        result = subprocess.run(
            cmd,
            cwd=str(root.resolve()),
            env=env,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise click.ClickException(f"Failed to launch '{module_name}': {exc}") from None
    if result.returncode != 0:
        output = (result.stdout or "") + (result.stderr or "")
        raise click.ClickException(
            f"External module '{module_name}' failed with exit code {result.returncode}: {output.strip() or 'no output'}"
        )
    # Surface the module's report on success too — a silent validate/migrate
    # run reads as if nothing was checked.
    output = (result.stdout or "").strip()
    if output:
        click.echo(output)
    stderr_output = (result.stderr or "").strip()
    if stderr_output:
        click.echo(stderr_output, err=True)
    return result.returncode


@main.command("validate")
@click.argument("paths", nargs=-1, type=click.Path(path_type=Path))
@click.option("--all", "all_scope", is_flag=True, help="Validate all known artifact folders.")
@click.option("--schema", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="Override schema path")
@click.option("--fix", is_flag=True, help="Write safe fixes")
def cmd_validate(paths: tuple[Path, ...], all_scope: bool, schema: Path | None, fix: bool) -> None:
    """Validate artifacts using local schema definitions."""
    if not all_scope and not paths:
        raise click.ClickException("Pass files/directories or --all")

    argv = ["validate.py"]
    if all_scope:
        argv.append("--all")
    if schema is not None:
        argv += ["--schema", str(schema)]
    if fix:
        argv.append("--fix")
    argv.extend(str(path) for path in paths)
    root = Path(load_config().project_root)
    _run_with_command_context(
        "azoth validate",
        lambda: _run_python_module("athanasor.scripts.validate", argv[1:], root=root),
    )


@main.command("migrate")
@click.argument("paths", nargs=-1, type=click.Path(path_type=Path))
@click.option("--all", "all_scope", is_flag=True, help="Migrate all known artifact folders.")
@click.option("--target", "target_version", type=int, help="Set a global target schema_version value.")
@click.option("--library-version", type=int, help="Target SCHEMA.yaml version (library outputs)")
@click.option("--exhaust-version", type=int, help="Target EXHAUST_SCHEMA.yaml version")
@click.option("--connect-version", type=int, help="Target CONNECT_SCHEMA.yaml version")
@click.option("--detect-version", type=int, help="Target DETECT_SCHEMA.yaml version")
@click.option("--dry-run", is_flag=True, help="Show planned changes only")
@click.option("--json", "json_output", is_flag=True, help="Emit JSON result payload")
def cmd_migrate(
    paths: tuple[Path, ...],
    all_scope: bool,
    target_version: int | None,
    library_version: int | None,
    exhaust_version: int | None,
    connect_version: int | None,
    detect_version: int | None,
    dry_run: bool,
    json_output: bool,
) -> None:
    """Migrate YAML artifacts across schema versions and normalize legacy fields."""
    if not all_scope and not paths:
        raise click.ClickException("Pass paths or --all")

    argv = ["migrate.py"]
    if all_scope:
        argv.append("--all")
    if dry_run:
        argv.append("--dry-run")
    if json_output:
        argv.append("--json")
    if target_version is not None:
        argv += ["--target", str(target_version)]
    if library_version is not None:
        argv += ["--library-version", str(library_version)]
    if exhaust_version is not None:
        argv += ["--exhaust-version", str(exhaust_version)]
    if connect_version is not None:
        argv += ["--connect-version", str(connect_version)]
    if detect_version is not None:
        argv += ["--detect-version", str(detect_version)]

    argv.extend(str(path) for path in paths)
    root = Path(load_config().project_root)
    _run_with_command_context(
        "azoth migrate",
        lambda: _run_python_module("athanasor.scripts.migrate", argv[1:], root=root),
    )


if __name__ == "__main__":
    main()
