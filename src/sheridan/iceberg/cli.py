"""Command-line interface for sheridan-iceberg."""

import json
import sys
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer

from sheridan.iceberg.ast_walker import ModuleInfo, walk_module, walk_path
from sheridan.iceberg.fixer import fix_module
from sheridan.iceberg.reporter import Issue, IssueKind, report

__all__ = [
    "app",
]


class OutputFormat(str, Enum):
    """Supported output formats for the check command."""

    text = "text"
    json = "json"


app = typer.Typer(
    name="iceberg",
    help="Enforce __all__ correctness in Python modules.",
    no_args_is_help=True,
)


def _load_modules(path: Path) -> list[ModuleInfo]:
    """Load module info from a file or directory.

    Args:
        path: A ``.py`` file or a directory to walk recursively.

    Returns:
        List of parsed :class:`~sheridan.iceberg.ast_walker.ModuleInfo`.
    """
    if path.is_dir():
        return walk_path(path)
    return [walk_module(path)]


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


@app.command("check")
def check_cmd(
    path: Annotated[Path, typer.Argument(exists=True, help="File or directory to check.")],
    fmt: Annotated[OutputFormat, typer.Option("--format", help="Output format.")] = OutputFormat.text,
    ignore_missing: Annotated[bool, typer.Option("--ignore-missing", help="Do not report modules missing __all__.")] = False,
) -> None:
    """Check Python modules under PATH for __all__ issues.

    Exits with code 1 if any issues are found.
    """
    modules = _load_modules(path)
    issues, _ = report(modules, fmt=fmt.value)

    if ignore_missing:
        issues = [i for i in issues if i.kind != IssueKind.MISSING]

    output = _render(issues, fmt)
    if output:
        typer.echo(output)

    if issues:
        raise typer.Exit(code=1)


@app.command("fix")
def fix_cmd(
    path: Annotated[Path, typer.Argument(exists=True, help="File or directory to fix.")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would change without writing files.")] = False,
) -> None:
    """Auto-fix __all__ declarations in modules under PATH."""
    modules = _load_modules(path)
    issues, _ = report(modules)

    if not issues:
        typer.echo("No issues found.")
        return

    module_by_path = {m.path: m for m in modules}
    fixed = 0

    for issue in issues:
        info = module_by_path.get(issue.path)
        if info is None:
            continue
        if dry_run:
            typer.echo(f"Would fix: {issue.path} ({issue.kind.value})")
        elif fix_module(info, issue.expected):
            typer.echo(f"Fixed: {issue.path}")
            fixed += 1

    if not dry_run:
        typer.echo(f"\n{fixed} file(s) fixed.")
