from __future__ import annotations

import hashlib
import platform
import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from athanasor.benchmark.artifacts import (
    LOCK_TYPE,
    PREPARED_TYPE,
    RUN_TYPE,
    BenchmarkArtifactError,
    artifact_digest,
    read_json_artifact,
    validate_prepared,
    validate_run,
)
from athanasor.benchmark.execution import (
    RUN_IDS,
    execution_manifest_digest,
    load_execution_manifest,
    validate_execution_manifest,
)
from athanasor.benchmark.protocol import BENCHMARK_ID


_SHA256 = re.compile(r"[0-9a-f]{64}")
_GIT_SHA = re.compile(r"[0-9a-f]{40}")
_LOCK_FIELDS = {
    "schema_version",
    "artifact_type",
    "benchmark_id",
    "status",
    "execution_manifest_sha256",
    "implementation_git_sha",
    "runtime",
    "prepared",
    "runs",
    "seal",
    "contamination_attestation",
}


def _package_version() -> str:
    try:
        return version("azoth")
    except PackageNotFoundError:
        return "unknown"


def _byte_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside_file(path: Path, root: Path, *, label: str) -> Path:
    resolved_root = Path(root).resolve()
    candidate = Path(path)
    if candidate.is_symlink():
        raise BenchmarkArtifactError(f"{label}: symlinks are forbidden")
    resolved = candidate.resolve()
    if not resolved.is_file() or resolved_root not in resolved.parents:
        raise BenchmarkArtifactError(f"{label}: expected file inside private lock root")
    return resolved


def _relative_file(path: Path, root: Path, *, label: str) -> Path:
    relative = Path(path)
    if relative.is_absolute() or ".." in relative.parts:
        raise BenchmarkArtifactError(f"{label} relative_path: traversal is forbidden")
    return _inside_file(Path(root) / relative, Path(root), label=label)


def _file_record(path: Path, root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "byte_count": path.stat().st_size,
        "sha256": _byte_sha256(path),
        "artifact_sha256": artifact_digest(payload),
    }


def _forbidden_tree_paths(
    root: Path, forbidden_names: list[str], *, allowed_files: set[Path] | None = None
) -> list[str]:
    findings: list[str] = []
    allowed = {path.resolve() for path in (allowed_files or set())}
    lowered_tokens = [token.casefold() for token in forbidden_names]
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            findings.append(f"{path.relative_to(root)}: symlink")
            continue
        if path.is_file() and path.resolve() in allowed:
            continue
        for part in path.relative_to(root).parts:
            lowered = part.casefold()
            if any(token in lowered for token in lowered_tokens):
                findings.append(f"{path.relative_to(root)}: forbidden lock-tree name")
                break
    return findings


def build_lock_manifest(
    prepared_path: Path,
    run_paths: dict[str, Path],
    execution_manifest: dict[str, Any],
    *,
    private_root: Path,
    benchmark_root: Path,
    implementation_git_sha: str,
) -> dict[str, Any]:
    root = Path(private_root).resolve()
    if not root.is_dir() or root.is_symlink():
        raise BenchmarkArtifactError("private lock root: expected real directory")
    if set(run_paths) != set(RUN_IDS):
        raise BenchmarkArtifactError("lock requires exact seven run IDs")
    if not _GIT_SHA.fullmatch(implementation_git_sha):
        raise BenchmarkArtifactError("implementation Git SHA: expected full lowercase commit SHA")
    manifest_errors = validate_execution_manifest(execution_manifest, Path(benchmark_root))
    if manifest_errors:
        raise BenchmarkArtifactError("invalid execution manifest: " + "; ".join(manifest_errors))
    manifest_digest = execution_manifest_digest(execution_manifest, Path(benchmark_root))
    prepared_file = _inside_file(prepared_path, root, label="prepared artifact")
    resolved_run_files = {
        run_id: _inside_file(run_paths[run_id], root, label=f"run {run_id}")
        for run_id in RUN_IDS
    }
    forbidden_names = list(execution_manifest["lock_contract"]["forbid_names"])
    findings = _forbidden_tree_paths(
        root,
        forbidden_names,
        allowed_files={prepared_file, *resolved_run_files.values()},
    )
    if findings:
        raise BenchmarkArtifactError(findings[0])

    prepared = read_json_artifact(prepared_file, artifact_type=PREPARED_TYPE)
    prepared_errors = validate_prepared(prepared)
    if prepared_errors:
        raise BenchmarkArtifactError("invalid prepared artifact: " + "; ".join(prepared_errors))
    prepared_digest = artifact_digest(prepared)

    run_records: list[dict[str, Any]] = []
    for run_id in RUN_IDS:
        run_file = resolved_run_files[run_id]
        run = read_json_artifact(run_file, artifact_type=RUN_TYPE)
        run_errors = validate_run(run)
        if run_errors:
            raise BenchmarkArtifactError(f"invalid run {run_id}: " + "; ".join(run_errors))
        if run.get("prepared_sha256") != prepared_digest:
            raise BenchmarkArtifactError(f"run {run_id}: prepared digest mismatch")
        backend = run.get("backend")
        if not isinstance(backend, dict) or backend.get("run_id") != run_id:
            raise BenchmarkArtifactError(f"run {run_id}: backend run ID mismatch")
        if backend.get("execution_manifest_sha256") != manifest_digest:
            raise BenchmarkArtifactError(f"run {run_id}: execution manifest digest mismatch")
        run_records.append({"run_id": run_id, **_file_record(run_file, root, run)})

    return {
        "schema_version": 1,
        "artifact_type": LOCK_TYPE,
        "benchmark_id": BENCHMARK_ID,
        "status": "locked",
        "execution_manifest_sha256": manifest_digest,
        "implementation_git_sha": implementation_git_sha,
        "runtime": {
            "python_version": platform.python_version(),
            "azoth_version": _package_version(),
        },
        "prepared": _file_record(prepared_file, root, prepared),
        "runs": run_records,
        "seal": {
            "file_mode": "0400",
            "directory_mode": "0500",
            "parent_mode": "0700",
        },
        "contamination_attestation": {
            "forbidden_names": forbidden_names,
            "gold_fields_present": False,
            "score_or_annotation_artifacts_present": False,
        },
    }


