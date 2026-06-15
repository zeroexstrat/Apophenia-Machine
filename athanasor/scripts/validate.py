#!/usr/bin/env python3
"""Validate pipeline artifacts against YAML schema definitions.

This is the machine guardrail that turns "LLM prompt compliance" into
artifact-level compliance. It does not replace human triage; it enforces
structured, parseable, and schema-conformant outputs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "PyYAML is required. Install with `pip install pyyaml` and retry."
    ) from exc


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATHS = {
    "library": ROOT / "SCHEMA.yaml",
    "exhaust": ROOT / "EXHAUST_SCHEMA.yaml",
    "connect": ROOT / "CONNECT_SCHEMA.yaml",
    "detect": ROOT / "DETECT_SCHEMA.yaml",
}


def load_yaml(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def coerce_value(value: Any, expected: str) -> tuple[Any, bool]:
    """Return (coerced_value, changed)."""
    if expected in {"integer", "number"} and isinstance(value, bool):
        return value, False

    if expected == "integer":
        if isinstance(value, bool):
            return value, False
        if isinstance(value, int):
            return value, False
        if isinstance(value, float) and value.is_integer():
            return int(value), True
        return value, False

    if expected == "number":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value), False
        if isinstance(value, str):
            try:
                return float(value), True
            except ValueError:
                return value, False
        return value, False

    if expected == "boolean":
        if isinstance(value, bool):
            return value, False
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "y"}:
                return True, True
            if lowered in {"false", "0", "no", "n"}:
                return False, True
        return value, False

    if expected == "list":
        if isinstance(value, tuple):
            return list(value), True
        return value, False

    if expected == "string":
        return str(value), True

    return value, False


def parse_iso_datetime(value: str) -> bool:
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt.datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def validate_field(value: Any, schema: dict[str, Any], path: str, errors: list[str], fix: bool) -> Any:
    changed = False

    field_type = str(schema.get("type", "string"))
    required = bool(schema.get("required", False))
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    default = schema.get("default")
    enum = schema.get("enum")
    pattern = schema.get("pattern")
    data_format = schema.get("format")

    if value is None:
        if required:
            errors.append(f"{path}: missing required field")
        return value

    # Lists are represented as `list`, `list[string]`, and `list[object]`.
    if field_type.startswith("list"):
        item_type = None
        if field_type.startswith("list[") and field_type.endswith("]"):
            item_type = field_type[5:-1]
        if not isinstance(value, list):
            coerced, did_coerce = coerce_value(value, "list")
            if fix and did_coerce:
                value, changed = coerced, True
            else:
                errors.append(f"{path}: expected list, got {type(value).__name__}")
                return value

        if item_type:
            min_items = schema.get("min_items")
            max_items = schema.get("max_items")
            if min_items is not None and len(value) < int(min_items):
                errors.append(f"{path}: expected at least {min_items} items, got {len(value)}")
            if max_items is not None and len(value) > int(max_items):
                errors.append(f"{path}: expected at most {max_items} items, got {len(value)}")

            if item_type == "object":
                item_schema = schema.get("fields", {})
                if not isinstance(item_schema, dict):
                    errors.append(f"{path}: list[object] schema missing fields")
                else:
                    for idx, item in enumerate(value):
                        if not isinstance(item, dict):
                            errors.append(f"{path}/{idx}: expected object")
                            continue
                        child_path = f"{path}/{idx}"
                        _, child_changed = validate_object(item, item_schema, child_path, errors, fix)
                        changed = changed or child_changed
            elif item_type == "string":
                for idx, item in enumerate(value):
                    if not isinstance(item, str):
                        coerced, did_coerce = coerce_value(item, "string")
                        if fix and did_coerce:
                            value[idx] = str(coerced)
                            changed = True
                        else:
                            errors.append(f"{path}/{idx}: expected string in list")
            else:
                errors.append(f"{path}: unsupported list item type '{item_type}'")
        return value

    # Objects are dictionaries, with optional field definitions.
    if field_type == "object":
        if not isinstance(value, dict):
            coerced, did_coerce = coerce_value(value, "object")
            if not (fix and did_coerce):
                errors.append(f"{path}: expected object, got {type(value).__name__}")
                return value
            value = coerced
            changed = True
        return validate_object(value, schema.get("fields", {}), path, errors, fix)[0]

    # Primitives
    if field_type == "string":
        if not isinstance(value, str):
            coerced, did_coerce = coerce_value(value, "string")
            if fix and did_coerce:
                value = str(coerced)
                changed = True
            else:
                errors.append(f"{path}: expected string, got {type(value).__name__}")
                return value

        if pattern and not re.fullmatch(pattern, str(value)):
            errors.append(f"{path}: value '{value}' does not match pattern {pattern}")
        if data_format == "ISO 8601" and isinstance(value, str) and not parse_iso_datetime(value):
            errors.append(f"{path}: value '{value}' is not ISO-8601 datetime format")
        if enum and value not in enum:
            errors.append(f"{path}: {value!r} not in enum {enum}")

        return value

    if field_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            coerced, did_coerce = coerce_value(value, "integer")
            if fix and did_coerce:
                value = coerced
                changed = True
            else:
                errors.append(f"{path}: expected integer, got {type(value).__name__}")
                return value
        if minimum is not None and value < minimum:
            errors.append(f"{path}: value {value} below minimum {minimum}")
        if maximum is not None and value > maximum:
            errors.append(f"{path}: value {value} above maximum {maximum}")
        if enum and value not in enum:
            errors.append(f"{path}: {value} not in enum {enum}")
        return value

    if field_type == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            coerced, did_coerce = coerce_value(value, "number")
            if fix and did_coerce:
                value = coerced
                changed = True
            else:
                errors.append(f"{path}: expected number, got {type(value).__name__}")
                return value
        if minimum is not None and value < minimum:
            errors.append(f"{path}: value {value} below minimum {minimum}")
        if maximum is not None and value > maximum:
            errors.append(f"{path}: value {value} above maximum {maximum}")
        if enum and value not in enum:
            errors.append(f"{path}: {value} not in enum {enum}")
        return value

    if field_type == "boolean":
        if not isinstance(value, bool):
            coerced, did_coerce = coerce_value(value, "boolean")
            if fix and did_coerce:
                value = coerced
                changed = True
            else:
                errors.append(f"{path}: expected boolean, got {type(value).__name__}")
        return value

    if enum and value not in enum:
        errors.append(f"{path}: {value!r} not in enum {enum}")
    return value


def validate_object(data: dict[str, Any], fields: dict[str, Any], path: str, errors: list[str], fix: bool) -> tuple[Any, bool]:
    changed = False

    if not fields:
        return data, changed

    if not isinstance(data, dict):
        errors.append(f"{path}: expected object, got {type(data).__name__}")
        return data, changed

    for key, field_schema in fields.items():
        if not isinstance(field_schema, dict):
            continue

        required = bool(field_schema.get("required", False))
        default = field_schema.get("default")
        if key not in data:
            if required:
                errors.append(f"{path}/{key}: missing required field")
            elif fix and "default" in field_schema:
                data[key] = default
                changed = True
            continue

        new_value = validate_field(data[key], field_schema, f"{path}/{key}", errors, fix)
        data[key] = new_value

    return data, changed


def validate_document(document: dict[str, Any], schema: dict[str, Any], path: str, fix: bool) -> tuple[bool, list[str], dict[str, Any], bool]:
    errors: list[str] = []
    doc_copy = json.loads(json.dumps(document))

    _, changed = validate_object(doc_copy, schema, path, errors, fix)
    return (len(errors) == 0), errors, doc_copy, changed


def detect_schema(path: Path) -> Path | None:
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        rel = None

    if rel is not None and len(rel.parts) >= 2:
        if rel.parts[0] == "albedo" and rel.parts[1] == "library":
            return SCHEMA_PATHS["library"]
        if rel.parts[0] == "albedo" and rel.parts[1] == "exhaust":
            return SCHEMA_PATHS["exhaust"]
        if rel.parts[0] == "citrinitas" and (rel.parts[1] == "within_domain" or rel.parts[1] == "cross_domain"):
            return SCHEMA_PATHS["connect"]
        if rel.parts[0] == "rubedo" and rel.parts[1] == "hypotheses":
            return SCHEMA_PATHS["detect"]

    if path.name.endswith("_exhaust.yaml"):
        return SCHEMA_PATHS["exhaust"]
    if path.name.startswith("cluster_") and path.suffix == ".yaml":
        return SCHEMA_PATHS["detect"]
    if path.parent.name in {"within_domain", "cross_domain"}:
        return SCHEMA_PATHS["connect"]
    return None


def iter_targets(explicit_targets: list[Path] | None = None) -> list[Path]:
    if explicit_targets:
        targets: list[Path] = []
        for target in explicit_targets:
            if not target.exists():
                continue
            if target.is_file():
                targets.append(target)
                continue
            if target.is_dir():
                targets.extend([p for p in target.rglob("*.y*ml") if p.is_file()])
        return targets

    files: list[Path] = []
    for subdir in [
        ROOT / "albedo" / "library",
        ROOT / "albedo" / "exhaust",
        ROOT / "citrinitas" / "within_domain",
        ROOT / "citrinitas" / "cross_domain",
        ROOT / "rubedo" / "hypotheses",
    ]:
        if subdir.exists():
            files.extend(sorted(subdir.rglob("*.yaml")))
            files.extend(sorted(subdir.rglob("*.yml")))
    return files


def validate_file(path: Path, schema_path: Path | None = None, *, fix: bool = False) -> tuple[bool, list[str], int]:
    schema_target = schema_path or detect_schema(path)
    if not schema_target or not schema_target.exists():
        return False, [f"{path}: cannot infer schema path"], 0

    try:
        schema = load_yaml(schema_target)
    except Exception as exc:  # pragma: no cover
        return False, [f"{schema_target}: failed to parse schema ({exc})"], 0

    try:
        content = load_yaml(path)
    except Exception as exc:  # pragma: no cover
        return False, [f"{path}: failed to parse YAML ({exc})"], 0

    if content is None:
        content = {}
    if not isinstance(content, dict):
        return False, [f"{path}: expected YAML mapping/document root"], 0

    schema_root = schema
    if not isinstance(schema_root, dict):
        return False, [f"{schema_target}: invalid schema (root must be mapping)"], 0

    valid, errors, fixed_data, changed = validate_document(content, schema_root, str(path), fix)
    if fix and changed:
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(fixed_data, f, sort_keys=False)
    return valid, errors, 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Validate Azoth artifact YAML files against local schema files.")
    p.add_argument("paths", nargs="*", help="One or more YAML files/directories to validate")
    p.add_argument("--all", action="store_true", help="Validate all known artifact directories")
    p.add_argument("--schema", type=Path, help="Override detected schema file")
    p.add_argument("--fix", action="store_true", help="Apply safe, limited auto-fixes")
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    explicit = [Path(p).resolve() for p in args.paths]
    targets = iter_targets(explicit) if args.all or explicit else []

    if args.all and not targets:
        print("No files found under known artifact directories.", flush=True)
        return 0
    if not args.all and not explicit:
        parser.print_help()
        return 2

    all_ok = True
    total = 0
    failed = 0

    for path in targets:
        if path.is_dir():
            continue
        schema_path = args.schema
        ok, errors, _ = validate_file(path, schema_path, fix=args.fix)
        total += 1
        if ok:
            status = "OK"
        else:
            status = "FAIL"
            all_ok = False
            failed += 1
        label = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        print(f"{status} {label}")
        for err in errors:
            print(f"  - {err}")

    if total == 0:
        print("No YAML files matched input.", flush=True)
        return 2

    print(f"Validated {total} files; failed: {failed}", flush=True)
    if args.fix:
        print("Fix mode enabled: optional fields with defaults were auto-filled where possible.")

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
