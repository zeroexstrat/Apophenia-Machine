"""YAML schema validation helpers used by ingest/exhaust/connect/detect."""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


class SchemaError(Exception):
    pass


def parse_schema(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        payload = yaml.safe_load(f)
    if not isinstance(payload, dict):
        raise SchemaError(f"Schema is not a mapping: {path}")
    return payload


def validate(
    payload: Any,
    schema: dict[str, Any],
    *,
    path: str = "",
    fix: bool = False,
) -> tuple[bool, list[str], Any, bool]:
    errors: list[str] = []
    doc = deepcopy(payload) if not isinstance(payload, dict) else deepcopy(payload)
    changed = False
    _, doc_changed = _validate_object(doc, schema, _json_pointer(path), errors, fix)
    changed = changed or doc_changed
    return len(errors) == 0, errors, doc, changed

def _json_pointer(path: str) -> str:
    return path or "/"


def _coerce_bool(value: Any) -> tuple[Any, bool]:
    if isinstance(value, bool):
        return value, False
    if isinstance(value, str):
        lv = value.strip().lower()
        if lv in {"true", "1", "yes", "y"}:
            return True, True
        if lv in {"false", "0", "no", "n"}:
            return False, True
    return value, False


def _coerce_int(value: Any) -> tuple[Any, bool]:
    if isinstance(value, bool):
        return value, False
    if isinstance(value, int):
        return value, False
    if isinstance(value, float) and value.is_integer():
        return int(value), True
    if isinstance(value, str):
        try:
            return int(value), True
        except ValueError:
            return value, False
    return value, False


def _validate_primitive(path: str, value: Any, field: dict[str, Any], errors: list[str], fix: bool) -> tuple[Any, bool]:
    changed = False
    field_type = field.get("type", "string")
    required = bool(field.get("required", False))
    default = field.get("default")
    enum = field.get("enum")
    pattern = field.get("pattern")
    minimum = field.get("minimum")
    maximum = field.get("maximum")
    fmt = field.get("format")

    if value is None:
        if required:
            errors.append(f"{path}: missing required field")
        if fix and "default" in field:
            return default, True
        return value, changed

    if field_type == "string":
        if not isinstance(value, str):
            try:
                if fix:
                    value = str(value)
                    changed = True
                else:
                    errors.append(f"{path}: expected string, got {type(value).__name__}")
            except Exception:
                errors.append(f"{path}: expected string, got {type(value).__name__}")
        if isinstance(value, str):
            if pattern and not re.fullmatch(pattern, value):
                errors.append(f"{path}: does not match pattern {pattern}")
            if fmt == "ISO 8601":
                try:
                    from datetime import datetime

                    if value.endswith("Z"):
                        value = value[:-1] + "+00:00"
                    datetime.fromisoformat(value)
                except ValueError:
                    errors.append(f"{path}: invalid ISO 8601 datetime")

    elif field_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            value, did = _coerce_int(value)
            if did:
                changed = True
            else:
                errors.append(f"{path}: expected integer")
        if isinstance(value, int) and not isinstance(value, bool):
            if minimum is not None and value < minimum:
                errors.append(f"{path}: value {value} < minimum {minimum}")
            if maximum is not None and value > maximum:
                errors.append(f"{path}: value {value} > maximum {maximum}")

    elif field_type == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            try:
                value = float(value)
                changed = True
            except (TypeError, ValueError):
                errors.append(f"{path}: expected number")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if minimum is not None and value < minimum:
                errors.append(f"{path}: value {value} < minimum {minimum}")
            if maximum is not None and value > maximum:
                errors.append(f"{path}: value {value} > maximum {maximum}")

    elif field_type == "boolean":
        if not isinstance(value, bool):
            value, did = _coerce_bool(value)
            if did:
                changed = True
            else:
                errors.append(f"{path}: expected boolean")

    elif field_type.startswith("list"):
        if not isinstance(value, list):
            if fix:
                value = [value]
                changed = True
            else:
                errors.append(f"{path}: expected list")
                return value, changed
        min_items = field.get("min_items")
        max_items = field.get("max_items")
        if min_items is not None and len(value) < min_items:
            errors.append(f"{path}: expected at least {min_items} items")
        if max_items is not None and len(value) > max_items:
            errors.append(f"{path}: expected at most {max_items} items")

        item_type = None
        if isinstance(field_type, str) and field_type.startswith("list[") and field_type.endswith("]"):
            item_type = field_type[5:-1]
        if item_type == "string":
            for idx, item in enumerate(list(value)):
                if not isinstance(item, str):
                    if fix:
                        value[idx] = str(item)
                        changed = True
                    else:
                        errors.append(f"{path}/{idx}: expected string")
        if item_type == "object":
            item_schema = field.get("fields", {})
            for idx, item in enumerate(list(value)):
                if not isinstance(item, dict):
                    errors.append(f"{path}/{idx}: expected object")
                    continue
                value[idx], item_changed = _validate_object(item, item_schema, f"{path}/{idx}", errors, fix)
                changed = changed or item_changed

    elif field_type == "object":
        if not isinstance(value, dict):
            errors.append(f"{path}: expected object")
            if fix:
                return {}, True
            return value, changed
        value, obj_changed = _validate_object(value, field.get("fields", {}), path, errors, fix)
        changed = changed or obj_changed

    if enum is not None:
        if value not in enum:
            errors.append(f"{path}: value {value!r} not in enum {enum}")
    return value, changed


def _validate_object(data: dict[str, Any], fields: dict[str, Any], path: str, errors: list[str], fix: bool) -> tuple[dict[str, Any], bool]:
    if fields is None:
        return data, False
    if not isinstance(data, dict):
        if fix:
            return {}, True
        errors.append(f"{path}: expected object")
        return data, False

    changed = False
    for key, spec in fields.items():
        if not isinstance(spec, dict):
            continue
        required = bool(spec.get("required", False))
        has_default = "default" in spec
        if key not in data:
            if required and fix:
                data[key] = spec.get("default") if has_default else None
                changed = True
            elif required:
                errors.append(f"{path}/{key}: missing required field")
            continue

        data[key], child_changed = _validate_primitive(f"{path}/{key}", data.get(key), spec, errors, fix)
        changed = changed or child_changed

    return data, changed

