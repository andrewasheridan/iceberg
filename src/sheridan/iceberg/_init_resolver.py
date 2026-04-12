"""Resolver for ``__init__.py`` re-export declarations.

``visit_module`` (in ``_visitor.py``) treats an init file as a plain module and
captures only locally-defined names.  This module runs on top of that to
resolve ``from .sibling import X`` style re-exports so the returned ``Module``
contains the actual ``Function`` / ``Class`` / ``Assignment`` objects from the
sibling module rather than nothing at all.

Architectural split
-------------------
Subpackage visibility (whether a sub-package appears in the parent's public
surface) is controlled by ``Config.include_subpackages_in_all`` and is the
orchestrator's responsibility.  This resolver returns only the init module's
own ``Module``; it never synthesises placeholder entries for subpackages.
Callers must assemble ``Package.subpackages`` separately.
"""

__all__ = ["ResolveReport", "resolve_init"]

import ast
from collections.abc import Mapping

from sheridan.iceberg._config import Config
from sheridan.iceberg._exceptions import ParseError
from sheridan.iceberg._models import Assignment, Class, Function, Module, ResolveReport
from sheridan.iceberg._utilities import extract_all, infer_all
from sheridan.iceberg._visitor import visit_module

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_init(
    init_source: str,
    dotted_package: str,
    sibling_modules: Mapping[str, Module],
    subpackage_names: frozenset[str],
    config: Config,
) -> tuple[Module, ResolveReport]:
    """Resolve an ``__init__.py`` source into a ``Module`` with re-exports attached.

    Parses *init_source*, determines the public name set (via ``__all__`` or
    the underscore-prefix rule), then for each public name attempts to resolve
    it to a ``Function``, ``Class``, or ``Assignment``:

    1. If the name was imported from a known sibling module, look it up on that
       sibling's ``Module`` object and attach the resolved object.
    2. If the name is defined locally in the init file, use whatever
       ``visit_module`` captured.
    3. If the name cannot be resolved from either source, record it in
       ``ResolveReport.unresolved`` — no exception is raised.

    ``config.include_subpackages_in_all`` is intentionally ignored here;
    subpackage visibility is the orchestrator's concern.

    Args:
        init_source: Raw Python source text of the ``__init__.py`` file.
        dotted_package: Fully-qualified package name (e.g. ``"my_pkg.sub"``).
        sibling_modules: Mapping from dotted module name to ``Module`` for all
            modules visible to this init file.
        subpackage_names: Names of direct sub-packages under this package.
            Used only to avoid recording subpackage names as unresolved — they
            are not attached to the returned ``Module``.
        config: Iceberg runtime configuration.

    Returns:
        A two-tuple of ``(module, report)`` where *module* is the resolved
        ``Module`` for the init file and *report* records any names that could
        not be resolved.

    Raises:
        ParseError: When *init_source* cannot be parsed as valid Python.
    """
    try:
        tree = ast.parse(init_source, feature_version=(3, 14))
    except SyntaxError as exc:
        raise ParseError(str(exc)) from exc

    # Use visit_module for locally-defined names; it also handles __all__
    # extraction and the public-name filter internally.
    local_module = visit_module(init_source, dotted_package)

    explicit_all = extract_all(tree)
    import_map = _build_import_map(tree, dotted_package)
    public_names = _compute_public_names(tree, explicit_all, import_map)

    # Index locally-captured objects by name for fast lookup.
    local_index = _index_module(local_module)

    assignments: list[Assignment] = []
    classes: list[Class] = []
    functions: list[Function] = []
    unresolved: list[str] = []

    for name in sorted(public_names):
        # Subpackage names are the orchestrator's domain — skip silently.
        if name in subpackage_names:
            continue

        obj = _resolve_name(name, import_map, sibling_modules, local_index)

        if obj is None:
            unresolved.append(name)
            continue

        match obj:
            case Assignment():
                assignments.append(obj)
            case Class():
                classes.append(obj)
            case Function():
                functions.append(obj)

    module = Module(
        name=dotted_package,
        assignments=tuple(assignments),
        classes=tuple(classes),
        functions=tuple(functions),
    )

    return module, ResolveReport(unresolved=tuple(unresolved))


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

# A resolved symbol is one of these three concrete types.
_Symbol = Assignment | Class | Function
"""Type alias for the three concrete symbol types that can be resolved from an init module."""


