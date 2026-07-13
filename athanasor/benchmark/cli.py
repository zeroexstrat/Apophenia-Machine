from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import click

from athanasor.benchmark.artifacts import (
    EXECUTION_MANIFEST_TYPE,
    LOCK_TYPE,
    PREPARED_TYPE,
    RUN_TYPE,
    SCORE_TYPE,
    BenchmarkArtifactError,
    artifact_digest,
    atomic_write_json,
    atomic_write_text,
    ensure_outside_repository,
    read_json_artifact,
    validate_prepared,
    validate_run,
    validate_score,
)
from athanasor.benchmark.pipeline import (
    extract_pdf_record,
    extract_synthetic_record,
    fetch_https,
    fetch_sources,
    import_run,
    prepare_benchmark,
    run_fallback,
)
from athanasor.benchmark.execution import (
    RUN_IDS,
    adapt_model_responses,
    generate_baseline,
    load_execution_manifest,
    validate_execution_manifest,
)
from athanasor.benchmark.locking import (
    build_lock_manifest,
    seal_lock_tree,
    verify_lock_manifest,
)
from athanasor.benchmark.evaluation import (
    build_annotation_template,
    build_comparison,
    build_failure_analysis,
    render_public_summary,
)
from athanasor.benchmark.protocol import (
    BenchmarkProtocolError,
    load_mapping,
    validate_public_bundle,
)
from athanasor.benchmark.reporting import render_markdown
from athanasor.benchmark.scoring import score_run


