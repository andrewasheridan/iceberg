"""Auto-fix __all__ declarations in Python source files."""

__all__ = [
    "fix_module",
    "fix_modules",
    "fix_needed",
]

import ast
import re
from pathlib import Path

from sheridan.iceberg.ast_walker import ModuleInfo
from sheridan.iceberg.reporter import Issue, IssueKind

_ALL_PATTERN = re.compile(
    r"^__all__\s*=\s*[\[(].*?[])]",
    re.MULTILINE | re.DOTALL,
)


def _render_all(names: list[str]) -> str:
    """Render a ``__all__`` assignment string.

    Args:
        names: Sorted list of public names.

    Returns:
        A Python source string for the ``__all__`` assignment.
    """
    if not names:
        return "__all__: list[str] = []"
    inner = ",\n    ".join(f'"{name}"' for name in sorted(names))
    return f"__all__ = [\n    {inner},\n]"


def _find_all_node(tree: ast.Module) -> ast.Assign | None:
    """Locate the ``__all__`` assignment node in the AST.

    Args:
        tree: Parsed AST of a module.

    Returns:
        The assignment node, or ``None`` if not found.
    """
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                return node
    return None


def fix_module(info: ModuleInfo, expected: list[str]) -> bool:
    """Rewrite the ``__all__`` declaration in a module file.

    If ``__all__`` is present it is replaced in-place. If absent, it is
    inserted after the module docstring (or at the top if none exists).

    Args:
        info: Parsed module information.
        expected: The correct sorted list of public names to write.

    Returns:
        ``True`` if the file was modified, ``False`` if already correct.
    """
    source = info.path.read_text(encoding="utf-8")
    new_decl = _render_all(expected)

    tree = ast.parse(source, filename=str(info.path))
    all_node = _find_all_node(tree)

    if all_node is not None:
        lines = source.splitlines(keepends=True)
        start = all_node.lineno - 1  # 0-indexed
        end = all_node.end_lineno if all_node.end_lineno is not None else start + 1
        # Preserve any trailing newline after the block
        new_lines = [*lines[:start], new_decl + "\n", *lines[end:]]
        new_source = "".join(new_lines)
    else:
        new_source = _insert_all(source, new_decl)

    if new_source == source:
        return False

    info.path.write_text(new_source, encoding="utf-8")
    return True


def _insert_all(source: str, decl: str) -> str:
    """Insert a ``__all__`` declaration into source that lacks one.

    Placement rules (in priority order):
    1. After the module docstring, if present.
    2. After leading comments/blank lines at the top of the file.

    Args:
        source: Original module source code.
        decl: The ``__all__`` declaration string to insert.

    Returns:
        Modified source with ``__all__`` inserted.
    """
    lines = source.splitlines(keepends=True)

    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Fallback: insert at line 0
        return decl + "\n\n" + source

    insert_after: int = 0

    # If the module has a docstring, insert after it
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        insert_after = tree.body[0].end_lineno or 0
    else:
        # Skip leading blank lines and comment lines
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped and not stripped.startswith("#"):
                insert_after = i
                break

    new_lines = [*lines[:insert_after], "\n", decl + "\n", *lines[insert_after:]]
    return "".join(new_lines)


def fix_modules(modules: list[ModuleInfo], issues: list[Issue]) -> list[Path]:
    """Apply ``__all__`` fixes for a list of issues.

    Matches each issue to its :class:`~sheridan.iceberg.ast_walker.ModuleInfo`
    and rewrites the file. Issues whose module cannot be found are skipped.

    Args:
        modules: Parsed module information used to look up each affected file.
        issues: Issues to fix.

    Returns:
        Paths of files that were actually modified.
    """
    module_by_path = {m.path: m for m in modules}
    fixed: list[Path] = []
    for issue in issues:
        info = module_by_path.get(issue.path)
        if info is None:
            continue
        if fix_module(info, issue.expected):
            fixed.append(issue.path)
    return fixed


def fix_needed(modules: list[ModuleInfo]) -> list[Issue]:
    """Return issues for all modules where ``__all__`` needs updating.

    Uses full bidirectional comparison: any module where ``declared_all``
    differs from ``sorted(inferred_all)`` needs fixing.  This includes both
    modules missing ``__all__`` entirely and modules whose ``__all__`` contains
    phantom names (present in ``__all__`` but absent from the AST).

    Unlike :func:`~sheridan.iceberg.reporter.check_modules`, which only reports
    names the AST considers public that are absent from ``__all__``, this
    function is used by the ``fix`` command to ensure ``__all__`` is fully
    synchronised with the AST in both directions.

    Args:
        modules: Parsed module information.

    Returns:
        List of :class:`~sheridan.iceberg.reporter.Issue` objects for modules
        that need their ``__all__`` rewritten.
    """
    targets: list[Issue] = []
    for info in modules:
        correct = sorted(info.inferred_all)
        if info.declared_all != correct:
            kind = IssueKind.missing if info.declared_all is None else IssueKind.incorrect
            targets.append(Issue(path=info.path, kind=kind, declared=info.declared_all, expected=correct))
    return targets
