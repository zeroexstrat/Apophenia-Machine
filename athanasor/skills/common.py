"""Shared helpers for Azoth skills."""

from __future__ import annotations

import hashlib
import json
import re
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def slugify(value: str, fallback: str = "item") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower())
    slug = slug.strip("-")
    slug = re.sub(r"-{2,}", "-", slug)[:70]
    return slug or fallback


def is_specific_text(value: Any) -> bool:
    """Return true for a nonblank trace that is not a known placeholder."""
    text = str(value or "").strip()
    return bool(text) and text.casefold() not in {
        "unspecified",
        "unknown",
        "n/a",
        "none",
        "shared top-level tags in registry",
    }


def short_id(value: str) -> str:
    h = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
    return h


def write_yaml(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False)


def write_jsonl(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, sort_keys=True) + "\n")


def load_yaml(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_yaml_tolerant(path: Path) -> dict[str, Any] | None:
    """Load a YAML mapping, returning None for missing/corrupt/non-mapping files.

    Pipeline commands sweep whole artifact directories; one corrupted file must
    degrade to a skip, not a crash.
    """
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = yaml.safe_load(f)
    except (yaml.YAMLError, OSError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def run_vigil_check(root: Path, phase: str, skill: str) -> str:
    """Run a Vigil phase for the current repo using the active Python interpreter."""
    if os.getenv("AZOTH_SKIP_VIGIL", "").strip().lower() in {"1", "true", "on", "yes"}:
        return f"Vigil skipped for {skill} ({phase})"

    cmd = [sys.executable, "-m", "athanasor.vigil.verify", phase]
    env = os.environ.copy()
    env["AZOTH_PROJECT_ROOT"] = str(root.resolve())
    try:
        result = subprocess.run(
            cmd,
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Vigil {phase} launch failed for {skill}: {exc}") from exc
    except OSError as exc:
        raise RuntimeError(f"Vigil {phase} runtime error for {skill}: {exc}") from exc

    output = (result.stderr or result.stdout or "").strip()
    if result.returncode != 0:
        command = " ".join(cmd)
        raise RuntimeError(
            f"Vigil {phase} failed for {skill} ({command}): {output or 'no details'}"
        )
    return output


def move_to_domain(src: Path, domain_root: Path, filename: str | None = None) -> Path:
    target_dir = domain_root
    ensure_dir(target_dir)
    destination = target_dir / (filename or src.name)
    stem, suffix = destination.stem, destination.suffix
    # The suffix must vary per collision: a name-derived constant would make a
    # third same-named file silently overwrite the second.
    counter = 1
    while destination.exists():
        tag = short_id(f"{stem}{suffix}:{counter}")[:6]
        destination = target_dir / f"{stem}_{tag}{suffix}"
        counter += 1
    shutil.move(str(src), destination)
    return destination
