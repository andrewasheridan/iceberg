"""Connect the steps of the analysis: discovery, visits, init resolution and trie assembly.

The orchestrator does these steps:

1. It visits the AST of each module. By default, it does this in the same
   process. If ``Config.max_workers`` is more than 1, it uses worker processes
   through ``concurrent.futures.ProcessPoolExecutor``.
2. It resolves each ``__init__.py`` in series, with full access to the module
   map that it collected.
3. It puts all the modules into a ``Package`` trie.

If the caller gives an ``errors`` list, the orchestrator records each module
that it cannot read or parse in that list as a ``Diagnostic``. Then it skips
the module and continues the run.
"""

__all__ = ["build_package", "unresolved_name_warnings"]

import ast
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

from sheridan.iceberg._config import Config
from sheridan.iceberg._discovery import DiscoveredModule, discover
from sheridan.iceberg._exceptions import IcebergError, ParseError, SourceReadError
from sheridan.iceberg._init_resolver import resolve_init, resolve_module_references
from sheridan.iceberg._models import Diagnostic, Module, Package
from sheridan.iceberg._utilities import extract_all, parse_source, read_source
from sheridan.iceberg._visitor import visit_module


def _error_diagnostic(name: str, path: Path, exc: IcebergError) -> Diagnostic:
    """Describe a module that the analysis skipped because of *exc*.

    Args:
        name: The dotted name of the skipped module.
        path: The source file of the module.
        exc: The error that occurred when the analysis read, parsed or visited
            the module.

    Returns:
        An ``"error"`` diagnostic with the bare message. For a ``ParseError``,
        the diagnostic also has the line.
    """
    message = getattr(exc, "message", None) or str(exc)
    lineno = getattr(exc, "lineno", None)

    return Diagnostic(severity="error", module=name, path=path, message=message, lineno=lineno)


def _visit_worker(
    discovered: DiscoveredModule,
    tree: ast.Module | None = None,
    known_all: Mapping[str, frozenset[str] | None] | None = None,
    *,
    keep_going: bool,
) -> Module | Diagnostic:
    """Read the source from disk and parse it into a ``Module``.

    If ``Config.max_workers`` is more than 1, this function runs in a worker
    process. The function parses the files that the parent did not parse
    already. Thus, this step runs in parallel.

    Args:
        discovered: The metadata of the module to visit, with its path and its
            dotted name.
        tree: The AST of the module, if the parent parsed it already.
        known_all: The evaluated ``__all__`` of each module, by dotted name.
        keep_going: If True and the function cannot read or parse the module,
            give a ``Diagnostic``. Do not raise an exception. A diagnostic
            goes to the parent process without changes. The exceptions of
            iceberg lose their location when they are pickled.

    Returns:
        A ``Module`` with the public API of the source file. If *keep_going*
        is True and the visit failed, an error ``Diagnostic``.
    """
    try:
        source = read_source(discovered.source_path)
        return visit_module(source, discovered.dotted_name, discovered.source_path, known_all, tree=tree)
    except IcebergError as exc:
        if not keep_going:
            raise

        return _error_diagnostic(discovered.dotted_name, discovered.source_path, exc)


