"""Tree and JSON formatters for iceberg public API snapshots."""

__all__ = ["format_json", "format_tree"]

import dataclasses
import json
from pathlib import Path
from typing import Any

from sheridan.iceberg._models import (
    Assignment,
    Class,
    Function,
    Module,
    Package,
    Parameter,
    Reference,
)

_BRANCH = "├── "
"""Connector string for a non-last tree node."""

_LAST = "└── "
"""Connector string for the final child of a tree node."""

_PIPE = "│   "
"""Vertical continuation line used when a parent has more siblings below."""

_BLANK = "    "
"""Blank indent used under the last child of a tree node."""


def _param_str(parameter: Parameter) -> str:
    """Render a single parameter as ``name: annotation = default``.

    Args:
        parameter: The parameter to render.

    Returns:
        A string in the form ``name``, ``name: annotation``,
        ``name = default``, or ``name: annotation = default`` depending on
        which fields are populated.
    """
    parts = [parameter.name]

    if parameter.annotation is not None:
        parts.append(f": {parameter.annotation}")

    if parameter.default is not None:
        parts.append(f" = {parameter.default}")

    return "".join(parts)


def _function_str(function: Function) -> str:
    """Render a function signature string (including the ``def`` keyword).

    Keyword-only parameters are sorted alphabetically for a stable output.
    A property is rendered as the attribute callers read, ``property name: type``,
    and classmethods and staticmethods are prefixed with their kind.

    Args:
        function: The function whose signature should be rendered.

    Returns:
        A string such as ``def name(param: type = default) -> return_type``.
        The ``async `` prefix is prepended for async functions, and
        ``classmethod `` or ``staticmethod `` for those kinds. A property
        gives ``property name`` or ``property name: return_type``.
    """
    if function.kind == "property":
        if function.returns is None:
            return f"property {function.name}"
        return f"property {function.name}: {function.returns}"

    params: list[str] = []

    for p in function.positional_parameters:
        params.append(_param_str(p))

    if function.var_positional is not None:
        params.append(f"*{_param_str(function.var_positional)}")
    elif function.keyword_parameters:
        params.append("*")

    sorted_kw = sorted(function.keyword_parameters, key=lambda p: (p.name, p.annotation or ""))
    for p in sorted_kw:
        params.append(_param_str(p))

    if function.var_keyword is not None:
        params.append(f"**{_param_str(function.var_keyword)}")

    prefix = f"{function.kind} " if function.kind in {"classmethod", "staticmethod"} else ""
    signature = f"{prefix}{'async def ' if function.is_async else 'def '}{function.name}({', '.join(params)})"
    if function.returns is not None:
        signature += f" -> {function.returns}"
    return signature


def _function_labels(function: Function, *, show_overload_implementation: bool) -> list[str]:
    """Render the tree labels for a function: one per overload, then the implementation.

    Args:
        function: The function to render.
        show_overload_implementation: ``True`` to show the implementation
            signature of an overloaded function after its overloads.

    Returns:
        ``[signature]`` for a function without overloads. For an overloaded
        function, one signature per overload, followed by the implementation
        signature when *show_overload_implementation* is ``True`` and the
        function is not itself one of the overloads.
    """
    if not function.overloads:
        return [_function_str(function)]

    labels = [_function_str(overload) for overload in function.overloads]
    is_overload = any(decorator.rpartition(".")[2] == "overload" for decorator in function.decorators)
    if show_overload_implementation and not is_overload:
        labels.append(_function_str(function))
    return labels


def _assignment_str(assignment: Assignment) -> str:
    """Render an assignment as ``name: annotation`` or ``name``.

    Args:
        assignment: The assignment to render.

    Returns:
        A short human-readable label for the assignment: ``name: annotation``
        when an annotation is present, otherwise the bare ``name``.
    """
    if assignment.annotation is not None:
        return f"{assignment.name}: {assignment.annotation}"

    return assignment.name


