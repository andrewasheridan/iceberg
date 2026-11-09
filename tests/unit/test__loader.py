"""Test sheridan.iceberg._loader (load_json)."""

import json
from pathlib import Path
from typing import Any

import pytest

from sheridan.iceberg._exceptions import IcebergError, SnapshotError
from sheridan.iceberg._formatter import JSON_SCHEMA_VERSION, format_json
from sheridan.iceberg._loader import load_json
from sheridan.iceberg._models import (
    Assignment,
    Class,
    Function,
    Module,
    Package,
    Parameter,
    Reference,
)

_PARAM = Parameter(name="x", annotation="int", default="1")
_FUNCTION = Function(
    name="f",
    positional_parameters=(_PARAM, Parameter(name="y", annotation=None, default=None)),
    keyword_parameters=frozenset({Parameter(name="b", annotation="str", default=None), Parameter("a", None, "0")}),
    var_positional=Parameter(name="args", annotation=None, default=None),
    var_keyword=Parameter(name="kwargs", annotation="Any", default=None),
    returns="int",
    is_async=True,
    kind="function",
    decorators=("functools.cache",),
    overloads=(
        Function(
            name="f",
            positional_parameters=(),
            keyword_parameters=frozenset(),
            var_positional=None,
            var_keyword=None,
            returns=None,
            is_async=False,
        ),
    ),
)
_CLASS = Class(
    name="C",
    bases=("Base", "Generic[T]"),
    keywords=("metaclass=Meta",),
    assignments=(Assignment(name="X", annotation="int"),),
    methods=(
        Function(
            name="p",
            positional_parameters=(Parameter("self", None, None),),
            keyword_parameters=frozenset(),
            var_positional=None,
            var_keyword=None,
            returns="int",
            is_async=False,
            kind="property",
            decorators=("property",),
        ),
    ),
    nested_classes=(Class(name="Inner", bases=(), keywords=(), assignments=(), methods=(), nested_classes=()),),
)
_MODULE = Module(
    name="pkg",
    assignments=(Assignment(name="Y", annotation=None),),
    classes=(_CLASS,),
    functions=(_FUNCTION,),
    references=(Reference(name="sqrt", module="math", attribute="sqrt"), Reference("ghost", None, None)),
)


def _package(root: Path) -> Package:
    sub = Package(name="pkg.sub", path=root / "sub", modules=(Module("pkg.sub", (), (), ()),), subpackages=())
    return Package(name="pkg", path=root, modules=(_MODULE,), subpackages=(sub,))


def _snapshot(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(format_json(_MODULE))
    data.update(changes)
    return data


def test_module_round_trips() -> None:
    assert load_json(format_json(_MODULE)) == _MODULE


def test_package_round_trips_with_root(tmp_path: Path) -> None:
    package = _package(tmp_path)

    assert load_json(format_json(package), root=tmp_path) == package


def test_package_paths_are_relative_without_root(tmp_path: Path) -> None:
    loaded = load_json(format_json(_package(tmp_path)))

    assert isinstance(loaded, Package)
    assert loaded.path == Path()
    assert loaded.subpackages[0].path == Path("sub")


def test_keyword_parameters_load_as_frozenset() -> None:
    loaded = load_json(format_json(_MODULE))

    assert isinstance(loaded, Module)
    assert isinstance(loaded.functions[0].keyword_parameters, frozenset)
    assert isinstance(loaded.functions[0].positional_parameters, tuple)


def test_unknown_fields_are_ignored() -> None:
    data = _snapshot(extra="ignored")
    data["classes"][0]["extra"] = 1

    assert load_json(json.dumps(data)) == _MODULE


def test_snapshot_error_is_iceberg_error() -> None:
    assert issubclass(SnapshotError, IcebergError)


@pytest.mark.parametrize("version", [JSON_SCHEMA_VERSION + 1, 0, "1", None, True])
def test_unknown_schema_version_raises(version: object) -> None:
    with pytest.raises(SnapshotError, match="schema_version"):
        load_json(json.dumps(_snapshot(schema_version=version)))


def test_missing_schema_version_raises() -> None:
    data = _snapshot()
    del data["schema_version"]

    with pytest.raises(SnapshotError, match="schema_version"):
        load_json(json.dumps(data))


def test_invalid_json_raises() -> None:
    with pytest.raises(SnapshotError, match="invalid JSON"):
        load_json("{not json")


def test_top_level_must_be_an_object() -> None:
    with pytest.raises(SnapshotError, match="JSON object"):
        load_json("[]")


@pytest.mark.parametrize("node_type", ["class", "function", None])
def test_top_level_must_be_package_or_module(node_type: str | None) -> None:
    with pytest.raises(SnapshotError, match="package or module"):
        load_json(json.dumps(_snapshot(node_type=node_type)))


def test_missing_field_raises() -> None:
    data = _snapshot()
    del data["functions"][0]["returns"]

    with pytest.raises(SnapshotError, match="missing field 'returns' in function 'f'"):
        load_json(json.dumps(data))


@pytest.mark.parametrize(
    ("key", "value"),
    [("name", 1), ("is_async", "yes"), ("returns", 3), ("positional_parameters", {}), ("var_keyword", "kw")],
)
def test_wrong_field_type_raises(key: str, value: object) -> None:
    data = _snapshot()
    data["functions"][0][key] = value

    with pytest.raises(SnapshotError, match="wrong type"):
        load_json(json.dumps(data))


def test_bool_is_not_accepted_as_a_string_field() -> None:
    data = _snapshot()
    data["assignments"][0]["annotation"] = True

    with pytest.raises(SnapshotError, match="wrong type"):
        load_json(json.dumps(data))


def test_unexpected_node_type_raises() -> None:
    data = _snapshot()
    data["classes"][0]["node_type"] = "function"

    with pytest.raises(SnapshotError, match="node_type must be 'class'"):
        load_json(json.dumps(data))


def test_non_object_node_raises() -> None:
    data = _snapshot()
    data["classes"] = ["C"]

    with pytest.raises(SnapshotError, match="JSON object"):
        load_json(json.dumps(data))


def test_unknown_function_kind_raises() -> None:
    data = _snapshot()
    data["functions"][0]["kind"] = "lambda"

    with pytest.raises(SnapshotError, match="unknown kind 'lambda'"):
        load_json(json.dumps(data))


def test_non_string_decorator_raises() -> None:
    data = _snapshot()
    data["functions"][0]["decorators"] = [1]

    with pytest.raises(SnapshotError, match="only strings"):
        load_json(json.dumps(data))


@pytest.mark.parametrize("key", ["bases", "keywords"])
def test_non_string_class_base_or_keyword_raises(key: str) -> None:
    data = _snapshot()
    data["classes"][0][key] = [None]

    with pytest.raises(SnapshotError, match="only strings"):
        load_json(json.dumps(data))


@pytest.mark.parametrize("key", ["bases", "keywords"])
def test_class_without_bases_or_keywords_raises(key: str) -> None:
    data = _snapshot()
    del data["classes"][0][key]

    with pytest.raises(SnapshotError, match=f"missing field '{key}'"):
        load_json(json.dumps(data))
