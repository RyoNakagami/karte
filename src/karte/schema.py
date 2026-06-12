"""Per-project custom field schema, loaded from .karte/schema.json.

The file is hand-edited by the user; karte only reads it. Shape:

    {
      "fields": [
        {"name": "estimate", "type": "float", "required": false, "default": 0},
        {"name": "assignee", "type": "str"},
        {"name": "sprint",   "type": "int"},
        {"name": "blocked",  "type": "bool", "default": false},
        {"name": "due_review", "type": "date"},
        {"name": "kind", "type": "enum", "choices": ["bug", "feat", "chore"],
         "default": "feat"}
      ]
    }

Supported types: str, int, float, bool, date, enum.
Per-field keys: name (required), type (required), required (bool, default false),
default (any), choices (list, required for enum).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

SCHEMA_FILE = "schema.json"

VALID_TYPES = {"str", "int", "float", "bool", "date", "enum"}

# Built-in fields are reserved; a custom field may not shadow them.
RESERVED_NAMES = {
    "id", "title", "description", "status", "priority",
    "created_at", "updated_at", "start_at", "end_at",
    "related_files", "tags",
}

# DuckDB column type per schema type, for the query view.
DUCKDB_TYPE = {
    "str": "VARCHAR",
    "int": "BIGINT",
    "float": "DOUBLE",
    "bool": "BOOLEAN",
    "date": "VARCHAR",   # stored as ISO string, queryable as timestamp
    "enum": "VARCHAR",
}


class SchemaError(Exception):
    """Raised when schema.json is malformed."""


class FieldError(Exception):
    """Raised when a --set value fails validation against the schema."""


def schema_path(karte_dir: Path) -> Path:
    return karte_dir / SCHEMA_FILE


def load_fields(karte_dir: Path) -> list[dict]:
    """Read and validate schema.json. Returns [] if the file is absent."""
    path = schema_path(karte_dir)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SchemaError(f"{path} is not valid JSON: {e}")

    fields = raw.get("fields", raw if isinstance(raw, list) else None)
    if not isinstance(fields, list):
        raise SchemaError(f"{path}: expected a 'fields' array.")

    seen: set[str] = set()
    for fld in fields:
        if not isinstance(fld, dict):
            raise SchemaError("Each field must be an object.")
        name = fld.get("name")
        ftype = fld.get("type")
        if not name or not isinstance(name, str):
            raise SchemaError("Field is missing a string 'name'.")
        if name in RESERVED_NAMES:
            raise SchemaError(f"Field '{name}' shadows a built-in field; rename it.")
        if name in seen:
            raise SchemaError(f"Duplicate field name '{name}'.")
        seen.add(name)
        if ftype not in VALID_TYPES:
            raise SchemaError(
                f"Field '{name}': type must be one of {sorted(VALID_TYPES)}, got {ftype!r}."
            )
        if ftype == "enum":
            choices = fld.get("choices")
            if not isinstance(choices, list) or not choices:
                raise SchemaError(f"Enum field '{name}' needs a non-empty 'choices' list.")
        # Validate default against its own type if present.
        if "default" in fld and fld["default"] is not None:
            try:
                coerce(fld, fld["default"], _is_default=True)
            except FieldError as e:
                raise SchemaError(f"Field '{name}' default invalid: {e}")
    return fields


def field_map(fields: list[dict]) -> dict[str, dict]:
    return {f["name"]: f for f in fields}


def coerce(field: dict, value: Any, *, _is_default: bool = False) -> Any:
    """Convert a raw string (or default value) to the field's typed value."""
    ftype = field["type"]
    name = field["name"]

    if value is None:
        return None

    try:
        if ftype == "str":
            return str(value)
        if ftype == "int":
            return int(value)
        if ftype == "float":
            return float(value)
        if ftype == "bool":
            if isinstance(value, bool):
                return value
            s = str(value).strip().lower()
            if s in {"true", "1", "yes", "y", "on"}:
                return True
            if s in {"false", "0", "no", "n", "off"}:
                return False
            raise ValueError("expected true/false")
        if ftype == "date":
            # Accept YYYY-MM-DD or full ISO; store normalized ISO string.
            return datetime.fromisoformat(str(value)).isoformat()
        if ftype == "enum":
            sval = str(value)
            if sval not in field["choices"]:
                raise ValueError(f"must be one of {field['choices']}")
            return sval
    except (ValueError, TypeError) as e:
        raise FieldError(f"'{name}' ({ftype}): {e}")
    raise FieldError(f"'{name}': unknown type {ftype}")


def defaults(fields: list[dict]) -> dict[str, Any]:
    """Default value for every field (explicit default, else None)."""
    out: dict[str, Any] = {}
    for f in fields:
        if "default" in f and f["default"] is not None:
            out[f["name"]] = coerce(f, f["default"], _is_default=True)
        else:
            out[f["name"]] = None
    return out


def apply_sets(
    fields: list[dict],
    raw_sets: dict[str, str],
    *,
    existing: Optional[dict] = None,
    require_required: bool = True,
) -> dict[str, Any]:
    """Validate and coerce a dict of name->raw-string into typed custom values.

    Unknown keys raise. On add (existing is None) missing required fields raise
    unless they have a default.
    """
    fmap = field_map(fields)
    for key in raw_sets:
        if key not in fmap:
            raise FieldError(
                f"Unknown custom field '{key}'. Defined: {sorted(fmap) or 'none'}."
            )

    result: dict[str, Any] = {}
    for name, raw in raw_sets.items():
        result[name] = coerce(fmap[name], raw)

    if require_required and existing is None:
        merged_defaults = defaults(fields)
        for f in fields:
            name = f["name"]
            if f.get("required") and result.get(name) is None and merged_defaults.get(name) is None:
                raise FieldError(f"Required custom field '{name}' not provided (use --set {name}=...).")
    return result
