"""Fail-closed checks for authoritative session worktree locations."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Iterable


def default_temporary_roots() -> tuple[Path, ...]:
    """Return resolved temporary roots that may be purged by the platform."""
    candidates = (Path("/tmp"), Path("/private/tmp"), Path("/var/tmp"), Path(tempfile.gettempdir()))
    roots: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def temporary_root_for(path: Path, *, roots: Iterable[Path] | None = None) -> Path | None:
    """Return the matching temporary root after resolving path aliases."""
    resolved_path = path.resolve()
    candidates = default_temporary_roots() if roots is None else tuple(roots)
    for candidate in candidates:
        resolved_root = candidate.resolve()
        if resolved_path == resolved_root or resolved_root in resolved_path.parents:
            return resolved_root
    return None


def assert_durable_worktree(path: Path, *, roots: Iterable[Path] | None = None) -> Path:
    """Return the resolved path or reject an authoritative temporary worktree."""
    resolved_path = path.resolve()
    temporary_root = temporary_root_for(resolved_path, roots=roots)
    if temporary_root is not None:
        raise RuntimeError(
            "refusing authoritative session in temporary storage: "
            f"worktree {resolved_path} is beneath {temporary_root}. "
            "Move or clone the repository to durable user storage, push an early "
            "checkpoint branch, and reserve temporary paths for disposable verification only."
        )
    return resolved_path

