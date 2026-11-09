"""Resolve the re-exports in ``__init__.py`` files.

``visit_module`` (in ``_visitor.py``) uses an init file as a plain module. It
collects only the names that the file defines. This module adds to that. It
resolves re-exports such as ``from .sibling import X``. Thus, the ``Module``
that it gives has the real ``Function``, ``Class`` and ``Assignment`` objects
from the sibling module.

Division of work
----------------
The orchestrator decides if a subpackage is part of the public API of its
parent. This resolver gives only the ``Module`` of the init module. It never
makes placeholder items for subpackages. Callers must assemble
``Package.subpackages`` separately.
"""

__all__ = ["resolve_init", "resolve_module_references"]

import ast
import dataclasses
from collections.abc import Callable, Mapping
from pathlib import Path

from sheridan.iceberg._models import Assignment, Class, Function, Module, Reference
from sheridan.iceberg._utilities import collect_imports, extract_all, infer_all, parse_source, star_candidate
from sheridan.iceberg._visitor import visit_module


def resolve_init(
    init_source: str,
    dotted_package: str,
    sibling_modules: Mapping[str, Module],
    subpackage_names: frozenset[str],
    *,
    namespace_parents: tuple[str, ...] = (),
    path: Path | None = None,
    known_all: Mapping[str, frozenset[str] | None] | None = None,
    tree: ast.Module | None = None,
) -> Module:
    """Resolve the source of an ``__init__.py`` into a ``Module`` with its re-exports.

    The function parses *init_source*. It finds the set of public names (from
    ``__all__`` or from the underscore rule). Then it tries to resolve each
    public name to a ``Function``, ``Class`` or ``Assignment``:

    1. If the init file imports the name from a known sibling module, the
       function finds the name in the ``Module`` of that sibling. Then it
       attaches the resolved object.
    2. If the init file defines the name, the function uses the object that
       ``visit_module`` collected.
    3. If the function cannot resolve the name from these sources, it attaches
       a ``Reference``. The reference tells where the name comes from, if this
       is known. The function does not raise an exception.

    The orchestrator, not this resolver, decides which subpackages are visible.

    Args:
        init_source: The raw Python source text of the ``__init__.py`` file.
        dotted_package: The fully qualified package name (for example
            ``"my_pkg.sub"``).
        sibling_modules: A mapping from dotted module name to ``Module`` for
            all the modules that this init file can see.
        subpackage_names: The names of the direct subpackages and submodules of
            this package. The function uses them only to not record them as
            unresolved. It does not attach them to the ``Module`` that it gives.
        namespace_parents: The names of the directories above the analyzed
            root, the outermost first. For example, ``("src", "sheridan")`` for
            the root ``src/sheridan/iceberg``. The function uses absolute
            imports with a prefix from the end of these names as imports in
            the package. An example is ``from sheridan.iceberg._api import x``.
        path: The file that contains *init_source*. If *init_source* has a
            syntax error, the ``ParseError`` shows this path.
        known_all: The evaluated ``__all__`` of each module in the analyzed
            tree, by dotted name. If it has *dotted_package*, the function uses
            that value. If not, the function evaluates ``__all__`` from
            *init_source*, and this mapping resolves ``__all__ += sub.__all__``.
        tree: The parsed *init_source*. With it, the caller parses each file
            only one time. If you give it, the function does not parse
            *init_source* again.

    Returns:
        The resolved ``Module`` of the init file. Its ``references`` hold the
        names that the function cannot resolve.

    Raises:
        ParseError: If *init_source* is not valid Python.
    """
    if tree is None:
        tree = parse_source(init_source, path)

    if known_all is not None and dotted_package in known_all:
        explicit_all = known_all[dotted_package]
    else:
        explicit_all = extract_all(
            tree,
            dotted_package,
            None if known_all is None else known_all.get,
            path=None if path is None else str(path),
        )

    # Use visit_module for the names that the file defines and for the public-name filter.
    # Give it the evaluated __all__. Then visit_module does not evaluate (and report) it again.
    local_all = {**(known_all or {}), dotted_package: explicit_all}
    local_module = visit_module(init_source, dotted_package, path, local_all, tree=tree)

    root_package = dotted_package.split(".")[0]

    def star_exports(module_name: str) -> frozenset[str] | None:
        # A visited module holds exactly its public names. These are its ``__all__``,
        # or the names without a leading underscore if it has no ``__all__``.
        sibling_name = _strip_namespace_prefix(module_name, root_package, namespace_parents)
        sibling = sibling_modules.get(sibling_name)

        return None if sibling is None else _exported_names(sibling)

    all_imports = collect_imports(tree, dotted_package, star_exports)
    candidate = star_candidate(tree, dotted_package, star_exports)
    import_map = _build_import_map(all_imports, dotted_package, namespace_parents)
    public_names = _compute_public_names(tree, explicit_all, import_map)

    # Index the objects that the file defines by name, for a fast search.
    local_index = _index_module(local_module)

    assignments: list[Assignment] = []
    classes: list[Class] = []
    functions: list[Function] = []
    references: list[Reference] = []

    for name in sorted(public_names):
        # The orchestrator handles subpackage names. Skip them silently.
        if name in subpackage_names:
            continue

        obj = _resolve_name(name, import_map, sibling_modules, local_index)

        if obj is None:
            if name in all_imports:
                module_name, attribute = all_imports[name]
            elif candidate is not None:
                module_name, attribute = candidate, name
            else:
                module_name, attribute = None, None

            references.append(Reference(name=name, module=module_name, attribute=attribute))
            continue

        match obj:
            case Assignment():
                assignments.append(obj)

            case Class():
                classes.append(obj)

            case Function():
                functions.append(obj)

    return Module(
        name=dotted_package,
        assignments=tuple(assignments),
        classes=tuple(classes),
        functions=tuple(functions),
        references=tuple(references),
    )


