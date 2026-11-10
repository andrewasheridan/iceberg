"""Format iceberg snapshots of a public API as a tree or as JSON."""

__all__ = ["format_diagnostic", "format_json", "format_tree"]

import dataclasses
import json
from pathlib import Path
from typing import Any

from sheridan.iceberg._models import (
    Assignment,
    Class,
    Diagnostic,
    Function,
    Module,
    Package,
    Parameter,
    Reference,
)

_BRANCH = "├── "
"""The connector string for a tree node that is not the last child."""

_LAST = "└── "
"""The connector string for the last child of a tree node."""

_PIPE = "│   "
"""The vertical line that continues the tree when a parent has more siblings below it."""

_BLANK = "    "
"""The blank indent below the last child of a tree node."""


def _param_str(parameter: Parameter) -> str:
    """Render a single parameter as ``name: annotation = default``.

    Args:
        parameter: The parameter to render.

    Returns:
        A string in the form ``name``, ``name: annotation``,
        ``name = default`` or ``name: annotation = default``. The form
        agrees with the fields that have a value.
    """
    parts = [parameter.name]

    if parameter.annotation is not None:
        parts.append(f": {parameter.annotation}")

    if parameter.default is not None:
        parts.append(f" = {parameter.default}")

    return "".join(parts)


def _function_str(function: Function) -> str:
    """Render the signature of a function as a string (with the ``def`` keyword).

    The function sorts keyword-only parameters alphabetically, so that the
    output is stable. It shows a property as the attribute that callers read,
    ``property name: type``. It puts the kind before classmethods and
    staticmethods.

    Args:
        function: The function to render.

    Returns:
        A string such as ``def name(param: type = default) -> return_type``.
        Async functions get the prefix ``async ``. Classmethods and
        staticmethods get the prefix ``classmethod `` or ``staticmethod ``. A
        property gives ``property name`` or ``property name: return_type``.
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

    sorted_kw = sorted(function.keyword_parameters, key=lambda p: p.name)
    for p in sorted_kw:
        params.append(_param_str(p))

    if function.var_keyword is not None:
        params.append(f"**{_param_str(function.var_keyword)}")

    prefix = f"{function.kind} " if function.kind in {"classmethod", "staticmethod"} else ""
    keyword = "async def" if function.is_async else "def"
    signature = f"{prefix}{keyword} {function.name}({', '.join(params)})"

    if function.returns is not None:
        signature += f" -> {function.returns}"

    return signature


def _function_labels(function: Function, *, show_overload_implementation: bool) -> list[str]:
    """Render the tree labels of a function: one for each overload, then the implementation.

    Args:
        function: The function to render.
        show_overload_implementation: ``True`` to show the signature of the
            implementation of an overloaded function after its overloads.

    Returns:
        ``[signature]`` for a function without overloads. For an overloaded
        function, one signature for each overload. Then the signature of the
        implementation, if *show_overload_implementation* is ``True`` and the
        function is not one of the overloads.
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
        A short label for the assignment that people can read. If the
        assignment has an annotation, the label is ``name: annotation``. If
        not, the label is the bare ``name``.
    """
    if assignment.annotation is not None:
        return f"{assignment.name}: {assignment.annotation}"

    return assignment.name


def _class_str(cls: Class) -> str:
    """Render a class header for tree output.

    Args:
        cls: The class to render.

    Returns:
        A string such as ``class Foo`` or ``class Foo(Base, metaclass=Meta)``.
    """
    arguments = (*cls.bases, *cls.keywords)
    if not arguments:
        return f"class {cls.name}"

    return f"class {cls.name}({', '.join(arguments)})"


def _reference_str(reference: Reference) -> str:
    """Render an unresolved public name as the import statement that binds it.

    Args:
        reference: The reference to render.

    Returns:
        ``from module import attribute [as name]``, ``import module [as name]``,
        or ``name (unresolved)`` if no import binds the name.
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
    """Collect the tree lines for *node* recursively, with *prefix* as the indent.

    Args:
        node: The current tree node. The function renders its children.
        prefix: The indent prefix that the parent calls collected.
        show_overload_implementation: The function gives this value to ``_children``.

    Returns:
        A list of strings, one for each tree row. You can join them with newlines.
    """
    children = _children(node, show_overload_implementation=show_overload_implementation)
    lines: list[str] = []
    last_index = len(children) - 1

    for index, (label, child) in enumerate(children):
        connector = _LAST if index == last_index else _BRANCH
        lines.append(f"{prefix}{connector}{label}")

        if child is not None:
            extension = _BLANK if index == last_index else _PIPE
            child_lines = _render_lines(
                child, prefix + extension, show_overload_implementation=show_overload_implementation
            )
            lines.extend(child_lines)

    return lines


