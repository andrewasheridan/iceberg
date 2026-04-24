"""Orchestrator that threads discovery, visiting, init-resolution, and trie assembly.

Parallelizes per-module AST visits across worker processes using
``concurrent.futures.ProcessPoolExecutor``, then serially resolves each
``__init__.py`` with full access to the accumulated module map, and finally
folds everything into a ``Package`` trie.
"""

__all__ = ["build_package"]

import ast
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from sheridan.iceberg._config import Config
from sheridan.iceberg._discovery import discover
from sheridan.iceberg._init_resolver import resolve_init
from sheridan.iceberg._models import DiscoveredModule, Module, Package
from sheridan.iceberg._utilities import extract_all
from sheridan.iceberg._visitor import visit_module


def _visit_worker(discovered: DiscoveredModule) -> Module:
    """Read source from disk and return a parsed ``Module``.

    Runs in a worker process. Any IO must happen here — not in the
    parent — so the filesystem walk and AST parse stages are
    actually parallel.

    Args:
        discovered: Metadata about the module to visit, including its path
            and dotted name.

    Returns:
        A ``Module`` capturing the public API surface of the source file.
    """
    source = discovered.source_path.read_text(encoding="utf-8")
    return visit_module(source, discovered.dotted_name)


def _subpackage_names_at_level(
    package_parts: tuple[str, ...],
    all_discovered: tuple[DiscoveredModule, ...],
) -> frozenset[str]:
    """Return the names of direct sub-packages under a given package.

    A direct sub-package is one whose ``package_parts`` is exactly one
    element longer than *package_parts* and whose prefix matches.

    Args:
        package_parts: The ``package_parts`` tuple of the init module being
            resolved.
        all_discovered: All discovered modules from the full walk.

    Returns:
        A frozenset of short names (not dotted) for each direct sub-package.
    """
    names: set[str] = set()

    for dm in all_discovered:
        if not dm.is_init:
            continue

        if len(dm.package_parts) != len(package_parts) + 1:
            continue

        if dm.package_parts[: len(package_parts)] != package_parts:
            continue

        # The last part of this init's package_parts is the sub-package name.
        names.add(dm.package_parts[-1])

    return frozenset(names)


def _build_trie(
    module_map: dict[str, Module],
    all_discovered: tuple[DiscoveredModule, ...],
    root: Path,
    package_all_map: dict[str, frozenset[str] | None],
) -> Package:
    """Fold a flat module map into a ``Package`` trie.

    Uses the ``package_parts`` on each ``DiscoveredModule`` to determine
    which ``Package`` node each module belongs to. The root ``Package``
    name is derived from the first component common to all discovered
    modules (or from ``root.name`` as a fallback).

    When a package's ``__init__.py`` defines ``__all__``, the resulting
    ``Package`` is filtered as follows:

    - ``Package.modules`` contains only the package-level ``Module`` (the
      resolved init module, which already holds all hoisted public symbols).
      Submodules whose short names do not appear in ``__all__`` are excluded.
    - ``Package.subpackages`` contains only sub-packages whose short name
      appears in ``__all__``.

    Args:
        module_map: Mapping of dotted module name to resolved ``Module``.
        all_discovered: All discovered modules, used to infer trie structure.
        root: The root directory of the package being assembled.
        package_all_map: Mapping from dotted package name to the literal
            ``__all__`` frozenset, or ``None`` when ``__all__`` is absent.

    Returns:
        The assembled ``Package`` trie.
    """
    # Separate init modules from regular modules by parts key.
    init_modules_by_parts: dict[tuple[str, ...], Module] = {}
    regular_modules_by_parts: dict[tuple[str, ...], list[Module]] = {}
    parts_to_path: dict[tuple[str, ...], Path] = {}

    for dm in all_discovered:
        module = module_map.get(dm.dotted_name)
        if module is None:
            continue

        if dm.is_init:
            pkg_parts = tuple(dm.dotted_name.split("."))
            init_modules_by_parts[pkg_parts] = module
            parts_to_path[pkg_parts] = dm.source_path.parent
        else:
            pkg_parts = dm.package_parts
            regular_modules_by_parts.setdefault(pkg_parts, []).append(module)
            if pkg_parts not in parts_to_path:
                parts_to_path[pkg_parts] = dm.source_path.parent

    # Collect all unique package_parts tuples to identify every package node.
    all_pkg_parts: set[tuple[str, ...]] = set()
    for dm in all_discovered:
        if dm.is_init:
            all_pkg_parts.add(tuple(dm.dotted_name.split(".")))
        else:
            all_pkg_parts.add(dm.package_parts)

    def _make_package(parts: tuple[str, ...]) -> Package:
        """Recursively assemble a ``Package`` for the given parts prefix.

        Args:
            parts: Tuple of name components identifying the package node,
                e.g. ``("my_pkg", "sub")``.

        Returns:
            A ``Package`` whose ``modules`` are the direct members at this
            level and whose ``subpackages`` are all immediate children,
            assembled recursively.
        """
        name = ".".join(parts)
        path = parts_to_path.get(parts, root)

        explicit_all = package_all_map.get(name)
        init_module = init_modules_by_parts.get(parts)

        # Find immediate children (one level deeper).
        child_parts_set: set[tuple[str, ...]] = set()
        for pkg_parts in all_pkg_parts:
            if len(pkg_parts) == len(parts) + 1 and pkg_parts[: len(parts)] == parts:
                child_parts_set.add(pkg_parts)

        if explicit_all is not None:
            # When __all__ is defined, hoist all public symbols into a single
            # package-level Module (the resolved init module) and suppress
            # private sub-modules.  Only sub-packages explicitly named in
            # __all__ are kept.
            direct_modules: tuple[Module, ...] = (init_module,) if init_module is not None else ()

            filtered_children = {child for child in child_parts_set if child[-1] in explicit_all}
            subpackages = tuple(
                sorted(
                    (_make_package(child) for child in sorted(filtered_children)),
                    key=lambda p: p.name,
                )
            )
        else:
            # No __all__: include all regular modules plus the init module.
            all_direct = regular_modules_by_parts.get(parts, [])
            all_direct = [direct_module for direct_module in all_direct if direct_module.is_public]
            if init_module is not None:
                all_direct.append(init_module)
            direct_modules = tuple(sorted(all_direct, key=lambda m: m.name))
            subpackages = (_make_package(child) for child in sorted(child_parts_set))
            subpackages = sorted(
                (subpackage for subpackage in subpackages if subpackage.is_public), key=lambda p: p.name
            )

        return Package(
            name=name,
            path=path,
            modules=direct_modules,
            subpackages=tuple(subpackages),
        )

    # Determine the root package parts.
    if not all_pkg_parts:
        return Package(name=root.name, path=root, modules=(), subpackages=())

    # The root is the shortest parts tuple (there should be exactly one).
    root_parts = min(all_pkg_parts, key=len)
    return _make_package(root_parts)


