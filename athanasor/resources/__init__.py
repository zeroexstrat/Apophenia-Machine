"""Read-only resources distributed with every Azoth installation."""

from __future__ import annotations

from contextlib import AbstractContextManager
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any

import yaml


RESOURCE_NAMES = (
    "SCHEMA.yaml",
    "EXHAUST_SCHEMA.yaml",
    "RETRIEVAL_SCHEMA.yaml",
    "CONNECT_SCHEMA.yaml",
    "DETECT_SCHEMA.yaml",
    "azoth.config.yaml",
    "vigil/gates.yaml",
)
_RESOURCE_SET = frozenset(RESOURCE_NAMES)


def _resource(name: str):
    if name not in _RESOURCE_SET:
        raise KeyError(f"Unknown Azoth resource: {name}")
    return files(__package__).joinpath(name)


def resource_text(name: str) -> str:
    """Return one allowlisted UTF-8 resource as text."""
    return _resource(name).read_text(encoding="utf-8")


def resource_yaml(name: str) -> Any:
    """Parse one allowlisted YAML resource."""
    return yaml.safe_load(resource_text(name))


def resource_path(name: str) -> AbstractContextManager[Path]:
    """Materialize one allowlisted resource for path-oriented consumers."""
    return as_file(_resource(name))