def _evaluate_all(
    discovered: Sequence[DiscoveredModule],
    trees: dict[str, ast.Module],
    errors: list[Diagnostic] | None = None,
) -> dict[str, frozenset[str] | None]:
    """Evaluate the ``__all__`` of each module that the discovery found.

    A module can add the ``__all__`` of a different module to its own
    ``__all__`` (``__all__ += sub.__all__``). Thus, the function evaluates each
    module only when it is necessary, and keeps the result in a cache.

    The function does not parse files that do not contain ``__all__``. It
    leaves out files with syntax errors. The visit of such a file raises
    ``ParseError`` later.

    Args:
        discovered: All the modules below the analyzed root.
        trees: The function adds the AST of each file that it parses to this
            mapping, by dotted name. Thus, later steps do not parse the file
            again.
        errors: If you give this list, the function records each file that it
            cannot read in it. It does not raise ``SourceReadError``.

    Returns:
        A mapping from dotted module name to its ``__all__``. The value is
        ``None`` if the module has no ``__all__``, or if the function cannot
        evaluate it statically. The mapping does not include files that the
        function cannot read.
    """
    by_name = {dm.dotted_name: dm for dm in discovered}
    result: dict[str, frozenset[str] | None] = {}
    in_progress: set[str] = set()

    def evaluate(name: str) -> frozenset[str] | None:
        if name in result:
            return result[name]

        dm = by_name.get(name)
        if dm is None or name in in_progress:
            return None

        try:
            source = read_source(dm.source_path)
        except SourceReadError as exc:
            if errors is None:
                raise

            errors.append(_error_diagnostic(name, dm.source_path, exc))
            result[name] = None
            return None

        if "__all__" not in source:
            result[name] = None
            return None

        try:
            tree = parse_source(source, dm.source_path)
        except ParseError:
            return None

        trees[name] = tree
        package = name if dm.is_init else name.rpartition(".")[0]

        in_progress.add(name)
        try:
            result[name] = extract_all(tree, package, evaluate, path=str(dm.source_path))
        finally:
            # pragma: no mutate start, result holds the name now, thus evaluate() never reads in_progress for it again
            in_progress.discard(name)
            # pragma: no mutate end

        return result[name]

    for name in by_name:
        evaluate(name)

    return result


def _namespace_parents(root: Path) -> tuple[str, ...]:
    """List the directories above *root* that have identifier names, the outermost first.

    With these names, ``resolve_init`` can find absolute imports such as
    ``sheridan.iceberg._api`` when the analyzed root is ``src/sheridan/iceberg``
    (with the name ``iceberg``). The walk stops at the first directory with a
    name that is not a valid Python identifier.

    Args:
        root: The analyzed root directory.

    Returns:
        A tuple of directory names, for example ``("src", "sheridan")``.
    """
    names: list[str] = []
    for parent in root.parents:
        if not parent.name.isidentifier():
            break

        names.append(parent.name)

    return tuple(reversed(names))


def _child_names_by_package(all_discovered: tuple[DiscoveredModule, ...]) -> dict[str, frozenset[str]]:
    """Map each package to the short names of all the items directly below it.

    These items are the submodules, the subpackages and the namespace
    subdirectories. A namespace subdirectory has no ``__init__.py``, but it
    contains modules. The function reads each module one time, so that the
    cost does not increase with the square of the number of modules.

    Args:
        all_discovered: All the modules that the full walk found.

    Returns:
        A mapping from the dotted name of a package to a frozenset of the
        short names (not dotted) of its direct children. A package with no
        children is not in the mapping.
    """
    children: dict[str, set[str]] = {}

    for dm in all_discovered:
        parts = dm.dotted_name.split(".")
        for depth in range(1, len(parts)):
            parent = ".".join(parts[:depth])
            children.setdefault(parent, set()).add(parts[depth])

    return {parent: frozenset(names) for parent, names in children.items()}


def _common_prefix(parts_set: set[tuple[str, ...]]) -> tuple[str, ...]:
    """Find the longest tuple that is a prefix of each tuple in *parts_set*.

    Args:
        parts_set: The parts tuples of the package nodes. It must not be empty.

    Returns:
        The common prefix. It is empty if the tuples have no common first component.
    """
    shortest = min(parts_set, key=len)

    for index, component in enumerate(shortest):
        if any(parts[index] != component for parts in parts_set):
            return shortest[:index]

    return shortest


def _node_parts(dm: DiscoveredModule) -> tuple[str, ...]:
    """Find the parts of the ``Package`` node that holds *dm*.

    A regular module is in the node of its parent directories. An
    ``__init__.py`` makes the node of its own directory. If the name of this
    directory is not an identifier, the directory is the analyzed root, and
    the node is the root node with the empty parts.

    Args:
        dm: The discovered module.

    Returns:
        The parts of the node, for example ``("my_pkg", "sub")``.
    """
    if not dm.is_init:
        return dm.package_parts

    directory_name = dm.source_path.parent.name
    if not directory_name.isidentifier():
        return dm.package_parts

    return (*dm.package_parts, directory_name)


