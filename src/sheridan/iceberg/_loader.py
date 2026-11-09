"""Loader that rebuilds iceberg models from the JSON written by ``format_json``."""

__all__ = ["load_json"]

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, get_args

from sheridan.iceberg._exceptions import SnapshotError
from sheridan.iceberg._formatter import JSON_SCHEMA_VERSION
from sheridan.iceberg._models import (
    Assignment,
    Class,
    Function,
    FunctionKind,
    Module,
    Package,
    Parameter,
    Reference,
)

_FUNCTION_KINDS: frozenset[str] = frozenset(get_args(FunctionKind.__value__))
"""The ``kind`` values a serialized function may carry."""


def _field(data: dict[str, Any], key: str, kind: type | tuple[type, ...]) -> Any:
    """Read ``data[key]`` after checking that it exists and has the expected type.

    Args:
        data: A JSON object.
        key: The field to read.
        kind: The type or types the value may have.

    Returns:
        The value of the field.

    Raises:
        SnapshotError: When the field is missing or has the wrong type.
    """
    if key not in data:
        raise SnapshotError(f"missing field {key!r} in {_describe(data)}")
    value = data[key]
    # bool is a subclass of int, so reject it unless bool itself is allowed.
    allowed = kind if isinstance(kind, tuple) else (kind,)
    if not isinstance(value, allowed) or (isinstance(value, bool) and bool not in allowed):
        raise SnapshotError(f"field {key!r} in {_describe(data)} has the wrong type: {type(value).__name__}")
    return value


def _optional_str(data: dict[str, Any], key: str) -> str | None:
    """Read a field that holds a string or ``null``.

    Args:
        data: A JSON object.
        key: The field to read.

    Returns:
        The string, or ``None``.
    """
    value: str | None = _field(data, key, (str, type(None)))
    return value


def _describe(data: dict[str, Any]) -> str:
    """Name a JSON object for an error message.

    Args:
        data: A JSON object.

    Returns:
        A short description such as ``function 'f'``.
    """
    node_type = data.get("node_type", "object")
    name = data.get("name")
    return f"{node_type} {name!r}" if isinstance(name, str) else str(node_type)


def _object(value: Any, node_type: str | None) -> dict[str, Any]:
    """Check that *value* is a JSON object with the expected ``node_type``.

    Args:
        value: The decoded JSON value.
        node_type: The required ``node_type``, or ``None`` for objects that
            have no ``node_type`` (parameters).

    Returns:
        *value*, typed as a dict.

    Raises:
        SnapshotError: When *value* is not an object or has another ``node_type``.
    """
    if not isinstance(value, dict):
        raise SnapshotError(f"expected a JSON object, got {type(value).__name__}")
    if node_type is not None and value.get("node_type") != node_type:
        raise SnapshotError(f"expected node_type {node_type!r}, got {value.get('node_type')!r}")
    return value


def _list[T](data: dict[str, Any], key: str, load: Callable[[Any], T]) -> tuple[T, ...]:
    """Load every item of a list field.

    Args:
        data: A JSON object.
        key: The list field to read.
        load: Builds one model from one list item.

    Returns:
        The loaded items in order.
    """
    return tuple(load(item) for item in _field(data, key, list))


def _str_list(data: dict[str, Any], key: str) -> tuple[str, ...]:
    """Read a list field whose items are strings.

    Args:
        data: A JSON object.
        key: The list field to read.

    Returns:
        The strings in order.

    Raises:
        SnapshotError: When an item is not a string.
    """
    items = _field(data, key, list)
    if not all(isinstance(item, str) for item in items):
        raise SnapshotError(f"field {key!r} in {_describe(data)} must hold only strings")
    return tuple(items)


def _load_parameter(value: Any) -> Parameter:
    data = _object(value, None)
    return Parameter(
        name=_field(data, "name", str),
        annotation=_optional_str(data, "annotation"),
        default=_optional_str(data, "default"),
    )


def _load_optional_parameter(data: dict[str, Any], key: str) -> Parameter | None:
    value = _field(data, key, (dict, type(None)))
    return None if value is None else _load_parameter(value)


def _load_function(value: Any) -> Function:
    data = _object(value, "function")
    kind = _field(data, "kind", str)
    if kind not in _FUNCTION_KINDS:
        raise SnapshotError(f"unknown kind {kind!r} in {_describe(data)}")
    return Function(
        name=_field(data, "name", str),
        positional_parameters=_list(data, "positional_parameters", _load_parameter),
        keyword_parameters=frozenset(_list(data, "keyword_parameters", _load_parameter)),
        var_positional=_load_optional_parameter(data, "var_positional"),
        var_keyword=_load_optional_parameter(data, "var_keyword"),
        returns=_optional_str(data, "returns"),
        is_async=_field(data, "is_async", bool),
        kind=kind,
        decorators=_str_list(data, "decorators"),
        overloads=_list(data, "overloads", _load_function),
    )


def _load_assignment(value: Any) -> Assignment:
    data = _object(value, "assignment")
    return Assignment(name=_field(data, "name", str), annotation=_optional_str(data, "annotation"))


def _load_reference(value: Any) -> Reference:
    data = _object(value, "reference")
    return Reference(
        name=_field(data, "name", str),
        module=_optional_str(data, "module"),
        attribute=_optional_str(data, "attribute"),
    )


def _load_class(value: Any) -> Class:
    data = _object(value, "class")
    return Class(
        name=_field(data, "name", str),
        assignments=_list(data, "assignments", _load_assignment),
        methods=_list(data, "methods", _load_function),
        nested_classes=_list(data, "nested_classes", _load_class),
    )


def _load_module(value: Any) -> Module:
    data = _object(value, "module")
    return Module(
        name=_field(data, "name", str),
        assignments=_list(data, "assignments", _load_assignment),
        classes=_list(data, "classes", _load_class),
        functions=_list(data, "functions", _load_function),
        references=_list(data, "references", _load_reference),
    )


def _load_package(value: Any, root: Path) -> Package:
    data = _object(value, "package")
    return Package(
        name=_field(data, "name", str),
        path=root / _field(data, "path", str),
        modules=_list(data, "modules", _load_module),
        subpackages=_list(data, "subpackages", lambda item: _load_package(item, root)),
    )


def load_json(text: str, *, root: Path | None = None) -> Package | Module:
    """Rebuild a ``Package`` or ``Module`` from the JSON that ``iceberg --json`` prints.

    The JSON stores package paths relative to the analyzed root, so the loaded
    paths are relative too unless *root* is given. With *root* set to the path
    that was analyzed, ``load_json(format_json(api), root=api.path) == api``.

    Fields that the current schema does not know are ignored.

    Args:
        text: The JSON text.
        root: The directory to resolve package paths against. Defaults to
            leaving them relative (the root package's path is ``Path(".")``).

    Returns:
        The rebuilt root package or module.

    Raises:
        SnapshotError: When *text* is not valid JSON, its ``schema_version`` is
            missing or not one this version of iceberg can read, or a node is
            missing a field, has a field of the wrong type, or has an
            unexpected ``node_type``.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SnapshotError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SnapshotError(f"expected a JSON object, got {type(data).__name__}")
    version = data.get("schema_version")
    if version != JSON_SCHEMA_VERSION or isinstance(version, bool):
        raise SnapshotError(
            f"unsupported schema_version {version!r}; this version of iceberg reads {JSON_SCHEMA_VERSION}"
        )

    match data.get("node_type"):
        case "package":
            return _load_package(data, root if root is not None else Path())
        case "module":
            return _load_module(data)
        case other:
            raise SnapshotError(f"expected a package or module at the top level, got node_type {other!r}")