def resolve_module_references(
    modules: Mapping[str, Module],
    *,
    namespace_parents: tuple[str, ...] = (),
) -> dict[str, Module]:
    """Resolve the ``Reference`` entries of regular modules against each other.

    If the ``__all__`` of a regular module lists an imported name, the module
    has a ``Reference`` for it. If the import points to a different module in
    *modules*, the function replaces the reference with the definition in that
    module. The function resolves the target first (and memoizes it). Thus, it
    follows chains of all lengths.

    An import cycle stops the walk. The function uses the module in the cycle
    as it was visited. A name that the modules in the cycle only re-export
    stays a ``Reference``.

    Args:
        modules: A mapping from dotted module name to the visited ``Module``.
        namespace_parents: The names of the directories above the analyzed
            root, the outermost first. See ``resolve_init``.

    Returns:
        A new mapping with the same keys. In each module, the function replaces
        the references that it can resolve with the ``Function``, ``Class`` or
        ``Assignment`` that they point to.
    """
    resolved: dict[str, Module] = {}
    in_progress: set[str] = set()

    def resolve(name: str) -> Module | None:
        if name in resolved:
            return resolved[name]

        module = modules.get(name)
        if module is None or name in in_progress or not module.references:
            # In a cycle, give back the module as it was visited, and do not memoize it.
            return module

        in_progress.add(name)
        try:
            result = _resolve_references(module, namespace_parents, resolve)
        finally:
            in_progress.discard(name)

        resolved[name] = result
        return result

    return {name: resolve(name) or module for name, module in modules.items()}


# A resolved symbol is one of these three concrete types.
_Symbol = Assignment | Class | Function
"""The type alias for the three concrete symbol types that an init module can resolve to."""