def _build_trie(
    module_map: dict[str, Module],
    all_discovered: tuple[DiscoveredModule, ...],
    root: Path,
    package_all_map: dict[str, frozenset[str] | None],
) -> Package:
    """Put a flat module map into a ``Package`` trie.

    The function uses the ``package_parts`` of each ``DiscoveredModule`` to
    find the ``Package`` node of each module. The name of the root ``Package``
    comes from the first component that all the modules have. If there is no
    such component, the name comes from ``root.name``.

    If the ``__init__.py`` of a package defines ``__all__``, the function
    applies these filters to the ``Package``:

    - ``Package.modules`` contains the package-level ``Module``. This is the
      resolved init module, which holds all the public symbols that it moved
      up. ``Package.modules`` also contains the submodules with a short name
      in ``__all__``.
    - ``Package.subpackages`` contains only the subpackages with a short name
      in ``__all__``.

    Args:
        module_map: The mapping from dotted module name to resolved ``Module``.
        all_discovered: All the modules that the discovery found. The function
            uses them to find the structure of the trie.
        root: The root directory of the package to assemble.
        package_all_map: The mapping from dotted package name to the literal
            ``__all__`` frozenset, or ``None`` if there is no ``__all__``.

    Returns:
        The assembled ``Package`` trie.
    """
    # Divide the init modules and the regular modules by their parts key.
    init_modules_by_parts: dict[tuple[str, ...], Module] = {}
    regular_modules_by_parts: dict[tuple[str, ...], list[Module]] = {}
    parts_to_path: dict[tuple[str, ...], Path] = {}

    for dm in all_discovered:
        module = module_map.get(dm.dotted_name)
        if module is None:
            continue

        pkg_parts = _node_parts(dm)

        if dm.is_init:
            init_modules_by_parts[pkg_parts] = module
            parts_to_path[pkg_parts] = dm.source_path.parent
        else:
            regular_modules_by_parts.setdefault(pkg_parts, []).append(module)
            parts_to_path.setdefault(pkg_parts, dm.source_path.parent)

    # Collect all the unique package_parts tuples to identify each package node.
    all_pkg_parts: set[tuple[str, ...]] = set()
    for dm in all_discovered:
        pkg_parts = _node_parts(dm)
        all_pkg_parts.add(pkg_parts)
        parts_to_path.setdefault(pkg_parts, dm.source_path.parent)

    if not all_pkg_parts:
        return Package(name=root.name, path=root, modules=(), subpackages=())

    # The root is the longest prefix that all the nodes have. If no module is
    # directly in the root directory, no node has these parts, and possibly no
    # node has the parts between the root and a deeper package. Add these
    # nodes, so that each node has a parent up to the root.
    root_parts = _common_prefix(all_pkg_parts)
    for pkg_parts in list(all_pkg_parts):
        package_dir = parts_to_path[pkg_parts]

        for end in range(len(root_parts), len(pkg_parts)):
            ancestor = pkg_parts[:end]
            all_pkg_parts.add(ancestor)
            parts_to_path.setdefault(ancestor, package_dir.parents[len(pkg_parts) - end - 1])

    # Index the direct child nodes of each node one time, so that _make_package
    # does not scan all the nodes for each node.
    child_parts_by_parts: dict[tuple[str, ...], list[tuple[str, ...]]] = {}
    for pkg_parts in all_pkg_parts:
        # The empty root parts have no parent. Without this check, they are their own child.
        if pkg_parts:
            child_parts_by_parts.setdefault(pkg_parts[:-1], []).append(pkg_parts)

    def _make_package(parts: tuple[str, ...]) -> Package:
        """Assemble a ``Package`` for the given parts prefix recursively.

        Args:
            parts: The tuple of name components that identifies the package
                node, for example ``("my_pkg", "sub")``.

        Returns:
            A ``Package``. Its ``modules`` are the direct members at this
            level. Its ``subpackages`` are all the direct children, which the
            function assembles recursively.
        """
        # If the name of root is not an identifier, the root parts are empty.
        # Then use the directory name, so that the name is never "". The root
        # __init__.py has this name too, thus package_all_map has its __all__.
        name = ".".join(parts) or root.name
        path = parts_to_path.get(parts, root)

        explicit_all = package_all_map.get(name)
        init_module = init_modules_by_parts.get(parts)

        child_parts = sorted(child_parts_by_parts.get(parts, []))

        direct_modules_list: list[Module] = []
        subpackages_list: list[Package] = []

        if explicit_all is not None:
            # If the package defines __all__, the resolved init module holds all
            # the public symbols that it moved up. Thus, remove private submodules.
            # Keep regular submodules and subpackages only if __all__ has their
            # short name.
            if init_module is not None:
                direct_modules_list.append(init_module)

            for mod in regular_modules_by_parts.get(parts, []):
                if mod.name.split(".")[-1] in explicit_all:
                    direct_modules_list.append(mod)

            for child in child_parts:
                if child[-1] in explicit_all:
                    subpackages_list.append(_make_package(child))
        else:
            for mod in regular_modules_by_parts.get(parts, []):
                if mod.is_public:
                    direct_modules_list.append(mod)

            if init_module is not None:
                direct_modules_list.append(init_module)

            for child in child_parts:
                subpackage = _make_package(child)
                if subpackage.is_public:
                    subpackages_list.append(subpackage)

        direct_modules = tuple(sorted(direct_modules_list, key=lambda m: m.name))
        subpackages = sorted(subpackages_list, key=lambda p: p.name)

        return Package(
            name=name,
            path=path,
            modules=direct_modules,
            subpackages=tuple(subpackages),
        )

    return _make_package(root_parts)


