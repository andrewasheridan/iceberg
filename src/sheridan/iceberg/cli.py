"""Command-line interface for sheridan-iceberg."""

__all__ = ["main"]

import argparse
import json
import sys
from pathlib import Path

from sheridan.iceberg import get_public_api
from sheridan.iceberg.ast_walker import ModuleInfo
from sheridan.iceberg.enums import MemberKind, ParamKind, ShowFormat
from sheridan.iceberg.models import ClassInfo, ClassMember, FunctionSignature, ParamInfo


def _render_param(param: ParamInfo) -> str:
    """Render a single parameter as a Python-style string.

    Args:
        param: Parameter information.

    Returns:
        Formatted parameter string, e.g. ``"x: int = ..."``.
    """
    prefix = ""
    if param.kind is ParamKind.var_positional:
        prefix = "*"
    elif param.kind is ParamKind.var_keyword:
        prefix = "**"
    result = f"{prefix}{param.name}"
    if param.annotation:
        result += f": {param.annotation}"
    if param.has_default and param.kind not in (ParamKind.var_positional, ParamKind.var_keyword):
        result += " = ..."
    return result


def _render_signature(sig: FunctionSignature) -> str:
    """Render a :class:`FunctionSignature` as a Python-style ``(params) → return`` string.

    Inserts ``/`` after positional-only parameters and ``*`` before keyword-only
    parameters when no ``*args`` is present.

    Args:
        sig: The function signature to render.

    Returns:
        Formatted signature string, e.g. ``"(x: int, y: str = ...) → bool"``.
    """
    parts: list[str] = []
    after_pos_only = False
    added_star = False

    for param in sig.params:
        if param.kind is not ParamKind.positional_only and after_pos_only:
            parts.append("/")
            after_pos_only = False
        match param.kind:
            case ParamKind.positional_only:
                parts.append(_render_param(param))
                after_pos_only = True
            case ParamKind.positional_or_keyword | ParamKind.var_keyword:
                parts.append(_render_param(param))
            case ParamKind.var_positional:
                added_star = True
                parts.append(_render_param(param))
            case ParamKind.keyword_only:
                if not added_star:
                    parts.append("*")
                    added_star = True
                parts.append(_render_param(param))

    if after_pos_only:
        parts.append("/")

    result = f"({', '.join(parts)})"
    if sig.return_annotation:
        result += f" \u2192 {sig.return_annotation}"
    return result


def _render_member(member: ClassMember) -> str:
    """Render a :class:`ClassMember` as a human-readable string.

    Args:
        member: The class member to render.

    Returns:
        Formatted member string appropriate for tree output.
    """
    match member.kind:
        case MemberKind.class_var | MemberKind.instance_attr:
            if member.annotation:
                return f"{member.name}: {member.annotation}"
            return member.name
        case MemberKind.property:
            if member.signature and member.signature.return_annotation:
                return f"{member.name} (property) \u2192 {member.signature.return_annotation}"
            return f"{member.name} (property)"
        case MemberKind.classmethod | MemberKind.staticmethod:
            label = member.kind.value  # "classmethod" or "staticmethod"
            if member.signature:
                return f"{label} {member.name}{_render_signature(member.signature)}"
            return f"{label} {member.name}"
        case MemberKind.method:
            if member.signature:
                prefix = "async " if member.signature.is_async else ""
                return f"{prefix}{member.name}{_render_signature(member.signature)}"
            return member.name


def _format_tree(
    modules: dict[str, ModuleInfo],
    use_ast: bool,
    root_name: str | None = None,
) -> str:
    """Render public API as an indented filesystem tree.

    Functions are rendered with their full signatures.  Classes are followed
    by an indented list of their public members (attributes, properties, and
    methods).

    Args:
        modules: Parsed module information.
        use_ast: When True, use ``inferred_all`` regardless of ``__all__``.
        root_name: Optional package name to display as the root header line.
            When provided, all module lines are indented one extra level beneath it.

    Returns:
        Multi-line string with one entry per line.
    """
    lines: list[str] = []
    printed_packages: set[str] = set()

    for mid, info in modules.items():
        # Subpackage __init__ files have their .__init__ suffix stripped by
        # module_id().  Restore it so the traversal places the module leaf
        # inside the correct package directory line (e.g. "formats/__init__"
        # appears under "formats/" rather than colliding with a bare "formats"
        # leaf produced by other modules whose IDs start with "formats.").
        display_id = mid + ".__init__" if info.path.name == "__init__.py" and mid != "__init__" else mid

        parts = display_id.split(".")
        # Emit a `pkg/` header for each ancestor package not yet printed.
        for depth, part in enumerate(parts[:-1]):
            pkg_key = ".".join(parts[: depth + 1])
            if pkg_key not in printed_packages:
                lines.append("  " * depth + part + "/")
                printed_packages.add(pkg_key)
        # Emit the module leaf line.
        mod_depth = len(parts) - 1
        lines.append("  " * mod_depth + parts[-1])
        # Emit public names for this module.
        names = info.inferred_all if use_ast else info.effective_all
        name_depth = mod_depth + 1
        for name in names:
            if sig := info.function_signatures.get(name):
                async_prefix = "async " if sig.is_async else ""
                lines.append("  " * name_depth + async_prefix + name + _render_signature(sig))
            elif cls := info.class_info.get(name):
                lines.append("  " * name_depth + name)
                for member in cls.members:
                    lines.append("  " * (name_depth + 1) + _render_member(member))
            elif name in info.variable_types:
                ann = info.variable_types[name]
                if ann is not None:
                    lines.append("  " * name_depth + f"{name}: {ann}")
                else:
                    lines.append("  " * name_depth + f"{name} (untyped)")
            else:
                lines.append("  " * name_depth + name)

    if root_name is not None:
        lines = [root_name] + ["  " + line for line in lines]

    return "\n".join(lines)


