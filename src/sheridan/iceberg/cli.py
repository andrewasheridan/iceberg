"""Command-line interface for sheridan-iceberg."""

__all__ = [
    "main",
]

import argparse
import json
import sys
from enum import StrEnum
from pathlib import Path

from sheridan.iceberg.ast_walker import load_modules
from sheridan.iceberg.fixer import fix_modules
from sheridan.iceberg.reporter import Issue, IssueKind, check_modules


class OutputFormat(StrEnum):
    """Supported output formats for the check command."""

    text = "text"
    json = "json"


def _render(issues: list[Issue], fmt: OutputFormat) -> str:
    """Render issues as text or JSON.

    Args:
        issues: Issues to render.
        fmt: Output format.

    Returns:
        Formatted string.
    """
    if fmt == OutputFormat.json:
        return json.dumps([i.to_dict() for i in issues], indent=2)
    return "\n".join(i.to_text() for i in issues)


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
    issues = check_modules(load_modules(path))

    if args.ignore_missing:
        issues = [i for i in issues if i.kind != IssueKind.MISSING]

    output = _render(issues, fmt)
    if output:
        print(output)

    return 1 if issues else 0


def _fix(args: argparse.Namespace) -> int:
    """Run the fix subcommand.

    Args:
        args: Parsed argument namespace.

    Returns:
        Exit code — always 0.
    """
    path = Path(args.path)
    if not path.exists():
        print(f"error: path does not exist: {path}", file=sys.stderr)
        return 2

    modules = load_modules(path)
    issues = check_modules(modules)

    if not issues:
        print("No issues found.")
        return 0

    if args.dry_run:
        for issue in issues:
            print(f"Would fix: {issue.path} ({issue.kind.value})")
    else:
        fixed = fix_modules(modules, issues)
        for p in fixed:
            print(f"Fixed: {p}")
        print(f"\n{len(fixed)} file(s) fixed.")

    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser.

    Returns:
        Configured :class:`argparse.ArgumentParser`.
    """
    parser = argparse.ArgumentParser(
        prog="iceberg",
        description="Enforce __all__ correctness in Python modules.",
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

    return parser


def main() -> None:
    """Entry point for the iceberg CLI."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "check":
        sys.exit(_check(args))
    elif args.command == "fix":
        sys.exit(_fix(args))
