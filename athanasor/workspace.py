"""Discovery and conflict-safe initialization of mutable Azoth workspaces."""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import yaml

from .resources import resource_yaml


DEFAULT_DOMAINS = (
    "physics",
    "ML",
    "philosophy",
    "neuroscience",
    "mathematics",
    "biology",
    "unclassified",
)
RUNTIME_DIRECTORIES = (
    "nigredo/inbox",
    *(f"nigredo/{domain}" for domain in DEFAULT_DOMAINS),
    "nigredo/ouroboros",
    "albedo/library",
    "albedo/exhaust",
    "citrinitas/retrieval_candidates",
    "citrinitas/within_domain",
    "citrinitas/cross_domain",
    "citrinitas/reports",
    "rubedo/hypotheses",
    "rubedo/drafts",
    "rubedo/reviews",
    "rubedo/experiments",
    "rubedo/promoted",
    "rubedo/prior_art",
    "rubedo/rejections",
    "athanasor/lapis",
    "athanasor/vigil/reports",
)


class WorkspaceConflictError(RuntimeError):
    """Raised when initialization would overwrite or reinterpret user data."""


def discover_workspace(start: Path | None = None) -> Path:
    """Resolve the active mutable workspace without consulting package paths."""
    override = os.getenv("AZOTH_PROJECT_ROOT")
    if override:
        return Path(override).expanduser().resolve()

    current = (start or Path.cwd()).expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / "azoth.config.yaml").is_file():
            return candidate
    return current


def _package_version() -> str:
    try:
        return version("azoth")
    except PackageNotFoundError:
        return "0.0.0"


def _initial_state() -> dict[str, Any]:
    return {
        "project": "Azoth / Apophenia Machine",
        "version": _package_version(),
        "pipeline": {
            "nigredo": {"total_papers_inbox": 0, "last_separatio": None},
            "albedo": {
                "total_ingested": 0,
                "total_exhausted": 0,
                "by_domain": {},
                "last_ingestion": None,
                "last_exhaustion": None,
            },
            "citrinitas": {
                "total_connections_within": 0,
                "total_connections_cross": 0,
                "last_connection_pass": None,
            },
            "rubedo": {
                "total_hypotheses": 0,
                "total_drafts": 0,
                "last_gap_detection": None,
                "last_draft_generation": None,
            },
        },
        "triage": {
            "confirmed": 0,
            "rejected": 0,
            "investigating": 0,
            "last_triage": None,
        },
        "gates": {
            "git_drift": "unchecked",
            "registry": "unchecked",
            "corpus": "unchecked",
            "coniunctio": "unchecked",
            "calcinatio": "unchecked",
            "caput_mortuum": "unchecked",
            "nigredo_redux": "unchecked",
        },
        "sessions": {"total": 0, "last_mortem": None},
        "processing": {
            "registry_total": 0,
            "status_counts": {},
            "library_records": 0,
            "exhaust_records": 0,
        },
    }


def _load_existing_config(path: Path, target: Path) -> dict[str, Any] | None:
    if path.exists() and not path.is_file():
        raise WorkspaceConflictError(f"Azoth configuration path is not a file: {path}")
    if not path.exists():
        return None
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise WorkspaceConflictError(f"Invalid Azoth configuration at {path}: {exc}") from None
    if not isinstance(payload, dict):
        raise WorkspaceConflictError(f"Invalid Azoth configuration at {path}: expected a YAML mapping")
    configured_root = payload.get("paths", {}).get("project_root") if isinstance(payload.get("paths"), dict) else None
    if configured_root and Path(str(configured_root)).expanduser().resolve() != target:
        raise WorkspaceConflictError(
            f"Azoth configuration at {path} points to a different workspace: {configured_root}"
        )
    return payload


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def initialize_workspace(target: Path) -> Path:
    """Create or repair an empty Azoth workspace without overwriting user files."""
    root = target.expanduser().resolve()
    if root.exists() and not root.is_dir():
        raise WorkspaceConflictError(f"Workspace target is not a directory: {root}")

    config_path = root / "azoth.config.yaml"
    if root.exists() and any(root.iterdir()) and not config_path.exists():
        raise WorkspaceConflictError(
            f"Refusing to initialize non-empty directory without azoth.config.yaml: {root}"
        )

    existing_config = _load_existing_config(config_path, root) if root.exists() else None
    registry_path = root / "albedo" / "registry.jsonl"
    state_path = root / "athanasor" / "lapis" / "state.json"
    for path, label in ((registry_path, "registry"), (state_path, "state")):
        if path.exists() and not path.is_file():
            raise WorkspaceConflictError(f"Azoth {label} path is not a file: {path}")

    config = deepcopy(existing_config or resource_yaml("azoth.config.yaml"))
    if not isinstance(config, dict):
        raise WorkspaceConflictError("Bundled Azoth configuration is invalid")
    paths = config.setdefault("paths", {})
    if not isinstance(paths, dict):
        raise WorkspaceConflictError(f"Invalid Azoth configuration at {config_path}: paths must be a mapping")
    paths["project_root"] = str(root)
    domains = config.get("domains") if isinstance(config.get("domains"), list) else list(DEFAULT_DOMAINS)

    directories = set(RUNTIME_DIRECTORIES)
    directories.update(f"nigredo/{str(domain)}" for domain in domains if str(domain).strip())
    for relative in sorted(directories):
        path = root / relative
        if path.exists() and not path.is_dir():
            raise WorkspaceConflictError(f"Workspace directory path is occupied by a file: {path}")

    root.mkdir(parents=True, exist_ok=True)
    for relative in sorted(directories):
        (root / relative).mkdir(parents=True, exist_ok=True)

    if existing_config is None:
        _atomic_write(config_path, yaml.safe_dump(config, sort_keys=False))
    if not registry_path.exists():
        _atomic_write(registry_path, "")
    if not state_path.exists():
        _atomic_write(state_path, json.dumps(_initial_state(), indent=2) + "\n")
    return root