def _sig_to_dict(sig: FunctionSignature) -> dict[str, object]:
    """Serialize a :class:`FunctionSignature` to a JSON-compatible dict.

    Args:
        sig: Signature to serialize.

    Returns:
        Dict with ``params``, ``return_annotation``, and ``is_async`` keys.
    """
    return {
        "params": [
            {
                "name": p.name,
                "annotation": p.annotation,
                "has_default": p.has_default,
                "kind": p.kind.value,
            }
            for p in sig.params
        ],
        "return_annotation": sig.return_annotation,
        "is_async": sig.is_async,
    }


def _member_to_dict(member: ClassMember) -> dict[str, object]:
    """Serialize a :class:`ClassMember` to a JSON-compatible dict.

    Args:
        member: Member to serialize.

    Returns:
        Dict with ``name``, ``kind``, and optional ``annotation``/``signature`` keys.
    """
    d: dict[str, object] = {"name": member.name, "kind": member.kind.value}
    if member.annotation is not None:
        d["annotation"] = member.annotation
    if member.signature is not None:
        d["signature"] = _sig_to_dict(member.signature)
    return d


def _class_info_to_dict(cls: ClassInfo) -> dict[str, object]:
    """Serialize a :class:`ClassInfo` to a JSON-compatible dict.

    Args:
        cls: Class info to serialize.

    Returns:
        Dict with ``kind``, ``bases``, and ``members`` keys.
    """
    return {
        "kind": "class",
        "bases": cls.bases,
        "members": [_member_to_dict(m) for m in cls.members],
    }


def _build_detail(names: list[str], info: ModuleInfo) -> dict[str, object]:
    """Build the per-name detail mapping for JSON output.

    Functions, classes, and variables are all included.  Names for which no
    rich info is available are omitted (bare fallback names from the AST that
    do not appear in any of the three info dicts).

    Args:
        names: The effective public names for the module.
        info: Parsed module information containing signature, class, and
            variable data.

    Returns:
        Dict mapping each name with rich info to its serialized detail.
    """
    detail: dict[str, object] = {}
    for name in names:
        if sig := info.function_signatures.get(name):
            detail[name] = {
                "kind": "async function" if sig.is_async else "function",
                "signature": _sig_to_dict(sig),
            }
        elif cls := info.class_info.get(name):
            detail[name] = _class_info_to_dict(cls)
        elif name in info.variable_types:
            detail[name] = {"kind": "variable", "annotation": info.variable_types[name]}
    return detail


def _format_show_json(modules: dict[str, ModuleInfo], use_ast: bool) -> str:
    """Render public API as a JSON array.

    Each entry includes a ``detail`` key with per-name signature and class
    member information for functions and classes.

    Args:
        modules: Parsed module information.
        use_ast: When True, use ``inferred_all`` regardless of ``__all__``.

    Returns:
        JSON string — an array of objects with ``module``, ``path``,
        ``source``, ``names``, and ``detail`` keys.
    """
    result = []
    for module_id, info in modules.items():
        names = info.inferred_all if use_ast else info.effective_all
        source = "ast" if (use_ast or info.declared_all is None) else "__all__"
        entry: dict[str, object] = {
            "module": module_id,
            "path": str(info.path),
            "source": source,
            "names": names,
            "detail": _build_detail(names, info),
        }
        result.append(entry)
    return json.dumps(result, indent=2)


def _show(args: argparse.Namespace) -> int:
    """Run the show logic for the root command.

    Args:
        args: Parsed argument namespace.

    Returns:
        Exit code — 0 on success, 2 if path missing.
    """
    path = Path(args.path)
    if not path.exists():
        print(f"error: path does not exist: {path}", file=sys.stderr)
        return 2

    use_ast: bool = args.use_ast
    result = get_public_api(path, use_ast=use_ast)

    if not result:
        return 0

    fmt = ShowFormat(args.format)

    if fmt is ShowFormat.json:
        print(_format_show_json(result, use_ast))
    else:
        root_name = path.name if path.is_dir() else None
        output = _format_tree(result, use_ast, root_name=root_name)
        if output:
            print(output)

    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser.

    Returns:
        Configured :class:`argparse.ArgumentParser`.
    """
    parser = argparse.ArgumentParser(
        prog="iceberg",
        description="Report the public API surface of Python modules.",
    )
    parser.add_argument("path", metavar="PATH", help="File or directory to inspect.")
    parser.add_argument(
        "--format",
        choices=["tree", "json"],
        default="tree",
        help="Output format (default: tree).",
    )
    parser.add_argument(
        "--use-ast",
        action="store_true",
        default=False,
        help="Ignore __all__ and always derive the public API from the AST.",
    )
    return parser


def main() -> None:
    """Entry point for the iceberg CLI."""
    parser = _build_parser()
    args = parser.parse_args()
    sys.exit(_show(args))
