"""Resolver for ``__init__.py`` re-export declarations.

``visit_module`` (in ``_visitor.py``) treats an init file as a plain module and
captures only locally-defined names.  This module runs on top of that to
resolve ``from .sibling import X`` style re-exports so the returned ``Module``
contains the actual ``Function`` / ``Class`` / ``Assignment`` objects from the
sibling module rather than nothing at all.

Architectural split
-------------------
Subpackage visibility (whether a sub-package appears in the parent's public
surface) is the orchestrator's responsibility.  This resolver returns only the init module's
own ``Module``; it never synthesises placeholder entries for subpackages.
Callers must assemble ``Package.subpackages`` separately.
"""

__all__ = ["ResolveReport", "resolve_init", "resolve_module_references"]

import ast
import dataclasses
from collections.abc import Callable, Mapping
from pathlib import Path

from sheridan.iceberg._exceptions import ParseError
from sheridan.iceberg._models import Assignment, Class, Function, Module, Reference, ResolveReport
from sheridan.iceberg._utilities import collect_imports, extract_all, infer_all
from sheridan.iceberg._visitor import visit_module

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_init(
    init_source: str,
    dotted_package: str,
    sibling_modules: Mapping[str, Module],
    subpackage_names: frozenset[str],
    *,
    namespace_parents: tuple[str, ...] = (),
    path: Path | None = None,
    known_all: Mapping[str, frozenset[str] | None] | None = None,
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
       ``ResolveReport.unresolved`` and attach a ``Reference`` describing
       where it was imported from (if anywhere) — no exception is raised.

    Subpackage visibility is the orchestrator's concern, not this resolver's.

    Args:
        init_source: Raw Python source text of the ``__init__.py`` file.
        dotted_package: Fully-qualified package name (e.g. ``"my_pkg.sub"``).
        sibling_modules: Mapping from dotted module name to ``Module`` for all
            modules visible to this init file.
        subpackage_names: Names of direct sub-packages and sub-modules under
            this package. Used only to avoid recording them as unresolved —
            they are not attached to the returned ``Module``.
        namespace_parents: Names of the directories above the analyzed root,
            outermost first (e.g. ``("src", "sheridan")`` for a root of
            ``src/sheridan/iceberg``). Absolute imports spelled with a trailing
            run of these as a prefix (``from sheridan.iceberg._api import x``)
            are treated as intra-package imports.
        path: The file *init_source* was read from. It is reported in the
            ``ParseError`` when *init_source* has a syntax error.
        known_all: The evaluated ``__all__`` of each module in the analyzed
            tree, by dotted name. When it holds *dotted_package*, that value
            is used as is; otherwise ``__all__`` is evaluated from
            *init_source*, and this mapping resolves
            ``__all__ += sub.__all__``.

    Returns:
        A two-tuple of ``(module, report)`` where *module* is the resolved
        ``Module`` for the init file and *report* records any names that could
        not be resolved.

    Raises:
        ParseError: When *init_source* cannot be parsed as valid Python.
    """
    try:
        tree = ast.parse(init_source, filename="<unknown>" if path is None else str(path), feature_version=(3, 14))
    except SyntaxError as exc:
        raise ParseError.from_syntax_error(exc) from exc

    if known_all is not None and dotted_package in known_all:
        explicit_all = known_all[dotted_package]
    else:
        explicit_all = extract_all(
            tree,
            dotted_package,
            None if known_all is None else known_all.get,
            path=None if path is None else str(path),
        )

    # Use visit_module for locally-defined names and the public-name filter.
    # Pass the evaluated __all__ so it is not evaluated (and reported) twice.
    local_module = visit_module(init_source, dotted_package, path, {**(known_all or {}), dotted_package: explicit_all})

    all_imports = collect_imports(tree, dotted_package)
    import_map = _build_import_map(all_imports, dotted_package, namespace_parents)
    public_names = _compute_public_names(tree, explicit_all, import_map)

    # Index locally-captured objects by name for fast lookup.
    local_index = _index_module(local_module)

    assignments: list[Assignment] = []
    classes: list[Class] = []
    functions: list[Function] = []
    references: list[Reference] = []
    unresolved: list[str] = []

    for name in sorted(public_names):
        # Subpackage names are the orchestrator's domain — skip silently.
        if name in subpackage_names:
            continue

        obj = _resolve_name(name, import_map, sibling_modules, local_index)

        if obj is None:
            unresolved.append(name)
            module_name, attribute = all_imports.get(name, (None, None))
            references.append(Reference(name=name, module=module_name, attribute=attribute))
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
        references=tuple(references),
    )

    return module, ResolveReport(unresolved=tuple(unresolved))


def resolve_module_references(
    modules: Mapping[str, Module],
    *,
    namespace_parents: tuple[str, ...] = (),
) -> dict[str, Module]:
    """Resolve the ``Reference`` entries of regular modules against each other.

    A regular module whose ``__all__`` lists an imported name carries a
    ``Reference`` for it. When the import points at another module in
    *modules*, the reference is replaced with the definition found there. The
    target is resolved first (memoized), so chains of any length are followed.
    An import cycle stops the walk: the module being resolved is used as
    visited, and a name that is only re-exported around the cycle stays a
    ``Reference``.

    Args:
        modules: Mapping from dotted module name to the visited ``Module``.
        namespace_parents: Names of the directories above the analyzed root,
            outermost first. See ``resolve_init``.

    Returns:
        A new mapping with the same keys, where each module's resolvable
        references have been replaced by the ``Function``, ``Class``, or
        ``Assignment`` they point to.
    """
    resolved: dict[str, Module] = {}
    in_progress: set[str] = set()

    def resolve(name: str) -> Module | None:
        if name in resolved:
            return resolved[name]
        module = modules.get(name)
        if module is None or name in in_progress or not module.references:
            # In a cycle, hand back the module as visited and do not memoize it.
            return module
        in_progress.add(name)
        try:
            result = _resolve_references(module, namespace_parents, resolve)
        finally:
            in_progress.discard(name)
        resolved[name] = result
        return result

    return {name: resolve(name) or module for name, module in modules.items()}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

# A resolved symbol is one of these three concrete types.
_Symbol = Assignment | Class | Function
"""Type alias for the three concrete symbol types that can be resolved from an init module."""


def _build_import_map(
    all_imports: Mapping[str, tuple[str, str | None]],
    dotted_package: str,
    namespace_parents: tuple[str, ...] = (),
) -> dict[str, tuple[str, str]]:
    """Select the ``from ... import`` bindings that point inside the analyzed tree.

    Handles relative imports (already absolutized by ``collect_imports``) and
    absolute imports that name a module under the same root package, including
    absolute imports spelled with a namespace prefix above the analyzed root
    (see ``namespace_parents``).

    Args:
        all_imports: Output of ``collect_imports`` for the init module.
        dotted_package: Fully-qualified package name of the init being resolved.
        namespace_parents: Directory names above the analyzed root, outermost
            first.

    Returns:
        A mapping from local alias to ``(dotted_module_name, original_name)``
        where ``dotted_module_name`` uses the analyzed tree's own naming.
    """
    root_package = dotted_package.split(".")[0]
    result: dict[str, tuple[str, str]] = {}

    for local_name, (module, attribute) in all_imports.items():
        if attribute is None:
            continue

        normalized = _strip_namespace_prefix(module, root_package, namespace_parents)
        if normalized == root_package or normalized.startswith(root_package + "."):
            result[local_name] = (normalized, attribute)

    return result


def _strip_namespace_prefix(module: str, root_package: str, namespace_parents: tuple[str, ...]) -> str:
    """Rewrite *module* into the analyzed tree's naming when it carries a namespace prefix.

    When iceberg is pointed at ``src/sheridan/iceberg`` the root package is
    named ``iceberg``, but the code itself imports ``sheridan.iceberg.x``. If
    the components before ``root_package`` exactly match the innermost
    directories above the root, they are stripped.

    Args:
        module: Absolute dotted module name as written in the import.
        root_package: First component of the analyzed tree's dotted names.
        namespace_parents: Directory names above the analyzed root, outermost
            first.

    Returns:
        The module name with the prefix removed, or *module* unchanged when no
        prefix matches.
    """
    parts = module.split(".")
    for depth in range(min(len(namespace_parents), len(parts) - 1), 0, -1):
        if parts[depth] == root_package and tuple(parts[:depth]) == namespace_parents[-depth:]:
            return ".".join(parts[depth:])
    return module


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
            if resolved.name != name:
                resolved = dataclasses.replace(resolved, name=name)
            return resolved

    return local_index.get(name)


def _resolve_references(
    module: Module,
    namespace_parents: tuple[str, ...],
    resolve: Callable[[str], Module | None],
) -> Module:
    """Replace the references of *module* that point at a module *resolve* knows.

    Args:
        module: The module whose references should be resolved.
        namespace_parents: Directory names above the analyzed root, outermost
            first.
        resolve: Returns the (resolved) module for a dotted name, or ``None``.

    Returns:
        A copy of *module* with each resolvable reference moved into its
        ``assignments``, ``classes``, or ``functions``.
    """
    root_package = module.name.split(".")[0]
    assignments = list(module.assignments)
    classes = list(module.classes)
    functions = list(module.functions)
    references: list[Reference] = []

    for reference in module.references:
        symbol: _Symbol | None = None
        if reference.module is not None and reference.attribute is not None:
            target = resolve(_strip_namespace_prefix(reference.module, root_package, namespace_parents))
            if target is not None:
                symbol = _index_module(target).get(reference.attribute)

        if symbol is None:
            references.append(reference)
            continue
        if symbol.name != reference.name:
            symbol = dataclasses.replace(symbol, name=reference.name)

        match symbol:
            case Assignment():
                assignments.append(symbol)
            case Class():
                classes.append(symbol)
            case Function():
                functions.append(symbol)

    return dataclasses.replace(
        module,
        assignments=tuple(assignments),
        classes=tuple(classes),
        functions=tuple(functions),
        references=tuple(references),
    )