def unresolved_name_warnings(api: Package | Module, path: Path) -> list[Diagnostic]:
    """List a warning for each public name in *api* that no import binds.

    These are the references that the tree shows as ``name (unresolved)``.
    The function does not report references that name their source module.
    These are re-exports from outside the analyzed tree, which are normal.

    Args:
        api: The assembled package or module.
        path: The analyzed path. If *api* is a ``Module``, this is the source file.

    Returns:
        One ``"warning"`` diagnostic for each unresolved name, sorted by module
        and then by name.
    """
    located: list[tuple[Module, Path]] = []
    packages: list[Package] = []

    if isinstance(api, Module):
        located.append((api, path))
    else:
        packages.append(api)

    while packages:
        package = packages.pop()

        for module in package.modules:
            stem = "__init__" if module.name == package.name else module.name.rpartition(".")[2]
            file_name = f"{stem}.py"

            located.append((module, package.path / file_name))

        packages.extend(package.subpackages)

    warnings: list[Diagnostic] = []
    for module, source_path in sorted(located, key=lambda item: item[0].name):
        for reference in module.references:
            if reference.module is not None:
                continue

            warnings.append(
                Diagnostic(
                    severity="warning",
                    module=module.name,
                    path=source_path,
                    message=f"{reference.name!r} is exported but never bound",
                )
            )

    return warnings


