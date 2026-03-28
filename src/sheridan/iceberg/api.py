"""High-level public API for sheridan-iceberg."""

__all__ = [
    "get_public_api",
]

from pathlib import Path

from sheridan.iceberg.ast_walker import base_for, load_modules, module_id, resolve_show_modules
from sheridan.iceberg.models import ModuleInfo


def get_public_api(
    path: Path | str,
    *,
    use_ast: bool = False,
) -> dict[str, ModuleInfo]:
    """Return the public API surface for a path.

    When a package's ``__init__.py`` declares ``__all__``, it is treated as the
    authoritative source of truth for the entire package; sub-modules are not
    reported separately.  Pass ``use_ast=True`` to bypass this and see every
    module's AST-inferred names.

    Args:
        path: File or directory to inspect.
        use_ast: When ``True``, ignore ``__all__`` and derive names from the AST.

    Returns:
        Mapping of dotted module name to ``ModuleInfo``.
    """
    p = Path(path)
    modules = resolve_show_modules(load_modules(p), use_ast)
    base = base_for(p)
    result: dict[str, ModuleInfo] = {}
    for info in modules:
        result[module_id(info.path, base)] = info
    return result
