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
)

# ---------------------------------------------------------------------------
# Tree formatter
# ---------------------------------------------------------------------------

_BRANCH = "├── "
_LAST = "└── "
_PIPE = "│   "
_BLANK = "    "


def _param_str(p: Parameter) -> str:
    """Render a single parameter as ``name: annotation = default``."""
    parts = [p.name]
    if p.annotation is not None:
        parts.append(f": {p.annotation}")
    if p.default is not None:
        parts.append(f" = {p.default}")
    return "".join(parts)


def _signature(fn: Function) -> str:
    """Render a function signature string (without the ``def`` keyword)."""
    params: list[str] = []

    for p in fn.positional_parameters:
        params.append(_param_str(p))

    if fn.var_positional is not None:
        params.append(f"*{_param_str(fn.var_positional)}")
    elif fn.keyword_parameters:
        params.append("*")

    sorted_kw = sorted(
        fn.keyword_parameters,
        key=lambda p: (p.name, p.annotation or ""),
    )
    for p in sorted_kw:
        params.append(_param_str(p))

    if fn.var_keyword is not None:
        params.append(f"**{_param_str(fn.var_keyword)}")

    sig = f"{'async ' if fn.is_async else ''}{fn.name}({', '.join(params)})"
    if fn.returns is not None:
        sig += f" -> {fn.returns}"
    return sig


def _assignment_str(a: Assignment) -> str:
    """Render an assignment as ``name: annotation`` or ``name = value``."""
    if a.annotation is not None:
        return f"{a.name}: {a.annotation}"
    if a.value_repr is not None:
        return f"{a.name} = {a.value_repr}"
    return a.name


def _render_lines(node: Package | Module | Class, prefix: str) -> list[str]:
    """Recursively collect tree lines for *node* using *prefix* for indentation."""
    children = _children(node)
    lines: list[str] = []
    last_idx = len(children) - 1

    for idx, (label, child) in enumerate(children):
        connector = _LAST if idx == last_idx else _BRANCH
        lines.append(f"{prefix}{connector}{label}")

        if child is not None:
            extension = _BLANK if idx == last_idx else _PIPE
            lines.extend(_render_lines(child, prefix + extension))

    return lines


def _children(
    node: Package | Module | Class,
) -> list[tuple[str, Package | Module | Class | None]]:
    """Return an ordered list of ``(label, child_node_or_None)`` pairs."""
    match node:
        case Package():
            items: list[tuple[str, Package | Module | Class | None]] = []
            for m in node.modules:
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
                items.append((_signature(fn), None))
            return items

        case Class():
            items = []
            for nc in node.nested_classes:
                items.append((f"class {nc.name}", nc))
            for a in node.assignments:
                items.append((_assignment_str(a), None))
            for fn in node.methods:
                items.append((_signature(fn), None))
            return items


def format_tree(package: Package) -> str:
    """Render a Unicode box-drawing tree of *package*'s public API.

    Args:
        package: The root package to render.

    Returns:
        A multi-line string suitable for printing to a terminal.
    """
    header = f"package {package.name}"
    body = _render_lines(package, prefix="")
    return "\n".join([header, *body])


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------


def _to_plain(obj: object) -> Any:
    """Recursively normalise *obj* to a JSON-serialisable plain Python value.

    Args:
        obj: Any Python object produced by the iceberg model layer.

    Returns:
        A ``dict``, ``list``, ``str``, ``int``, ``float``, ``bool``, or
        ``None`` — all suitable for ``json.dumps``.
    """
    match obj:
        case _ if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return {f.name: _to_plain(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
        case Path():
            return str(obj)
        case frozenset():
            converted = [_to_plain(item) for item in obj]
            return sorted(
                converted,
                key=lambda x: x["name"] if isinstance(x, dict) and "name" in x else json.dumps(x, sort_keys=True),
            )
        case tuple() | list():
            return [_to_plain(item) for item in obj]
        case _:
            return obj


def format_json(package: Package) -> str:
    """Render *package* as deterministic, indented JSON.

    ``frozenset`` fields are serialised as sorted lists so that output is
    stable across interpreter runs.

    Args:
        package: The root package to serialise.

    Returns:
        A JSON string with two-space indentation and sorted keys.
    """
    return json.dumps(_to_plain(package), indent=2)