def _children(
    node: Package | Module | Class,
    *,
    show_overload_implementation: bool,
) -> list[tuple[str, Package | Module | Class | None]]:
    """List the children of *node* as ordered ``(label, child_node_or_None)`` pairs.

    Leaf items (assignments, functions, references) have ``None`` as the
    second element, because they have no subtree. Container items (modules,
    subpackages, classes) hold the node. Thus, ``_render_lines`` can go into
    the node recursively.

    An overloaded function gives one leaf for each overload signature. It
    gives the signature of its implementation only if
    *show_overload_implementation* is ``True``.

    Args:
        node: A ``Package``, ``Module`` or ``Class``. The function lists its children.
        show_overload_implementation: ``True`` to list the signature of the
            implementation of an overloaded function after its overloads.

    Returns:
        An ordered list of ``(label, child_or_None)`` pairs. *label* is the
        string to show. *child_or_None* is the node to go into recursively, or
        ``None`` for leaf items.
    """
    items: list[tuple[str, Package | Module | Class | None]] = []

    match node:
        case Package():
            for m in node.modules:
                if m.name == node.name:
                    # This is the __init__ module. Put its contents directly at
                    # the package level, not below an unnecessary
                    # "module <name>" node.
                    items.extend(_module_items(m, show_overload_implementation=show_overload_implementation))
                else:
                    items.append((f"module {m.name}", m))

            for sp in node.subpackages:
                items.append((f"package {sp.name}", sp))

        case Module():
            items.extend(_module_items(node, show_overload_implementation=show_overload_implementation))

        case Class():
            for nc in node.nested_classes:
                items.append((_class_str(nc), nc))

            for a in node.assignments:
                items.append((_assignment_str(a), None))

            for fn in node.methods:
                for label in _function_labels(fn, show_overload_implementation=show_overload_implementation):
                    items.append((label, None))

    return items


def _module_items(
    module: Module,
    *,
    show_overload_implementation: bool,
) -> list[tuple[str, Package | Module | Class | None]]:
    """List the members of *module* as ``(label, child_node_or_None)`` pairs.

    Args:
        module: The module with the members to list.
        show_overload_implementation: The function gives this value to ``_function_labels``.

    Returns:
        The assignments, classes, functions and references of the module, in that order.
    """
    items: list[tuple[str, Package | Module | Class | None]] = []

    for a in module.assignments:
        items.append((_assignment_str(a), None))

    for cls in module.classes:
        items.append((_class_str(cls), cls))

    for fn in module.functions:
        for label in _function_labels(fn, show_overload_implementation=show_overload_implementation):
            items.append((label, None))

    for ref in module.references:
        items.append((_reference_str(ref), None))

    return items


def format_tree(api: Package | Module, *, show_overload_implementation: bool = False) -> str:
    """Render the public API of *api* as a tree of Unicode box-drawing characters.

    The tree shows an overloaded function as its ``@overload`` signatures. It
    does not show the signature of the implementation, unless
    *show_overload_implementation* is ``True``.

    Args:
        api: The root package or module to render.
        show_overload_implementation: ``True`` to also show the signature of
            the implementation of each overloaded function, after its overloads.

    Returns:
        A string with many lines, for a terminal.
    """
    header = f"package {api.name}" if isinstance(api, Package) else f"module {api.name}"
    body = _render_lines(api, prefix="", show_overload_implementation=show_overload_implementation)

    return "\n".join([header, *body])


JSON_SCHEMA_VERSION = 2
"""The version of the JSON output format. The output gives it as the top-level ``schema_version``.

If a change to the JSON output can break a program that reads it, increase this
value. Then update ``docs/schema/iceberg.schema.json`` to agree with it.
"""

