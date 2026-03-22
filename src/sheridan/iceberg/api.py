"""High-level public API for sheridan-iceberg."""

__all__ = [
    "check_api",
    "fix_api",
    "get_public_api",
]

from pathlib import Path

from sheridan.iceberg.ast_walker import load_modules, resolve_show_modules
from sheridan.iceberg.fixer import fix_modules, fix_needed
from sheridan.iceberg.reporter import IssueKind, check_modules


def get_public_api(
    path: Path | str,
    *,
    use_ast: bool = False,
) -> dict[str, list[str]]:
    """Return the public API surface for a path.

    When a package's ``__init__.py`` declares ``__all__``, it is treated as the
    authoritative source of truth for the entire package; sub-modules are not
    reported separately.  Pass ``use_ast=True`` to bypass this and see every
    module's AST-inferred names.

    Args:
        path: File or directory to inspect.
        use_ast: When ``True``, ignore ``__all__`` and derive names from the AST.

    Returns:
        Mapping of dotted module name to sorted list of public names.
    """
    p = Path(path)
    modules = resolve_show_modules(load_modules(p), use_ast)
    base = p if p.is_dir() else p.parent
    result: dict[str, list[str]] = {}
    for info in modules:
        try:
            rel = info.path.relative_to(base)
            module_id = str(rel).removesuffix(".py").replace("/", ".")
            if module_id.endswith(".__init__"):
                module_id = module_id[: -len(".__init__")]
        except ValueError:
            module_id = str(info.path)
        result[module_id] = info.inferred_all if use_ast else info.effective_all
    return result


def check_api(
    path: Path | str,
    *,
    ignore_missing: bool = False,
) -> list[dict[str, object]]:
    """Check ``__all__`` correctness and return any issues found.

    Args:
        path: File or directory to check.
        ignore_missing: When ``True``, suppress IB001 (missing ``__all__``) reports.

    Returns:
        List of issue dictionaries.  Each dict contains ``code``, ``path``,
        ``kind``, ``declared``, and ``expected`` keys.  An empty list means
        no issues were found.
    """
    issues = check_modules(load_modules(Path(path)))
    if ignore_missing:
        issues = [i for i in issues if i.kind != IssueKind.MISSING]
    return [i.to_dict() for i in issues]


def fix_api(
    path: Path | str,
    *,
    dry_run: bool = False,
) -> list[Path]:
    """Fix ``__all__`` declarations in place.

    Uses full bidirectional comparison: adds missing names, removes phantom
    names, and sorts the result.

    Args:
        path: File or directory to fix.
        dry_run: When ``True``, return the paths that would be modified
            without writing any files.

    Returns:
        List of paths that were modified (or would be, if ``dry_run`` is ``True``).
    """
    modules = load_modules(Path(path))
    issues = fix_needed(modules)
    if dry_run or not issues:
        return [i.path for i in issues]
    return fix_modules(modules, issues)