def build_package(root: Path, config: Config) -> Package | Module:
    """Build a ``Package`` snapshot for the Python source rooted at *root*.

    When *root* is a single ``.py`` file, discovery is skipped and the file
    is visited directly.  When *root* is a directory, the full five-step
    pipeline runs:

    1. Discover all Python modules under *root*.
    2. Partition into non-init and init modules.
    3. Parallel-visit non-init modules via ``ProcessPoolExecutor``.
    4. Serially resolve each ``__init__.py`` against the accumulated map.
    5. Fold the completed map into a ``Package`` trie.

    Args:
        root: A path to either a single ``.py`` file or a package directory.
        config: Runtime configuration controlling workers, filters, etc.

    Returns:
        A ``Package`` containing the full public API surface of *root*. When
        *root* is a single file, the bare ``Module`` is returned directly.
    """
    if root.is_file():
        source = root.read_text(encoding="utf-8")
        return visit_module(source, root.stem)

    # 1. Discover all Python source files under root.
    all_discovered = discover(root, config)

    # 2. Partition into regular modules and __init__.py files.
    non_init_modules = [dm for dm in all_discovered if not dm.is_init]
    init_modules = [dm for dm in all_discovered if dm.is_init]

    # 3. Visit non-init modules in parallel.
    module_map: dict[str, Module] = {}

    with ProcessPoolExecutor(max_workers=config.max_workers) as executor:
        visited_modules = executor.map(_visit_worker, non_init_modules)
        for dm, module in zip(non_init_modules, visited_modules, strict=True):
            module_map[dm.dotted_name] = module

    # 4. Resolve __init__.py files serially, shallowest first, so each
    #    parent package is available in module_map before its children run.
    sorted_inits = sorted(init_modules, key=lambda dm: len(dm.package_parts))

    # Track the __all__ for each package so _build_trie can filter modules and
    # subpackages accordingly.  A value of None means __all__ was absent.
    package_all_map: dict[str, frozenset[str] | None] = {}

    for init_module in sorted_inits:
        source = init_module.source_path.read_text(encoding="utf-8")
        subpackage_names = _subpackage_names_at_level(init_module.package_parts, all_discovered)

        # Extract __all__ from the init source to record for the trie step.
        try:
            init_tree = ast.parse(source, feature_version=(3, 14))
        except SyntaxError:
            init_tree = None

        package_all_map[init_module.dotted_name] = extract_all(init_tree) if init_tree is not None else None

        module, _report = resolve_init(
            source,
            init_module.dotted_name,
            module_map,
            subpackage_names,
            config,
        )
        module_map[init_module.dotted_name] = module

    # 5. Fold the completed module map into a Package trie.
    return _build_trie(module_map, all_discovered, root, package_all_map)
