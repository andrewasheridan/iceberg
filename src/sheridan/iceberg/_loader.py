"""Make the iceberg models again from the JSON that ``format_json`` writes."""

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
"""The ``kind`` values that a serialized function can have."""


def _field(data: dict[str, Any], key: str, kind: type | tuple[type, ...]) -> Any:
    """Read ``data[key]``. First, make sure that it exists and has the expected type.

    Args:
        data: A JSON object.
        key: The field to read.
        kind: The type or types that the value can have.

    Returns:
        The value of the field.

    Raises:
        SnapshotError: If the field is missing or has the wrong type.
    """
    if key not in data:
        raise SnapshotError(f"missing field {key!r} in {_describe(data)}")

    value = data[key]
    allowed = kind if isinstance(kind, tuple) else (kind,)
    # bool is a subclass of int. Thus, reject a bool, unless the allowed types include bool.
    is_unwanted_bool = isinstance(value, bool) and bool not in allowed

    if not isinstance(value, allowed) or is_unwanted_bool:
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

    if not isinstance(name, str):
        return str(node_type)

    return f"{node_type} {name!r}"


def _object(value: Any, node_type: str | None) -> dict[str, Any]:
    """Check that *value* is a JSON object with the expected ``node_type``.

    Args:
        value: The decoded JSON value.
        node_type: The necessary ``node_type``, or ``None`` for objects that
            have no ``node_type`` (parameters).

    Returns:
        *value*, with the type dict.

    Raises:
        SnapshotError: If *value* is not an object or has a different ``node_type``.
    """
    if not isinstance(value, dict):
        raise SnapshotError(f"the value must be a JSON object, not {type(value).__name__}")

    if node_type is not None and value.get("node_type") != node_type:
        raise SnapshotError(f"node_type must be {node_type!r}, not {value.get('node_type')!r}")

    return value


def _list[T](data: dict[str, Any], key: str, load: Callable[[Any], T]) -> tuple[T, ...]:
    """Load each item of a list field.

    Args:
        data: A JSON object.
        key: The list field to read.
        load: A function that builds one model from one list item.

    Returns:
        The loaded items in order.
    """
    return tuple(load(item) for item in _field(data, key, list))


def _str_list(data: dict[str, Any], key: str) -> tuple[str, ...]:
    """Read a list field that holds strings.

    Args:
        data: A JSON object.
        key: The list field to read.

    Returns:
        The strings in order.

    Raises:
        SnapshotError: If an item is not a string.
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
        bases=_str_list(data, "bases"),
        keywords=_str_list(data, "keywords"),
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

    The JSON keeps package paths relative to the analyzed root. Thus, the
    loaded paths are also relative, unless you give *root*. If *root* is the
    analyzed path, ``load_json(format_json(api), root=api.path) == api``.

    The function ignores the fields that the current schema does not know.

    Args:
        text: The JSON text.
        root: The directory for the package paths. If you do not give it, the
            paths stay relative (the path of the root package is ``Path(".")``).

    Returns:
        The root package or module that the function made again.

    Raises:
        SnapshotError: If *text* is not valid JSON, if its ``schema_version`` is
            missing or this version of iceberg cannot read it, or if a node has
            a missing field, a field of the wrong type or an unexpected
            ``node_type``.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SnapshotError(f"invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise SnapshotError(f"the value must be a JSON object, not {type(data).__name__}")

    version = data.get("schema_version")
    if version != JSON_SCHEMA_VERSION or isinstance(version, bool):
        raise SnapshotError(
            f"unsupported schema_version {version!r}. This version of iceberg reads {JSON_SCHEMA_VERSION}."
        )

    match data.get("node_type"):
        case "package":
            return _load_package(data, root if root is not None else Path())

        case "module":
            return _load_module(data)

        case other:
            raise SnapshotError(f"the top level must be a package or module, not node_type {other!r}")
