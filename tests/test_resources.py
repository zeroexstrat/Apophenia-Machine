"""Immutable package-resource contracts."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from athanasor.resources import RESOURCE_NAMES, resource_path, resource_text, resource_yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTHORING_PATHS = {
    "SCHEMA.yaml": REPO_ROOT / "SCHEMA.yaml",
    "EXHAUST_SCHEMA.yaml": REPO_ROOT / "EXHAUST_SCHEMA.yaml",
    "RETRIEVAL_SCHEMA.yaml": REPO_ROOT / "RETRIEVAL_SCHEMA.yaml",
    "CONNECT_SCHEMA.yaml": REPO_ROOT / "CONNECT_SCHEMA.yaml",
    "DETECT_SCHEMA.yaml": REPO_ROOT / "DETECT_SCHEMA.yaml",
    "azoth.config.yaml": REPO_ROOT / "azoth.config.yaml",
    "vigil/gates.yaml": REPO_ROOT / "athanasor" / "vigil" / "gates.yaml",
}


def test_declared_resources_are_complete_and_parseable() -> None:
    assert set(RESOURCE_NAMES) == set(AUTHORING_PATHS)
    for name in RESOURCE_NAMES:
        text = resource_text(name)
        assert text == AUTHORING_PATHS[name].read_text(encoding="utf-8")
        assert isinstance(resource_yaml(name), dict)
        assert isinstance(yaml.safe_load(text), dict)


def test_resource_path_materializes_the_declared_resource() -> None:
    with resource_path("SCHEMA.yaml") as path:
        assert path.is_file()
        assert path.read_text(encoding="utf-8") == resource_text("SCHEMA.yaml")


@pytest.mark.parametrize("name", ["../SCHEMA.yaml", "/tmp/SCHEMA.yaml", "missing.yaml"])
def test_resource_access_rejects_unknown_or_unsafe_names(name: str) -> None:
    with pytest.raises(KeyError, match="Unknown Azoth resource"):
        resource_text(name)