def _reference_str(reference: Reference) -> str:
    """Render an unresolved public name as the import statement that binds it.

    Args:
        reference: The reference to render.

    Returns:
        ``from module import attribute [as name]``, ``import module [as name]``,
        or ``name (unresolved)`` when no binding import was found.
    """
    if reference.module is None:
        return f"{reference.name} (unresolved)"

    if reference.attribute is not None:
        label = f"from {reference.module} import {reference.attribute}"
        bound = reference.attribute
    else:
        label = f"import {reference.module}"
        bound = reference.module.split(".")[0]

    if bound != reference.name:
        label += f" as {reference.name}"
    return label


def _render_lines(node: Package | Module | Class, prefix: str, *, show_overload_implementation: bool) -> list[str]:
    """Recursively collect tree lines for *node* using *prefix* for indentation.

    Args:
        node: The current tree node whose children should be rendered.
        prefix: The indentation prefix accumulated from parent calls.
        show_overload_implementation: Passed on to ``_children``.

    Returns:
        A list of strings, one per tree row, ready to be joined with newlines.
    """
    children = _children(node, show_overload_implementation=show_overload_implementation)
    lines: list[str] = []
    last_index = len(children) - 1

    for index, (label, child) in enumerate(children):
        connector = _LAST if index == last_index else _BRANCH
        lines.append(f"{prefix}{connector}{label}")

        if child is not None:
            extension = _BLANK if index == last_index else _PIPE
            lines.extend(
                _render_lines(child, prefix + extension, show_overload_implementation=show_overload_implementation)
            )

    return lines


def _children(
    node: Package | Module | Class,
    *,
    show_overload_implementation: bool,
) -> list[tuple[str, Package | Module | Class | None]]:
    """List the children of *node* as ordered ``(label, child_node_or_None)`` pairs.

    Leaf items (assignments, functions, references) have ``None`` as the second element
    because they have no subtree to recurse into. Container items (modules,
    subpackages, classes) carry the node itself so ``_render_lines`` can
    recurse.

    An overloaded function gives one leaf per overload signature, and its
    implementation signature only when *show_overload_implementation* is set.

    Args:
        node: A ``Package``, ``Module``, or ``Class`` to enumerate children for.
        show_overload_implementation: ``True`` to list the implementation
            signature of an overloaded function after its overloads.

    Returns:
        An ordered list of ``(label, child_or_None)`` pairs where *label* is
        the display string and *child_or_None* is the node to recurse into, or
        ``None`` for leaf items.
    """
    match node:
        case Package():
            items: list[tuple[str, Package | Module | Class | None]] = []
            for m in node.modules:
                if m.name == node.name:
                    # This is the __init__ module: hoist its contents directly
                    # at the package level rather than nesting under a spurious
                    # "module <name>" node.
                    for a in m.assignments:
                        items.append((_assignment_str(a), None))
                    for cls in m.classes:
                        items.append((f"class {cls.name}", cls))
                    for fn in m.functions:
                        items.extend(
                            (label, None)
                            for label in _function_labels(fn, show_overload_implementation=show_overload_implementation)
                        )
                    for ref in m.references:
                        items.append((_reference_str(ref), None))
                else:
                    items.append((f"module {m.name}", m))
            for sp in node.subpackages:
                items.append((f"package {sp.name}", sp))
            return items

        case Module():
            items = []
            for a in node.assignments:
                items.append((_assignment_str(a), None))
            for cls in node.classes:
                items.append((f"class {cls.name}", cls))
            for fn in node.functions:
                items.extend(
                    (label, None)
                    for label in _function_labels(fn, show_overload_implementation=show_overload_implementation)
                )
            for ref in node.references:
                items.append((_reference_str(ref), None))
            return items

        case Class():
            items = []
            for nc in node.nested_classes:
                items.append((f"class {nc.name}", nc))
            for a in node.assignments:
                items.append((_assignment_str(a), None))
            for fn in node.methods:
                items.extend(
                    (label, None)
                    for label in _function_labels(fn, show_overload_implementation=show_overload_implementation)
                )
            return items