def _build_import_map(
    all_imports: Mapping[str, tuple[str, str | None]],
    dotted_package: str,
    namespace_parents: tuple[str, ...] = (),
) -> dict[str, tuple[str, str]]:
    """Select the ``from ... import`` bindings that point inside the analyzed tree.

    The function accepts these imports:

    - Relative imports. ``collect_imports`` already made them absolute.
    - Absolute imports of a module in the same root package.
    - Absolute imports with a namespace prefix above the analyzed root (see
      ``namespace_parents``).

    Args:
        all_imports: The output of ``collect_imports`` for the init module.
        dotted_package: The fully qualified package name of the init module.
        namespace_parents: The names of the directories above the analyzed
            root, the outermost first.

    Returns:
        A mapping from local alias to ``(dotted_module_name, original_name)``.
        ``dotted_module_name`` uses the names of the analyzed tree.
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
    """Change *module* to the names of the analyzed tree, if it has a namespace prefix.

    If you give iceberg ``src/sheridan/iceberg``, the name of the root package
    is ``iceberg``. But the code imports ``sheridan.iceberg.x``. If the
    components before ``root_package`` are the same as the innermost
    directories above the root, the function removes them.

    Args:
        module: The absolute dotted module name, as the import gives it.
        root_package: The first component of the dotted names of the analyzed tree.
        namespace_parents: The names of the directories above the analyzed
            root, the outermost first.

    Returns:
        The module name without the prefix. If no prefix matches, *module*
        without a change.
    """
    parts = module.split(".")
    deepest = min(len(namespace_parents), len(parts) - 1)

    for depth in range(deepest, 0, -1):
        if parts[depth] == root_package and tuple(parts[:depth]) == namespace_parents[-depth:]:
            return ".".join(parts[depth:])

    return module


def _compute_public_names(
    tree: ast.Module,
    explicit_all: frozenset[str] | None,
    import_map: dict[str, tuple[str, str]],
) -> frozenset[str]:
    """Find the public names that the init module exports.

    If the module has ``__all__``, the function uses its literal string items.
    If not, it includes each top-level name that does not start with ``_``.
    These are the names that the module defines or imports.

    Args:
        tree: The parsed module AST.
        explicit_all: The literal names from ``__all__``, or ``None`` if there
            is no ``__all__``.
        import_map: The mapping from local name to source that
            ``_build_import_map`` makes.

    Returns:
        The set of public names to resolve.
    """
    if explicit_all is not None:
        return explicit_all

    names: set[str] = set()

    # Include all the imported names that are not private.
    for name in import_map:
        if not name.startswith("_"):
            names.add(name)

    return infer_all(tree) | names


def _index_module(module: Module) -> dict[str, _Symbol]:
    """Build an index from name to symbol for a ``Module``.

    Args:
        module: The module with the public symbols to index.

    Returns:
        A flat mapping from name to the related ``Function``, ``Class`` or
        ``Assignment`` object.
    """
    index: dict[str, _Symbol] = {}
    for fn in module.functions:
        index[fn.name] = fn

    for cls in module.classes:
        index[cls.name] = cls

    for asgn in module.assignments:
        index[asgn.name] = asgn

    return index


def _exported_names(module: Module) -> frozenset[str]:
    """List all the names that a visited module exports, resolved and unresolved.

    Args:
        module: A visited module. It can also be resolved.

    Returns:
        The names of its definitions and its references.
    """
    return frozenset(_index_module(module)) | {reference.name for reference in module.references}


def _lookup_in_sibling(
    name: str,
    source_name: str,
    dotted_module: str,
    sibling_modules: Mapping[str, Module],
) -> _Symbol | None:
    """Look up *source_name* in a sibling module from the mapping.

    Args:
        name: The local alias. The function does not examine it.
        source_name: The original name that the sibling module exports.
        dotted_module: The fully qualified name of the sibling module to search.
        sibling_modules: All the available sibling modules, by dotted name.

    Returns:
        The resolved symbol, or ``None`` if the module or the name is not there.
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
    """Try to resolve *name* to a concrete symbol.

    The function uses this order:

    1. If *import_map* has the name, find the name in *sibling_modules*.
    2. If not, use *local_index* (the symbols that the init module defines).

    Args:
        name: The public name to resolve.
        import_map: The map from local name to ``(dotted_module, original_name)``.
        sibling_modules: All the sibling modules that the imports can use.
        local_index: The index of the symbols that the init module defines.

    Returns:
        The resolved ``Function``, ``Class`` or ``Assignment``. ``None`` if the
        function cannot resolve the name from a source.
    """
    if name not in import_map:
        return local_index.get(name)

    dotted_module, source_name = import_map[name]
    resolved = _lookup_in_sibling(name, source_name, dotted_module, sibling_modules)

    if resolved is None:
        return local_index.get(name)

    if resolved.name != name:
        resolved = dataclasses.replace(resolved, name=name)

    return resolved


def _resolve_references(
    module: Module,
    namespace_parents: tuple[str, ...],
    resolve: Callable[[str], Module | None],
) -> Module:
    """Replace the references of *module* that point at a module *resolve* knows.

    Args:
        module: The module with the references to resolve.
        namespace_parents: The names of the directories above the analyzed
            root, the outermost first.
        resolve: A function that gives the (resolved) module for a dotted
            name, or ``None``.

    Returns:
        A copy of *module*. The function moves each reference that it can
        resolve into the ``assignments``, ``classes`` or ``functions``.
    """
    root_package = module.name.split(".")[0]

    assignments = list(module.assignments)
    classes = list(module.classes)
    functions = list(module.functions)
    references: list[Reference] = []

    for reference in module.references:
        symbol: _Symbol | None = None
        if reference.module is not None and reference.attribute is not None:
            target_name = _strip_namespace_prefix(reference.module, root_package, namespace_parents)
            target = resolve(target_name)
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