def _record_errors(
    record: Any,
    *,
    path: str,
    root: Path,
    artifact_type: str,
    require_sealed: bool,
) -> tuple[list[str], dict[str, Any] | None, Path | None]:
    if not isinstance(record, dict):
        return [f"{path}: expected object"], None, None
    expected_fields = {"relative_path", "byte_count", "sha256", "artifact_sha256"}
    errors: list[str] = []
    if set(record) != expected_fields:
        errors.append(f"{path}: expected exact file record fields")
    try:
        file_path = _relative_file(Path(str(record.get("relative_path", ""))), root, label=path)
    except BenchmarkArtifactError as exc:
        return errors + [str(exc)], None, None
    if record.get("byte_count") != file_path.stat().st_size:
        errors.append(f"{path}/byte_count: mismatch")
    actual_sha = _byte_sha256(file_path)
    if record.get("sha256") != actual_sha:
        errors.append(f"{path}/sha256: mismatch")
    try:
        payload = read_json_artifact(file_path, artifact_type=artifact_type)
    except BenchmarkArtifactError as exc:
        errors.append(f"{path}: {exc}")
        payload = None
    if payload is not None and record.get("artifact_sha256") != artifact_digest(payload):
        errors.append(f"{path}/artifact_sha256: mismatch")
    if require_sealed and file_path.stat().st_mode & 0o777 != 0o400:
        errors.append(f"{path}/mode: expected 0400")
    return errors, payload, file_path