@contextmanager
def _cli_errors() -> Iterator[None]:
    try:
        yield
    except click.ClickException:
        raise
    except (BenchmarkArtifactError, BenchmarkProtocolError, OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from None


def _emit(payload: dict[str, Any], json_output: bool) -> None:
    if json_output:
        click.echo(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        return
    click.echo(" ".join(f"{key}={value}" for key, value in payload.items()))


@click.group("benchmark")
def benchmark_cli() -> None:
    """Validate, run, lock, score, and report frozen benchmarks."""


def _parse_named_paths(values: tuple[str, ...], *, label: str) -> dict[str, Path]:
    parsed: dict[str, Path] = {}
    for value in values:
        name, separator, raw_path = value.partition("=")
        if not separator or not name or not raw_path:
            raise BenchmarkArtifactError(f"{label}: expected RUN_ID=PATH")
        if name in parsed:
            raise BenchmarkArtifactError(f"{label}: duplicate run ID {name}")
        parsed[name] = Path(raw_path)
    return parsed


def _read_response_directory(path: Path) -> dict[str, dict[str, Any]]:
    root = Path(path)
    responses: dict[str, dict[str, Any]] = {}
    for response_path in sorted(root.glob("*.json")):
        payload = read_json_artifact(response_path)
        pair_identifier = payload.get("pair_id")
        if not isinstance(pair_identifier, str) or not pair_identifier:
            raise BenchmarkArtifactError(f"{response_path.name}: missing pair_id")
        if pair_identifier in responses:
            raise BenchmarkArtifactError(f"response directory: duplicate pair_id {pair_identifier}")
        responses[pair_identifier] = payload
    if not responses:
        raise BenchmarkArtifactError("response directory: no JSON responses found")
    return responses


@benchmark_cli.command("validate")
@click.option("--benchmark-root", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--artifact", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def cmd_validate(benchmark_root: Path, artifact: Path | None, json_output: bool) -> None:
    """Validate the public freeze and an optional public P6 artifact."""
    with _cli_errors():
        errors = list(validate_public_bundle(benchmark_root))
        artifact_type: str | None = None
        if artifact is not None:
            payload = (
                load_mapping(artifact)
                if artifact.suffix.casefold() in {".yaml", ".yml"}
                else read_json_artifact(artifact)
            )
            artifact_type = payload.get("artifact_type")
            validator = {
                PREPARED_TYPE: validate_prepared,
                RUN_TYPE: validate_run,
                SCORE_TYPE: validate_score,
                EXECUTION_MANIFEST_TYPE: lambda value: validate_execution_manifest(
                    value, benchmark_root
                ),
            }.get(artifact_type)
            if validator is None:
                raise BenchmarkArtifactError(
                    f"/artifact_type: unsupported public P6 artifact {artifact_type}"
                )
            errors.extend(validator(payload))
        if errors:
            raise BenchmarkArtifactError("; ".join(sorted(errors)))
        summary: dict[str, Any] = {"status": "valid", "benchmark_id": "operations-decision-support-v1"}
        if artifact_type is not None:
            summary["artifact_type"] = artifact_type
        _emit(summary, json_output)


@benchmark_cli.command("baseline")
@click.option("--prepared", "prepared_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--execution-manifest", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--run-id", type=click.Choice(list(RUN_IDS[1:])), required=True)
@click.option("--output", type=click.Path(path_type=Path), required=True)
@click.option("--repo-root", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--force", is_flag=True, help="Replace an existing baseline run.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def cmd_baseline(
    prepared_path: Path,
    execution_manifest: Path,
    run_id: str,
    output: Path,
    repo_root: Path,
    force: bool,
    json_output: bool,
) -> None:
    """Generate one preregistered deterministic baseline without gold access."""
    with _cli_errors():
        destination = ensure_outside_repository(output, repo_root, label="baseline output")
        prepared = read_json_artifact(prepared_path, artifact_type=PREPARED_TYPE)
        manifest = load_execution_manifest(execution_manifest)
        run = generate_baseline(prepared, manifest, run_id)
        digest = atomic_write_json(destination, run, force=force)
        _emit(
            {
                "status": "locked",
                "run_id": run_id,
                "artifact_sha256": digest,
                "pair_count": len(run["results"]),
            },
            json_output,
        )


@benchmark_cli.command("adapt")
@click.option("--prepared", "prepared_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--execution-manifest", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--responses-dir", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--provenance", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--output", type=click.Path(path_type=Path), required=True)
@click.option("--repo-root", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--force", is_flag=True, help="Replace an existing adapted model run.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def cmd_adapt(
    prepared_path: Path,
    execution_manifest: Path,
    responses_dir: Path,
    provenance: Path,
    output: Path,
    repo_root: Path,
    force: bool,
    json_output: bool,
) -> None:
    """Adapt complete blinded model responses into one locked model run."""
    with _cli_errors():
        response_root = ensure_outside_repository(
            responses_dir, repo_root, label="model response directory"
        )
        destination = ensure_outside_repository(output, repo_root, label="model run output")
        prepared = read_json_artifact(prepared_path, artifact_type=PREPARED_TYPE)
        manifest = load_execution_manifest(execution_manifest)
        run = adapt_model_responses(
            prepared,
            manifest,
            _read_response_directory(response_root),
            read_json_artifact(
                ensure_outside_repository(provenance, repo_root, label="model provenance")
            ),
        )
        digest = atomic_write_json(destination, run, force=force)
        _emit(
            {
                "status": "locked",
                "run_id": RUN_IDS[0],
                "artifact_sha256": digest,
                "pair_count": len(run["results"]),
            },
            json_output,
        )


@benchmark_cli.command("lock")
@click.option("--benchmark-root", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--prepared", "prepared_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--execution-manifest", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--run", "run_values", multiple=True, required=True, help="Repeat exactly seven times as RUN_ID=PATH.")
@click.option("--output", type=click.Path(path_type=Path), required=True)
@click.option("--repo-root", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--implementation-git-sha", required=True)
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def cmd_lock(
    benchmark_root: Path,
    prepared_path: Path,
    execution_manifest: Path,
    run_values: tuple[str, ...],
    output: Path,
    repo_root: Path,
    implementation_git_sha: str,
    json_output: bool,
) -> None:
    """Build, seal, and independently verify the exact seven-run lock."""
    with _cli_errors():
        destination = ensure_outside_repository(output, repo_root, label="lock manifest output")
        if destination.name != "lock-manifest.json":
            raise BenchmarkArtifactError("lock output must be named lock-manifest.json")
        if destination.exists():
            raise BenchmarkArtifactError("destination already exists: lock-manifest.json")
        run_paths = _parse_named_paths(run_values, label="run")
        manifest = load_execution_manifest(execution_manifest)
        lock = build_lock_manifest(
            prepared_path,
            run_paths,
            manifest,
            private_root=destination.parent,
            benchmark_root=benchmark_root,
            implementation_git_sha=implementation_git_sha,
        )
        digest = atomic_write_json(destination, lock)
        preseal_errors = verify_lock_manifest(
            lock,
            private_root=destination.parent,
            benchmark_root=benchmark_root,
            expected_git_sha=implementation_git_sha,
            require_sealed=False,
        )
        if preseal_errors:
            raise BenchmarkArtifactError("pre-seal lock verification failed: " + "; ".join(preseal_errors))
        seal_lock_tree(destination.parent)
        sealed_errors = verify_lock_manifest(
            lock,
            private_root=destination.parent,
            benchmark_root=benchmark_root,
            expected_git_sha=implementation_git_sha,
        )
        if sealed_errors:
            raise BenchmarkArtifactError("sealed lock verification failed: " + "; ".join(sealed_errors))
        _emit(
            {"status": "locked", "artifact_sha256": digest, "run_count": len(lock["runs"])},
            json_output,
        )


@benchmark_cli.command("fetch")
@click.option("--benchmark-root", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--source-manifest", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--source-dir", type=click.Path(path_type=Path), required=True)
@click.option("--repo-root", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--force", is_flag=True, help="Replace an existing complete destination.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def cmd_fetch(
    benchmark_root: Path,
    source_manifest: Path | None,
    source_dir: Path,
    repo_root: Path,
    force: bool,
    json_output: bool,
) -> None:
    """Fetch and verify exact source bytes outside the repository."""
    with _cli_errors():
        errors = validate_public_bundle(benchmark_root)
        if errors:
            raise BenchmarkArtifactError("invalid public benchmark: " + "; ".join(sorted(errors)))
        destination = ensure_outside_repository(source_dir, repo_root, label="source directory")
        manifest = load_mapping(source_manifest or benchmark_root / "sources.yaml")
        result = fetch_sources(manifest, destination, fetcher=fetch_https, force=force)
        _emit({"status": "fetched", **result}, json_output)


@benchmark_cli.command("prepare")
@click.option("--benchmark-root", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--source-manifest", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--source-dir", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--output", type=click.Path(path_type=Path), required=True)
@click.option("--repo-root", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--force", is_flag=True, help="Replace an existing prepared artifact.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def cmd_prepare(
    benchmark_root: Path,
    source_manifest: Path | None,
    source_dir: Path,
    output: Path,
    repo_root: Path,
    force: bool,
    json_output: bool,
) -> None:
    """Build canonical blinded packets from verified source bytes."""
    with _cli_errors():
        source_root = ensure_outside_repository(source_dir, repo_root, label="source directory")
        destination = ensure_outside_repository(output, repo_root, label="prepared output")
        manifest = load_mapping(source_manifest or benchmark_root / "sources.yaml")
        sources = manifest.get("sources")
        synthetic = isinstance(sources, list) and bool(sources) and all(
            isinstance(source, dict) and source.get("synthetic") is True for source in sources
        )
        prepared = prepare_benchmark(
            benchmark_root,
            manifest,
            source_root,
            destination,
            extractor=extract_synthetic_record if synthetic else extract_pdf_record,
            force=force,
        )
        _emit(
            {
                "status": "prepared",
                "artifact_sha256": artifact_digest(prepared),
                "pair_count": len(prepared["packets"]),
                "synthetic": prepared["synthetic"],
            },
            json_output,
        )


@benchmark_cli.command("run")
@click.option("--prepared", "prepared_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--output", type=click.Path(path_type=Path), required=True)
@click.option("--backend", type=click.Choice(["fallback"]), default="fallback", show_default=True)
@click.option("--responses", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--seed", type=int, default=5607, show_default=True)
@click.option("--force", is_flag=True, help="Replace an existing locked run artifact.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def cmd_run(
    prepared_path: Path,
    output: Path,
    backend: str,
    responses: Path | None,
    seed: int,
    force: bool,
    json_output: bool,
) -> None:
    """Lock a deterministic fallback run or complete imported responses."""
    with _cli_errors():
        prepared = read_json_artifact(prepared_path, artifact_type=PREPARED_TYPE)
        if responses is None:
            if backend != "fallback":
                raise BenchmarkArtifactError("only the deterministic fallback backend is available")
            run = run_fallback(prepared, seed=seed)
        else:
            run = import_run(prepared, read_json_artifact(responses))
        digest = atomic_write_json(output, run, force=force)
        _emit(
            {
                "status": "locked",
                "artifact_sha256": digest,
                "pair_count": len(run["results"]),
                "backend": run["backend"]["name"],
                "synthetic": run["synthetic"],
            },
            json_output,
        )


@benchmark_cli.command("score")
@click.option("--benchmark-root", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--run", "run_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--gold", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--output", type=click.Path(path_type=Path), required=True)
@click.option("--repo-root", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--annotations", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--lock", "lock_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--execution-manifest", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--expected-git-sha")
@click.option("--force", is_flag=True, help="Replace an existing score artifact.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def cmd_score(
    benchmark_root: Path,
    run_path: Path,
    gold: Path,
    output: Path,
    repo_root: Path,
    annotations: Path | None,
    lock_path: Path | None,
    execution_manifest: Path | None,
    expected_git_sha: str | None,
    force: bool,
    json_output: bool,
) -> None:
    """Score one already-locked run against explicit external gold."""
    with _cli_errors():
        gold_path = ensure_outside_repository(gold, repo_root, label="private gold")
        annotation_path = (
            ensure_outside_repository(annotations, repo_root, label="human annotations")
            if annotations is not None
            else None
        )
        destination = ensure_outside_repository(output, repo_root, label="score output")
        run = read_json_artifact(run_path, artifact_type=RUN_TYPE)
        gold_payload = read_json_artifact(gold_path)
        annotation_payload = read_json_artifact(annotation_path) if annotation_path else None
        lock_payload = None
        lock_root = None
        if lock_path is not None:
            private_lock_path = ensure_outside_repository(
                lock_path, repo_root, label="private lock manifest"
            )
            lock_payload = read_json_artifact(private_lock_path, artifact_type=LOCK_TYPE)
            lock_root = private_lock_path.parent
        execution_payload = (
            load_execution_manifest(execution_manifest)
            if execution_manifest is not None
            else None
        )
        score = score_run(
            benchmark_root,
            run,
            gold_payload,
            annotations=annotation_payload,
            verified_lock=lock_payload,
            lock_private_root=lock_root,
            execution_manifest=execution_payload,
            expected_git_sha=expected_git_sha,
        )
        digest = atomic_write_json(destination, score, force=force)
        _emit(
            {
                "status": "scored",
                "artifact_sha256": digest,
                "metric_count": len(score["metrics"]),
                "synthetic": score["synthetic"],
            },
            json_output,
        )


@benchmark_cli.command("annotations")
@click.option("--benchmark-root", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--run", "run_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--lock", "lock_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--output", type=click.Path(path_type=Path), required=True)
@click.option("--repo-root", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--expected-git-sha")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def cmd_annotations(
    benchmark_root: Path,
    run_path: Path,
    lock_path: Path,
    output: Path,
    repo_root: Path,
    expected_git_sha: str | None,
    json_output: bool,
) -> None:
    """Create the explicit Rafael-authority annotation template after lock."""
    with _cli_errors():
        private_lock_path = ensure_outside_repository(
            lock_path, repo_root, label="private lock manifest"
        )
        destination = ensure_outside_repository(output, repo_root, label="annotation output")
        lock = read_json_artifact(private_lock_path, artifact_type=LOCK_TYPE)
        lock_errors = verify_lock_manifest(
            lock,
            private_root=private_lock_path.parent,
            benchmark_root=benchmark_root,
            expected_git_sha=expected_git_sha,
        )
        if lock_errors:
            raise BenchmarkArtifactError("invalid verified P7 lock: " + "; ".join(lock_errors))
        run = read_json_artifact(run_path, artifact_type=RUN_TYPE)
        template = build_annotation_template(run, lock)
        digest = atomic_write_json(destination, template)
        _emit(
            {
                "status": "pending_review",
                "artifact_sha256": digest,
                "item_count": len(template["items"]),
            },
            json_output,
        )


@benchmark_cli.command("compare")
@click.option("--lock", "lock_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--score", "score_values", multiple=True, required=True, help="Repeat exactly seven times as RUN_ID=PATH.")
@click.option("--output", type=click.Path(path_type=Path), required=True)
@click.option("--repo-root", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--run", "run_values", multiple=True, help="For failure analysis, repeat seven times as RUN_ID=PATH.")
@click.option("--gold", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--annotations", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--failure-output", type=click.Path(path_type=Path))
@click.option("--public-summary-output", type=click.Path(path_type=Path))
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def cmd_compare(
    lock_path: Path,
    score_values: tuple[str, ...],
    output: Path,
    repo_root: Path,
    run_values: tuple[str, ...],
    gold: Path | None,
    annotations: Path | None,
    failure_output: Path | None,
    public_summary_output: Path | None,
    json_output: bool,
) -> None:
    """Compare seven lock-bound scores and optionally render post-gold failure analysis."""
    with _cli_errors():
        private_lock_path = ensure_outside_repository(
            lock_path, repo_root, label="private lock manifest"
        )
        destination = ensure_outside_repository(output, repo_root, label="comparison output")
        lock = read_json_artifact(private_lock_path, artifact_type=LOCK_TYPE)
        score_paths = _parse_named_paths(score_values, label="score")
        scores = {
            run_id: read_json_artifact(
                ensure_outside_repository(path, repo_root, label=f"score {run_id}"),
                artifact_type=SCORE_TYPE,
            )
            for run_id, path in score_paths.items()
        }
        comparison = build_comparison(lock, scores)
        failure = None
        summary = None
        failure_destination = None
        summary_destination = None
        optional = (run_values, gold, annotations, failure_output, public_summary_output)
        if any(value for value in optional):
            if not run_values or gold is None or annotations is None or failure_output is None or public_summary_output is None:
                raise BenchmarkArtifactError(
                    "failure analysis requires --run, --gold, --annotations, --failure-output, and --public-summary-output"
                )
            run_paths = _parse_named_paths(run_values, label="run")
            runs = {
                run_id: read_json_artifact(
                    ensure_outside_repository(path, repo_root, label=f"run {run_id}"),
                    artifact_type=RUN_TYPE,
                )
                for run_id, path in run_paths.items()
            }
            gold_path = ensure_outside_repository(gold, repo_root, label="private gold")
            annotation_path = ensure_outside_repository(
                annotations, repo_root, label="human annotations"
            )
            failure_destination = ensure_outside_repository(
                failure_output, repo_root, label="failure analysis output"
            )
            summary_destination = ensure_outside_repository(
                public_summary_output, repo_root, label="public summary output"
            )
            failure = build_failure_analysis(
                lock,
                runs,
                scores,
                read_json_artifact(gold_path),
                read_json_artifact(annotation_path),
            )
            summary = render_public_summary(comparison, failure)
        comparison_digest = atomic_write_json(destination, comparison)
        if failure is not None and failure_destination is not None:
            atomic_write_json(failure_destination, failure)
        if summary is not None and summary_destination is not None:
            atomic_write_text(summary_destination, summary)
        _emit(
            {
                "status": "compared",
                "artifact_sha256": comparison_digest,
                "run_count": len(comparison["runs"]),
            },
            json_output,
        )


@benchmark_cli.command("report")
@click.option("--score", "score_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--output", type=click.Path(path_type=Path), required=True)
@click.option("--force", is_flag=True, help="Replace an existing report.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def cmd_report(score_path: Path, output: Path, force: bool, json_output: bool) -> None:
    """Render a provenance-first Markdown report without recomputing metrics."""
    with _cli_errors():
        score = read_json_artifact(score_path, artifact_type=SCORE_TYPE)
        report = render_markdown(score)
        digest = atomic_write_text(output, report, force=force)
        _emit(
            {
                "status": "reported",
                "artifact_sha256": digest,
                "metric_count": len(score["metrics"]),
                "synthetic": score["synthetic"],
            },
            json_output,
        )
