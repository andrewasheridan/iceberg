"""Command-line interface for sheridan-iceberg."""

__all__ = ["main"]

import argparse
import json
import sys
from pathlib import Path

from sheridan.iceberg.api import check_api, fix_api
from sheridan.iceberg.ast_walker import ModuleInfo, base_for, load_modules, module_id, resolve_show_modules
from sheridan.iceberg.enums import OutputFormat, ShowFormat
from sheridan.iceberg.models import ClassInfo, ClassMember, FunctionSignature, MemberKind, ParamInfo, ParamKind


def _check(args: argparse.Namespace) -> int:
    """Run the check subcommand.

    Args:
        args: Parsed argument namespace.

    Returns:
        Exit code — 0 if no issues, 1 if issues found, 2 if path missing.
    """
    path = Path(args.path)
    if not path.exists():
        print(f"error: path does not exist: {path}", file=sys.stderr)
        return 2

    fmt = OutputFormat(args.format)
    issues = check_api(path, ignore_missing=args.ignore_missing)

    output = json.dumps(issues, indent=2) if fmt is OutputFormat.json else "\n".join(str(i["message"]) for i in issues)

    if output:
        print(output)

    return 1 if issues else 0


def _fix(args: argparse.Namespace) -> int:
    """Run the fix subcommand.

    Uses full bidirectional comparison to identify modules needing an update:
    modules missing ``__all__`` entirely and modules whose ``__all__`` contains
    phantom names (present in ``__all__`` but absent from the AST) are both
    targeted.

    Args:
        args: Parsed argument namespace.

    Returns:
        Exit code — always 0.
    """
    path = Path(args.path)
    if not path.exists():
        print(f"error: path does not exist: {path}", file=sys.stderr)
        return 2

    paths = fix_api(path, dry_run=args.dry_run)

    if not paths:
        print("No issues found.")
        return 0

    for p in paths:
        if args.dry_run:
            print(f"Would fix: {p}")
        else:
            print(f"Fixed: {p}")

    if not args.dry_run:
        print(f"\n{len(paths)} file(s) fixed.")

    return 0


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


def _format_tree(modules: list[ModuleInfo], root: Path, use_ast: bool) -> str:
    """Render public API as an indented filesystem tree.

    Functions are rendered with their full signatures.  Classes are followed
    by an indented list of their public members (attributes, properties, and
    methods).

    Args:
        modules: Parsed module information.
        root: The path argument supplied to the show command.
        use_ast: When True, use ``inferred_all`` regardless of ``__all__``.

    Returns:
        Multi-line string with one entry per line.
    """
    lines: list[str] = []
    base = base_for(root)

    if root.is_dir():
        lines.append(f"{root.name}/")

    seen_dirs: set[tuple[str, ...]] = set()

    for info in modules:
        try:
            rel = info.path.relative_to(base)
        except ValueError:
            rel = info.path

        parts = rel.parts  # e.g. ('ast_walker.py',) or ('subpkg', 'mod.py')

        # Emit intermediate directory headers
        for i in range(len(parts) - 1):
            dir_key = parts[: i + 1]
            if dir_key not in seen_dirs:
                seen_dirs.add(dir_key)
                dir_depth = i + 1 if root.is_dir() else i
                lines.append(f"{'  ' * dir_depth}{parts[i]}/")

        # Module name line
        depth = len(parts)
        module_depth = depth if root.is_dir() else depth - 1
        module_name = parts[-1].removesuffix(".py")
        lines.append(f"{'  ' * module_depth}{module_name}")

        # Public names with rich info
        names = info.inferred_all if use_ast else info.effective_all
        name_depth = module_depth + 1
        for name in names:
            if sig := info.function_signatures.get(name):
                prefix = "async " if sig.is_async else ""
                lines.append(f"{'  ' * name_depth}{prefix}{name}{_render_signature(sig)}")
            elif cls := info.class_info.get(name):
                lines.append(f"{'  ' * name_depth}{name}")
                member_depth = name_depth + 1
                for member in cls.members:
                    lines.append(f"{'  ' * member_depth}{_render_member(member)}")
            else:
                lines.append(f"{'  ' * name_depth}{name}")

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
    """Build the per-name detail mapping for JSON show output.

    Only names for which rich info is available (functions and classes) are
    included.  Plain variables are omitted.

    Args:
        names: The effective public names for the module.
        info: Parsed module information containing signature and class data.

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
    return detail


def _format_show_json(modules: list[ModuleInfo], root: Path, use_ast: bool) -> str:
    """Render public API as a JSON array.

    Each entry includes a ``detail`` key with per-name signature and class
    member information for functions and classes.

    Args:
        modules: Parsed module information.
        root: The path argument supplied to the show command.
        use_ast: When True, use ``inferred_all`` regardless of ``__all__``.

    Returns:
        JSON string — an array of objects with ``module``, ``path``,
        ``source``, ``names``, and ``detail`` keys.
    """
    base = base_for(root)
    result = []
    for info in modules:
        names = info.inferred_all if use_ast else info.effective_all
        source = "ast" if (use_ast or info.declared_all is None) else "__all__"
        entry: dict[str, object] = {
            "module": module_id(info.path, base),
            "path": str(info.path),
            "source": source,
            "names": names,
            "detail": _build_detail(names, info),
        }
        result.append(entry)
    return json.dumps(result, indent=2)


def _show(args: argparse.Namespace) -> int:
    """Run the show subcommand.

    Args:
        args: Parsed argument namespace.

    Returns:
        Exit code — 0 on success, 2 if path missing.
    """
    path = Path(args.path)
    if not path.exists():
        print(f"error: path does not exist: {path}", file=sys.stderr)
        return 2

    fmt = ShowFormat(args.format)
    use_ast: bool = args.use_ast
    modules = resolve_show_modules(load_modules(path), use_ast)

    if not modules:
        return 0

    if fmt is ShowFormat.json:
        print(_format_show_json(modules, path, use_ast))
    else:
        output = _format_tree(modules, path, use_ast)
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
        description="Inspect and enforce __all__ in Python modules.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    # check
    check_p = subparsers.add_parser("check", help="Check Python modules under PATH for __all__ issues.")
    check_p.add_argument("path", metavar="PATH", help="File or directory to check.")
    check_p.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text).",
    )
    check_p.add_argument(
        "--ignore-missing",
        action="store_true",
        default=False,
        help="Do not report modules missing __all__.",
    )

    # fix
    fix_p = subparsers.add_parser("fix", help="Auto-fix __all__ declarations in modules under PATH.")
    fix_p.add_argument("path", metavar="PATH", help="File or directory to fix.")
    fix_p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would change without writing files.",
    )

    # show
    show_p = subparsers.add_parser("show", help="Report the public API of Python modules under PATH.")
    show_p.add_argument("path", metavar="PATH", help="File or directory to inspect.")
    show_p.add_argument(
        "--format",
        choices=["tree", "json"],
        default="tree",
        help="Output format (default: tree).",
    )
    show_p.add_argument(
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

    if args.command == "check":
        sys.exit(_check(args))
    elif args.command == "fix":
        sys.exit(_fix(args))
    elif args.command == "show":
        sys.exit(_show(args))