def verify_lock_manifest(
    payload: Any,
    *,
    private_root: Path,
    benchmark_root: Path,
    expected_git_sha: str | None = None,
    require_sealed: bool = True,
) -> list[str]:
    if not isinstance(payload, dict):
        return ["/: expected lock manifest object"]
    root = Path(private_root).resolve()
    errors: list[str] = []
    for field in sorted(set(payload) - _LOCK_FIELDS):
        errors.append(f"/{field}: unexpected field")
    expected_scalars = {
        "schema_version": 1,
        "artifact_type": LOCK_TYPE,
        "benchmark_id": BENCHMARK_ID,
        "status": "locked",
    }
    for field, expected in expected_scalars.items():
        if payload.get(field) != expected:
            errors.append(f"/{field}: expected {expected!r}")
    git_sha = payload.get("implementation_git_sha")
    if not isinstance(git_sha, str) or not _GIT_SHA.fullmatch(git_sha):
        errors.append("/implementation_git_sha: expected full lowercase commit SHA")
    if expected_git_sha is not None and git_sha != expected_git_sha:
        errors.append("/implementation_git_sha: does not match expected Git SHA")

    try:
        execution_manifest = load_execution_manifest(Path(benchmark_root) / "execution-manifest.yaml")
        manifest_errors = validate_execution_manifest(execution_manifest, Path(benchmark_root))
        errors.extend(f"/execution_manifest{error}" for error in manifest_errors)
        expected_manifest_digest = execution_manifest_digest(execution_manifest, Path(benchmark_root))
    except (BenchmarkArtifactError, OSError, ValueError) as exc:
        errors.append(f"/execution_manifest: {exc}")
        execution_manifest = {}
        expected_manifest_digest = ""
    if payload.get("execution_manifest_sha256") != expected_manifest_digest:
        errors.append("/execution_manifest_sha256: mismatch")

    prepared_errors, prepared, prepared_file = _record_errors(
        payload.get("prepared"),
        path="/prepared",
        root=root,
        artifact_type=PREPARED_TYPE,
        require_sealed=require_sealed,
    )
    errors.extend(prepared_errors)
    prepared_digest = artifact_digest(prepared) if isinstance(prepared, dict) else None

    runs = payload.get("runs")
    actual_run_ids = (
        [row.get("run_id") for row in runs if isinstance(row, dict)]
        if isinstance(runs, list)
        else []
    )
    if actual_run_ids != list(RUN_IDS):
        errors.append("/runs: expected exact canonical run order")
    run_files: set[Path] = set()
    if not isinstance(runs, list) or len(runs) != len(RUN_IDS):
        errors.append("/runs: expected exact seven run records")
    else:
        for index, record in enumerate(runs):
            if not isinstance(record, dict):
                errors.append(f"/runs/{index}: expected object")
                continue
            run_id = record.get("run_id")
            file_record = {key: value for key, value in record.items() if key != "run_id"}
            row_errors, run, run_file = _record_errors(
                file_record,
                path=f"/runs/{index}",
                root=root,
                artifact_type=RUN_TYPE,
                require_sealed=require_sealed,
            )
            errors.extend(row_errors)
            if run_file is not None:
                run_files.add(run_file)
            if isinstance(run, dict):
                run_errors = validate_run(run)
                errors.extend(f"/runs/{index}{error}" for error in run_errors)
                if prepared_digest is not None and run.get("prepared_sha256") != prepared_digest:
                    errors.append(f"/runs/{index}/prepared_sha256: mismatch")
                backend = run.get("backend")
                if not isinstance(backend, dict) or backend.get("run_id") != run_id:
                    errors.append(f"/runs/{index}/backend/run_id: mismatch")
                if not isinstance(backend, dict) or backend.get("execution_manifest_sha256") != expected_manifest_digest:
                    errors.append(f"/runs/{index}/backend/execution_manifest_sha256: mismatch")

    forbidden = (
        execution_manifest.get("lock_contract", {}).get("forbid_names", [])
        if isinstance(execution_manifest, dict)
        else []
    )
    allowed_files = run_files | ({prepared_file} if prepared_file is not None else set())
    lock_path = root / "lock-manifest.json"
    if lock_path.is_file():
        allowed_files.add(lock_path.resolve())
    errors.extend(
        _forbidden_tree_paths(root, list(forbidden), allowed_files=allowed_files)
    )
    actual_files = {path.resolve() for path in root.rglob("*") if path.is_file()}
    for extra in sorted(actual_files - allowed_files):
        errors.append(f"/{extra.relative_to(root)}: undeclared lock-tree file")

    if require_sealed:
        if root.stat().st_mode & 0o777 != 0o500:
            errors.append("/seal/directory_mode: lock root expected 0500")
        if root.parent.stat().st_mode & 0o777 != 0o700:
            errors.append("/seal/parent_mode: lock parent expected 0700")
        for directory in (path for path in root.rglob("*") if path.is_dir()):
            if directory.stat().st_mode & 0o777 != 0o500:
                errors.append(f"/{directory.relative_to(root)}/mode: expected 0500")
        if lock_path.is_file() and lock_path.stat().st_mode & 0o777 != 0o400:
            errors.append("/lock-manifest.json/mode: expected 0400")
    return sorted(set(errors))


def seal_lock_tree(path: Path) -> None:
    root = Path(path).resolve()
    if not root.is_dir() or root.is_symlink():
        raise BenchmarkArtifactError("private lock root: expected real directory")
    root.parent.chmod(0o700)
    for candidate in root.rglob("*"):
        if candidate.is_symlink():
            raise BenchmarkArtifactError(f"cannot seal symlink {candidate.relative_to(root)}")
    for file_path in (candidate for candidate in root.rglob("*") if candidate.is_file()):
        file_path.chmod(0o400)
    directories = sorted(
        (candidate for candidate in root.rglob("*") if candidate.is_dir()),
        key=lambda candidate: len(candidate.parts),
        reverse=True,
    )
    for directory in directories:
        directory.chmod(0o500)
    root.chmod(0o500)
