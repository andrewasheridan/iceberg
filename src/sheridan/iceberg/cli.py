"""Command-line interface for sheridan-iceberg."""

__all__: list[str] = []

import argparse
import json
import sys
from enum import StrEnum
from pathlib import Path

from sheridan.iceberg.api import check_api, fix_api
from sheridan.iceberg.ast_walker import ModuleInfo, base_for, load_modules, module_id, resolve_show_modules


class _OutputFormat(StrEnum):
    """Supported output formats for the check command."""

    text = "text"
    json = "json"


class _ShowFormat(StrEnum):
    """Supported output formats for the show command."""

    tree = "tree"
    json = "json"


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

    fmt = _OutputFormat(args.format)
    issues = check_api(path, ignore_missing=args.ignore_missing)

    output = json.dumps(issues, indent=2) if fmt == _OutputFormat.json else "\n".join(str(i["message"]) for i in issues)

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


def _format_tree(modules: list[ModuleInfo], root: Path, use_ast: bool) -> str:
    """Render public API as an indented filesystem tree.

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

        # Public names
        names = info.inferred_all if use_ast else info.effective_all
        name_depth = module_depth + 1
        for name in names:
            lines.append(f"{'  ' * name_depth}{name}")

    return "\n".join(lines)


def _format_show_json(modules: list[ModuleInfo], root: Path, use_ast: bool) -> str:
    """Render public API as a JSON array.

    Args:
        modules: Parsed module information.
        root: The path argument supplied to the show command.
        use_ast: When True, use ``inferred_all`` regardless of ``__all__``.

    Returns:
        JSON string — an array of objects with ``module``, ``path``,
        ``source``, and ``names`` keys.
    """
    base = base_for(root)
    result = []
    for info in modules:
        names = info.inferred_all if use_ast else info.effective_all
        source = "ast" if (use_ast or info.declared_all is None) else "__all__"
        result.append(
            {
                "module": module_id(info.path, base),
                "path": str(info.path),
                "source": source,
                "names": names,
            }
        )
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

    fmt = _ShowFormat(args.format)
    use_ast: bool = args.use_ast
    modules = resolve_show_modules(load_modules(path), use_ast)

    if not modules:
        return 0

    if fmt == _ShowFormat.json:
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
