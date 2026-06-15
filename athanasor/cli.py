#!/usr/bin/env python3
"""Command-line entrypoint for Azoth."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import click

from .config import Config, load_config
from .llm import LLMClient
from .skills import connect as connect_skill
from .skills import detect as detect_skill
from .skills import draft as draft_skill
from .skills import exhaust as exhaust_skill
from .skills import ingest as ingest_skill


@click.group()
def main() -> None:
    """Azoth CLI."""


def _load_skill_config(no_llm: bool) -> tuple[Config, LLMClient | None]:
    cfg = load_config()
    if no_llm:
        return cfg, None

    client = LLMClient(cfg)
    if client.client is None:
        raise click.ClickException(
            "LLM client unavailable. Install/openai and check azoth.config.yaml or use --no-llm."
        )
    return cfg, client


def _emit(results: list[dict[str, Any]], json_output: bool) -> None:
    if json_output:
        click.echo(json.dumps(results, indent=2, sort_keys=True))
        return

    for idx, item in enumerate(results, start=1):
        ident = item.get("paper_id") or item.get("cluster_id") or item.get("gap_id")
        if ident is None and isinstance(item, dict):
            ident = item.get("file")
        if ident is None:
            ident = f"result-{idx}"
        click.echo(f"  - {ident}")


@main.command("ingest")
@click.argument("paths", nargs=-1, type=click.Path(exists=True, path_type=Path), required=True)
@click.option("--reprocess", is_flag=True, help="Reprocess files already in registry.")
@click.option("--domain-override", default=None, help="Force domain label for classification.")
@click.option("--no-llm", is_flag=True, help="Disable LLM extraction (fallback mode).")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON")
def cmd_ingest(
    paths: tuple[Path, ...],
    reprocess: bool,
    domain_override: str | None,
    no_llm: bool,
    json_output: bool,
) -> None:
    """Ingest PDFs from one or more paths into Albedo."""
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

    if json_output:
        click.echo(json.dumps(outputs, indent=2, sort_keys=True))
    else:
        click.echo(f"Ingested {len(outputs)} paper(s).")
        _emit(outputs, json_output=False)


@main.command("exhaust")
@click.argument("paper_id", required=False)
@click.option("--domain", default=None, help="Exhaust a specific domain bucket.")
@click.option("--all", "all_scope", is_flag=True, help="Exhaust all eligible papers.")
@click.option("--depth", default=3, type=click.IntRange(1, 5), show_default=True)
@click.option("--count", default=0, help="Max papers in --all or --domain mode.")
@click.option("--reprocess", is_flag=True, help="Allow reprocessing exhausted papers.")
@click.option("--no-llm", is_flag=True, help="Disable LLM exhaustion prompts.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON")
def cmd_exhaust(
    paper_id: str | None,
    domain: str | None,
    all_scope: bool,
    depth: int,
    count: int,
    reprocess: bool,
    no_llm: bool,
    json_output: bool,
) -> None:
    """Generate structured exhaust output for one or many papers."""
    if not paper_id and not domain and not all_scope:
        raise click.ClickException("Provide paper_id, --domain, or --all.")

    cfg, llm = _load_skill_config(no_llm)
    outputs = exhaust_skill.run_exhaust(
        target=paper_id,
        config=cfg,
        llm=llm,
        depth=depth,
        domain=domain,
        all_scope=all_scope,
        count=count,
        reprocess=reprocess,
    )
    if json_output:
        click.echo(json.dumps(outputs, indent=2, sort_keys=True))
    else:
        click.echo(f"Exhausted {len(outputs)} paper(s).")
        _emit(outputs, json_output=False)


@main.command("connect")
@click.option("--within", required=False, help="Domain to run within-domain pass.")
@click.option("--cross", nargs=2, metavar="D1 D2", required=False, help="Domain pair for cross-domain pass.")
@click.option("--paper", "paper_id", help="Single paper id sweep.")
@click.option("--all", "all_scope", is_flag=True, help="Run all candidate pairs.")
@click.option("--no-llm", is_flag=True, help="Disable LLM pair assessment.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON")
def cmd_connect(
    within: str | None,
    cross: tuple[str, str] | None,
    paper_id: str | None,
    all_scope: bool,
    no_llm: bool,
    json_output: bool,
) -> None:
    """Discover connection candidates between paper pairs."""
    if not any([within, cross, paper_id, all_scope]):
        raise click.ClickException("Provide --within, --cross, --paper, or --all.")

    if sum(bool(x) for x in [within, cross, paper_id, all_scope]) != 1:
        raise click.ClickException("Use exactly one mode: --within, --cross, --paper, or --all.")

    cfg, llm = _load_skill_config(no_llm)
    outputs = connect_skill.connect(
        config=cfg,
        llm=llm,
        within=within,
        cross=cross,
        paper_id=paper_id,
        all_scope=all_scope,
    )
    if json_output:
        click.echo(json.dumps(outputs, indent=2, sort_keys=True))
    else:
        click.echo(f"Generated {len(outputs)} connection(s).")
        _emit(outputs, json_output=False)


@main.command("detect")
@click.option("--domain", default=None, help="Limit to within-domain clusters.")
@click.option("--cross", nargs=2, metavar="D1 D2", required=False, help="Limit to cross-domain pairs.")
@click.option("--cluster", "cluster", required=False, help="Force an existing hypothesis id.")
@click.option("--all", "all_scope", is_flag=True, help="Scan all connection artifacts.")
@click.option("--no-llm", is_flag=True, help="Disable LLM cluster synthesis.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON")
def cmd_detect(
    domain: str | None,
    cross: tuple[str, str] | None,
    cluster: str | None,
    all_scope: bool,
    no_llm: bool,
    json_output: bool,
) -> None:
    """Synthesize gap hypotheses from connection clusters."""
    cfg, llm = _load_skill_config(no_llm)
    outputs = detect_skill.detect(
        config=cfg,
        llm=llm,
        domain=domain,
        cross=cross,
        all_scope=all_scope,
        cluster=cluster,
    )
    if json_output:
        click.echo(json.dumps(outputs, indent=2, sort_keys=True))
    else:
        click.echo(f"Generated {len(outputs)} hypothesis cluster(s).")
        _emit(outputs, json_output=False)


@main.command("draft")
@click.argument("gap_id", required=False)
@click.option("--top", default=1, type=click.IntRange(min=1), show_default=True, help="Top N pending hypotheses.")
@click.option("--no-llm", is_flag=True, help="Disable LLM drafting")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON")
def cmd_draft(
    gap_id: str | None,
    top: int,
    no_llm: bool,
    json_output: bool,
) -> None:
    """Draft rubedo notes from hypothesis files."""
    cfg, llm = _load_skill_config(no_llm)

    paths = draft_skill.run_draft(
        gap_id=gap_id,
        top=top,
        config=cfg,
        llm=llm,
    )

    if json_output:
        click.echo(json.dumps([str(path) for path in paths], indent=2))
    else:
        for path in paths:
            click.echo(f"  - {path}")
        click.echo(f"Generated {len(paths)} draft file(s).")


def _run_python_module(module_path: Path, argv: list[str]) -> int:
    cmd = [sys.executable, str(module_path), *argv]
    result = subprocess.run(cmd, cwd=str(Path(__file__).resolve().parents[1]))
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
    module = (Path(__file__).resolve().parents[1] / "athanasor" / "scripts" / "validate.py")
    raise SystemExit(_run_python_module(module, argv[1:]))


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
    module = (Path(__file__).resolve().parents[1] / "athanasor" / "scripts" / "migrate.py")
    raise SystemExit(_run_python_module(module, argv[1:]))


if __name__ == "__main__":
    main()