def format_tree(api: Package | Module, *, show_overload_implementation: bool = False) -> str:
    """Render a Unicode box-drawing tree of *package*'s public API.

    An overloaded function is shown as its ``@overload`` signatures. Its
    implementation signature is hidden unless *show_overload_implementation*
    is ``True``.

    Args:
        api: The root package/module to render.
        show_overload_implementation: ``True`` to also show the implementation
            signature of each overloaded function, after its overloads.

    Returns:
        A multi-line string suitable for printing to a terminal.
    """
    header = f"package {api.name}" if isinstance(api, Package) else f"module {api.name}"
    body = _render_lines(api, prefix="", show_overload_implementation=show_overload_implementation)
    return "\n".join([header, *body])


JSON_SCHEMA_VERSION = 1
"""Version of the JSON output format, emitted as the top-level ``schema_version``.

Bump it whenever a change to the JSON output could break a consumer.
"""

_NODE_TYPES: dict[type, str] = {
    Package: "package",
    Module: "module",
    Class: "class",
    Function: "function",
    Assignment: "assignment",
    Reference: "reference",
}
"""The ``node_type`` value serialized for each model class."""


def _sort_key(obj: Any) -> str:
    """Compute a stable sort key for a plain-Python value produced by ``_to_plain``.

    Named dicts (those with a ``"name"`` key) sort by that name; everything
    else falls back to its JSON representation.

    Args:
        obj: A value already normalized by ``_to_plain``.

    Returns:
        A string used as the comparison key.
    """
    if isinstance(obj, dict) and "name" in obj:
        return str(obj["name"])
    return json.dumps(obj, sort_keys=True)


def _relative_path(path: Path, root: Path | None) -> str:
    """Render *path* as a POSIX string relative to *root*.

    Absolute paths would make snapshots depend on where the source is checked
    out, so every path is expressed relative to the analyzed root. The root
    itself becomes ``"."``.

    Args:
        path: The path to render.
        root: The analyzed root directory, or ``None`` when there is none.

    Returns:
        The relative POSIX path, or just the final path component when *path*
        is not inside *root*.
    """
    if root is not None and path.is_relative_to(root):
        return path.relative_to(root).as_posix() or "."
    return path.name or "."


def _to_plain(obj: Any, root: Path | None = None) -> Any:
    """Recursively normalise *obj* to a JSON-serializable plain Python value.

    Args:
        obj: Any Python object produced by the iceberg model layer.
        root: The analyzed root directory; ``Path`` values are rendered
            relative to it.

    Returns:
        A ``dict``, ``list``, ``str``, ``int``, ``float``, ``bool``, or
        ``None`` — all suitable for ``json.dumps``.
    """
    match obj:
        case _ if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            fields = {f.name: _to_plain(getattr(obj, f.name), root) for f in dataclasses.fields(obj)}
            node_type = _NODE_TYPES.get(type(obj))
            return fields if node_type is None else {"node_type": node_type, **fields}

        case Path():
            return _relative_path(obj, root)

        case frozenset():
            converted = [_to_plain(item, root) for item in obj]
            return sorted(converted, key=_sort_key)

        case tuple() | list():
            return [_to_plain(item, root) for item in obj]

        case _:
            return obj


def format_json(api: Package | Module) -> str:
    """Render *api* as deterministic, indented JSON.

    The top-level object starts with ``schema_version`` (see
    ``JSON_SCHEMA_VERSION``). Every package, module, class, function,
    assignment and reference object starts with a ``node_type`` field naming
    what it is; the other keys follow in model field order.

    ``frozenset`` fields are serialized as sorted lists so that output is
    stable across interpreter runs. Package paths are relative to the root
    package directory (the root itself is ``"."``), so the same source in two
    different directories gives byte-identical output.

    Args:
        api: The root package or module to serialize.

    Returns:
        A JSON string with two-space indentation and keys in a fixed order.
    """
    root = api.path if isinstance(api, Package) else None
    return json.dumps({"schema_version": JSON_SCHEMA_VERSION, **_to_plain(api, root)}, indent=2)