def build_package(root: Path, config: Config, *, errors: list[Diagnostic] | None = None) -> Package | Module:
    """Build a ``Package`` snapshot of the Python source at *root*.

    If *root* is one ``.py`` file, the function does not do the discovery. It
    visits the file directly. If *root* is a directory, the function does all
    these five steps:

    1. Find all the Python modules below *root*.
    2. Divide them into init modules and other modules.
    3. Visit the other modules. If ``config.max_workers > 1``, use a
       ``ProcessPoolExecutor``. Then resolve the re-exports between them.
    4. Resolve each ``__init__.py`` in series, with the collected map.
    5. Put the completed map into a ``Package`` trie.

    Args:
        root: The path to one ``.py`` file or to a package directory.
        config: The runtime configuration. It sets the workers, the filters
            and other options.
        errors: If you give this list and *root* is a directory, the function
            records each module that it cannot read or parse in the list,
            sorted by module. It leaves the module out of the result and does
            not raise an exception. If *root* is one file, the function still
            raises an exception, because there is nothing else to report.

    Returns:
        A ``Package`` with the full public API of *root*. If *root* is one
        file, the function gives the bare ``Module``.
    """
    if root.is_file():
        source = read_source(root)
        return visit_module(source, root.stem, root)

    keep_going = errors is not None
    found: list[Diagnostic] = []

    # 1. Find all the Python source files below root.
    all_discovered = discover(root, config)

    # 2. Evaluate each __all__ one time, so that `__all__ += sub.__all__` can see
    #    other modules. Then divide the modules into regular modules and __init__.py files.
    trees: dict[str, ast.Module] = {}
    known_all = _evaluate_all(all_discovered, trees, found if keep_going else None)
    unreadable = {diagnostic.module for diagnostic in found}
    readable = [dm for dm in all_discovered if dm.dotted_name not in unreadable]
    non_init_modules = [dm for dm in readable if not dm.is_init]
    init_modules = [dm for dm in readable if dm.is_init]

    # 3. Visit the other modules. For usual packages, a process pool costs more
    #    time to start than it saves. New workers also import the __main__ of
    #    the caller again. Thus, the user must ask for the pool.
    visit = partial(_visit_worker, known_all=known_all, keep_going=keep_going)
    parsed_trees = [trees.get(dm.dotted_name) for dm in non_init_modules]

    visited: list[Module | Diagnostic]
    if config.max_workers > 1:
        # pragma: no mutate start, without the trees or the worker count, the result is the same but slower
        with ProcessPoolExecutor(max_workers=config.max_workers) as executor:
            visited = list(executor.map(visit, non_init_modules, parsed_trees))
        # pragma: no mutate end
    else:
        # pragma: no mutate start, the lists have the same length, thus strict has no effect
        visited = [visit(dm, tree) for dm, tree in zip(non_init_modules, parsed_trees, strict=True)]
        # pragma: no mutate end

    module_map: dict[str, Module] = {}
    for dm, outcome in zip(non_init_modules, visited, strict=True):  # pragma: no mutate, the same length
        if isinstance(outcome, Diagnostic):
            found.append(outcome)
        else:
            module_map[dm.dotted_name] = outcome

    # Follow the chains of re-exports between regular modules (``_a`` re-exports
    # ``X`` from ``_b``). Thus, an init that imports from ``_a`` finds ``X``.
    namespace_parents = _namespace_parents(root)
    module_map = resolve_module_references(module_map, namespace_parents=namespace_parents)

    # 4. Resolve the __init__.py files in series, the deepest first. Thus, each
    #    subpackage init is in module_map before its parent init tries to
    #    resolve imports from it.
    sorted_inits = sorted(init_modules, key=lambda dm: len(dm.package_parts), reverse=True)

    # Record the __all__ of each package, so that _build_trie can filter the
    # modules and subpackages. The value None means that there is no __all__.
    package_all_map: dict[str, frozenset[str] | None] = {}
    child_names = _child_names_by_package(all_discovered)

    for init_module in sorted_inits:
        package_all_map[init_module.dotted_name] = known_all.get(init_module.dotted_name)
        try:
            module = resolve_init(
                read_source(init_module.source_path),
                init_module.dotted_name,
                module_map,
                child_names.get(init_module.dotted_name, frozenset()),
                namespace_parents=namespace_parents,
                path=init_module.source_path,
                known_all=known_all,
                tree=trees.get(init_module.dotted_name),
            )
        except IcebergError as exc:
            if not keep_going:
                raise

            found.append(_error_diagnostic(init_module.dotted_name, init_module.source_path, exc))
            continue

        module_map[init_module.dotted_name] = module

    if errors is not None:
        errors.extend(sorted(found, key=lambda diagnostic: diagnostic.module))

    # 5. Put the completed module map into a Package trie.
    return _build_trie(module_map, all_discovered, root, package_all_map)
