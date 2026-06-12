import json
from pathlib import Path

import pytest

from karte import schema as sch


def write_schema(karte_dir: Path, fields: list[dict]) -> None:
    karte_dir.mkdir(parents=True, exist_ok=True)
    (karte_dir / "schema.json").write_text(json.dumps({"fields": fields}))


def test_load_fields_absent_returns_empty(tmp_path: Path) -> None:
    assert sch.load_fields(tmp_path) == []


def test_load_fields_valid(tmp_path: Path) -> None:
    write_schema(
        tmp_path,
        [
            {"name": "assignee", "type": "str"},
            {"name": "estimate", "type": "float", "default": 0},
            {"name": "kind", "type": "enum", "choices": ["bug", "feat"], "default": "feat"},
        ],
    )
    fields = sch.load_fields(tmp_path)
    assert [f["name"] for f in fields] == ["assignee", "estimate", "kind"]


@pytest.mark.parametrize(
    "fields, match",
    [
        ([{"name": "id", "type": "str"}], "shadows a built-in"),
        ([{"name": "x", "type": "nope"}], "type must be one of"),
        ([{"name": "x", "type": "enum"}], "non-empty 'choices'"),
        ([{"name": "x", "type": "str"}, {"name": "x", "type": "int"}], "Duplicate"),
        ([{"name": "x", "type": "int", "default": "abc"}], "default invalid"),
    ],
)
def test_load_fields_rejects_bad_schema(tmp_path: Path, fields: list[dict], match: str) -> None:
    write_schema(tmp_path, fields)
    with pytest.raises(sch.SchemaError, match=match):
        sch.load_fields(tmp_path)


def test_load_fields_invalid_json(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "schema.json").write_text("{not json")
    with pytest.raises(sch.SchemaError, match="not valid JSON"):
        sch.load_fields(tmp_path)


@pytest.mark.parametrize(
    "field, raw, expected",
    [
        ({"name": "x", "type": "str"}, 12, "12"),
        ({"name": "x", "type": "int"}, "42", 42),
        ({"name": "x", "type": "bool"}, "yes", True),
        ({"name": "x", "type": "bool"}, "off", False),
        ({"name": "x", "type": "date"}, "2026-06-12", "2026-06-12T00:00:00"),
        ({"name": "x", "type": "enum", "choices": ["a", "b"]}, "a", "a"),
    ],
)
def test_coerce(field: dict, raw: object, expected: object) -> None:
    assert sch.coerce(field, raw) == expected


def test_coerce_float() -> None:
    assert sch.coerce({"name": "x", "type": "float"}, "1.5") == pytest.approx(1.5)


@pytest.mark.parametrize(
    "field, raw",
    [
        ({"name": "x", "type": "int"}, "abc"),
        ({"name": "x", "type": "bool"}, "maybe"),
        ({"name": "x", "type": "date"}, "not-a-date"),
        ({"name": "x", "type": "enum", "choices": ["a"]}, "z"),
    ],
)
def test_coerce_rejects_bad_values(field: dict, raw: str) -> None:
    with pytest.raises(sch.FieldError):
        sch.coerce(field, raw)


def test_apply_sets_unknown_key() -> None:
    with pytest.raises(sch.FieldError, match="Unknown custom field"):
        sch.apply_sets([{"name": "a", "type": "str"}], {"b": "1"})


def test_apply_sets_required_missing_on_add() -> None:
    fields = [{"name": "sprint", "type": "int", "required": True}]
    with pytest.raises(sch.FieldError, match="Required custom field 'sprint'"):
        sch.apply_sets(fields, {}, existing=None)


def test_apply_sets_required_satisfied_by_default() -> None:
    fields = [{"name": "sprint", "type": "int", "required": True, "default": 1}]
    assert sch.apply_sets(fields, {}, existing=None) == {}


def test_apply_sets_not_required_on_update() -> None:
    fields = [{"name": "sprint", "type": "int", "required": True}]
    assert sch.apply_sets(fields, {"sprint": "3"}, existing={"id": 1}) == {"sprint": 3}


def test_defaults() -> None:
    fields = [
        {"name": "a", "type": "int", "default": 2},
        {"name": "b", "type": "str"},
    ]
    assert sch.defaults(fields) == {"a": 2, "b": None}