def _build_import_map(
    tree: ast.Module,
    dotted_package: str,
) -> dict[str, tuple[str, str]]:
    """Map each imported name to ``(dotted_module, original_name)``.

    Handles:
    - Relative imports with no module part: ``from . import X``
    - Relative imports with a sibling path: ``from .sibling import X``
    - Relative imports with a deeper path: ``from .sub.deep import X``
    - Absolute imports that name a module inside the same package.

    Args:
        tree: Parsed module AST.
        dotted_package: Fully-qualified package name of the init being resolved.

    Returns:
        A mapping from local alias to ``(dotted_module_name, original_name)``.
    """
    result: dict[str, tuple[str, str]] = {}

    for node in tree.body:
        match node:
            case ast.ImportFrom(module=module, names=aliases, level=level) if level is not None and level > 0:
                # Relative import: level is the number of leading dots.
                resolved_module = _resolve_relative(dotted_package, module, level)
                for alias in aliases:
                    local_name = alias.asname if alias.asname else alias.name
                    result[local_name] = (resolved_module, alias.name)

            case ast.ImportFrom(module=module, names=aliases, level=0) if module is not None:
                # Absolute import — only consider siblings inside our package.
                pkg_prefix = dotted_package + "."
                if module == dotted_package or module.startswith(pkg_prefix):
                    for alias in aliases:
                        local_name = alias.asname if alias.asname else alias.name
                        result[local_name] = (module, alias.name)

            case _:
                pass

    return result


def _resolve_relative(dotted_package: str, module: str | None, level: int) -> str:
    """Compute the fully-qualified module name for a relative import.

    Args:
        dotted_package: The package containing the init file.
        module: The module part after the dots, or ``None`` for ``from . import``.
        level: The number of leading dots (always >= 1 for relative imports).

    Returns:
        The fully-qualified dotted module name.
    """
    # level=1 means "this package"; level>1 means walk up that many levels.
    parts = dotted_package.split(".")
    anchor_parts = parts[: len(parts) - (level - 1)]
    anchor = ".".join(anchor_parts)

    if not module:
        return anchor

    return f"{anchor}.{module}"


def _compute_public_names(
    tree: ast.Module,
    explicit_all: frozenset[str] | None,
    import_map: dict[str, tuple[str, str]],
) -> frozenset[str]:
    """Determine the public names exported by the init module.

    When ``__all__`` is present its literal string members are used directly.
    Otherwise, every top-level name (locally-defined or imported) that does not
    start with ``_`` is included.

    Args:
        tree: Parsed module AST.
        explicit_all: Literal names from ``__all__``, or ``None`` when absent.
        import_map: Mapping of local name → source produced by
            ``_build_import_map``.

    Returns:
        The set of public names to resolve.
    """
    if explicit_all is not None:
        return explicit_all

    names: set[str] = set()

    # Include all non-private imported names.
    for name in import_map:
        if not name.startswith("_"):
            names.add(name)

    # Include all non-private locally-defined names
    local_names = infer_all(tree)
    return local_names | names


def _index_module(module: Module) -> dict[str, _Symbol]:
    """Build a name → symbol index from a ``Module``.

    Args:
        module: The module whose public symbols should be indexed.

    Returns:
        A flat mapping from name to the corresponding
        ``Function``, ``Class``, or ``Assignment`` object.
    """
    index: dict[str, _Symbol] = {}
    for fn in module.functions:
        index[fn.name] = fn
    for cls in module.classes:
        index[cls.name] = cls
    for asgn in module.assignments:
        index[asgn.name] = asgn
    return index


def _lookup_in_sibling(
    name: str,
    source_name: str,
    dotted_module: str,
    sibling_modules: Mapping[str, Module],
) -> _Symbol | None:
    """Look up *source_name* in a sibling module from the mapping.

    Args:
        name: The local alias (used for error context only; not inspected here).
        source_name: The original name exported by the sibling module.
        dotted_module: Fully-qualified name of the sibling module to search.
        sibling_modules: All available sibling modules keyed by dotted name.

    Returns:
        The resolved symbol, or ``None`` when the module or name is absent.
    """
    sibling = sibling_modules.get(dotted_module)
    if sibling is None:
        return None

    sibling_index = _index_module(sibling)
    return sibling_index.get(source_name)


def _resolve_name(
    name: str,
    import_map: dict[str, tuple[str, str]],
    sibling_modules: Mapping[str, Module],
    local_index: dict[str, _Symbol],
) -> _Symbol | None:
    """Attempt to resolve *name* to a concrete symbol.

    Resolution order:
    1. If the name appears in *import_map*, look it up in *sibling_modules*.
    2. Otherwise, fall back to *local_index* (locally-defined in the init).

    Args:
        name: The public name to resolve.
        import_map: Map from local name to ``(dotted_module, original_name)``.
        sibling_modules: All sibling modules available for import resolution.
        local_index: Index of locally-defined symbols in the init module.

    Returns:
        The resolved ``Function``, ``Class``, or ``Assignment``, or ``None``
        when the name cannot be resolved from any source.
    """
    if name in import_map:
        dotted_module, source_name = import_map[name]
        resolved = _lookup_in_sibling(name, source_name, dotted_module, sibling_modules)
        if resolved is not None:
            return resolved

    return local_index.get(name)