_NODE_TYPES: dict[type, str] = {
    Package: "package",
    Module: "module",
    Class: "class",
    Function: "function",
    Assignment: "assignment",
    Reference: "reference",
}
"""The ``node_type`` value that the JSON output gives for each model class."""


def _sort_key(obj: Any) -> str:
    """Compute a stable sort key for a plain Python value from ``_to_plain``.

    The function sorts dicts with a ``"name"`` key by that name. It sorts all
    other values by their JSON representation.

    Args:
        obj: A value that ``_to_plain`` normalized.

    Returns:
        A string to use as the comparison key.
    """
    if isinstance(obj, dict) and "name" in obj:
        return str(obj["name"])

    return json.dumps(obj, sort_keys=True)


def _relative_path(path: Path, root: Path | None) -> str:
    """Render *path* as a POSIX string relative to *root*.

    With absolute paths, a snapshot changes when the location of the source
    changes. Thus, the function gives each path relative to the analyzed root.
    The root becomes ``"."``.

    Args:
        path: The path to render.
        root: The analyzed root directory, or ``None`` if there is no root.

    Returns:
        The relative POSIX path. If *path* is not in *root*, only the last
        component of the path.
    """
    if root is not None and path.is_relative_to(root):
        return path.relative_to(root).as_posix()

    return path.name or "."


def _to_plain(obj: Any, root: Path | None = None) -> Any:
    """Convert *obj* recursively to a plain Python value that JSON can hold.

    Args:
        obj: A Python object from the iceberg model layer.
        root: The analyzed root directory. The function renders ``Path``
            values relative to it.

    Returns:
        A ``dict``, ``list``, ``str``, ``int``, ``float``, ``bool`` or
        ``None``. ``json.dumps`` accepts all these types.
    """
    match obj:
        case _ if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            fields = {f.name: _to_plain(getattr(obj, f.name), root) for f in dataclasses.fields(obj)}

            node_type = _NODE_TYPES.get(type(obj))
            if node_type is None:
                return fields

            return {"node_type": node_type, **fields}

        case Path():
            return _relative_path(obj, root)

        case frozenset():
            converted = [_to_plain(item, root) for item in obj]
            return sorted(converted, key=_sort_key)

        case tuple() | list():
            return [_to_plain(item, root) for item in obj]

        case _:
            return obj


def format_diagnostic(diagnostic: Diagnostic) -> str:
    """Render *diagnostic* as one ``path:line: severity: message`` line.

    Args:
        diagnostic: The diagnostic to render.

    Returns:
        The line. If the line number is not known, the line has no ``:line`` part.
    """
    location = str(diagnostic.path)
    if diagnostic.lineno is not None:
        location += f":{diagnostic.lineno}"

    return f"{location}: {diagnostic.severity}: {diagnostic.message}"


def format_json(api: Package | Module, diagnostics: tuple[Diagnostic, ...] | None = None) -> str:
    """Render *api* as deterministic, indented JSON.

    The top-level object starts with ``schema_version`` (see
    ``JSON_SCHEMA_VERSION``). Each package, module, class, function,
    assignment and reference object starts with a ``node_type`` field. This
    field tells the type of the object. The other keys come after it, in the
    order of the model fields.

    The function writes ``frozenset`` fields as sorted lists. Thus, the output
    is the same for each run of the interpreter. Package paths are relative to
    the root package directory (the root is ``"."``). Thus, the same source in
    two different directories gives output with the same bytes.

    If you give *diagnostics*, they come after the API, in a top-level
    ``diagnostics`` key. Their paths are also relative to the root package
    directory.

    Args:
        api: The root package or module to serialize.
        diagnostics: The diagnostics to include, or ``None`` to leave out the key.

    Returns:
        A JSON string with two-space indentation and keys in a fixed order.
    """
    root = api.path if isinstance(api, Package) else None
    output = {"schema_version": JSON_SCHEMA_VERSION, **_to_plain(api, root)}

    if diagnostics is not None:
        output["diagnostics"] = _to_plain(diagnostics, root)

    return json.dumps(output, indent=2)
