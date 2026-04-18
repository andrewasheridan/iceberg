"""Single-pass filesystem discovery of Python source modules.

Walks a package directory (or accepts a single ``.py`` file) and produces a
tuple of :class:`DiscoveredModule` values describing every Python module to
visit. Test modules are filtered out according to
:attr:`~sheridan.iceberg._config.Config.test_module_pattern`.
"""

__all__ = ["DiscoveredModule", "discover"]

from pathlib import Path

from sheridan.iceberg._config import Config
from sheridan.iceberg._exceptions import InvalidPathError
from sheridan.iceberg._models import DiscoveredModule

_PRUNED_DIRS = frozenset({"__pycache__", ".venv", ".git"})
"""Directory names that are unconditionally excluded from the filesystem walk."""


def _should_prune(name: str) -> bool:
    """Return ``True`` if a directory name should be excluded from the walk.

    Args:
        name: The bare directory name (not a full path).

    Returns:
        ``True`` for ``__pycache__``, ``.venv``, ``.git``, and any name that
        starts with ``'.'``.
    """
    return name in _PRUNED_DIRS or name.startswith(".")


def _compute_dotted_name(py_file: Path, root: Path) -> tuple[str, tuple[str, ...]]:
    """Compute the dotted module name and package_parts for a ``.py`` file.

    Walks upward from the file's parent directory, collecting directory names
    until *root* is reached or a component that is not a valid Python identifier
    is encountered. This supports both traditional packages (with
    ``__init__.py``) and namespace packages (directories without
    ``__init__.py``, such as the ``sheridan/`` layer in ``src/sheridan/iceberg/``).

    Args:
        py_file: Absolute path to the ``.py`` source file.
        root: The top-level search root passed to :func:`discover`. The walk
            stops when *current* reaches this directory.

    Returns:
        A two-tuple of ``(dotted_name, package_parts)`` where ``dotted_name``
        is the fully-qualified module name and ``package_parts`` is the tuple
        of ancestor directory names forming the dotted prefix (all components
        except the module's own contribution).
    """
    is_init = py_file.name == "__init__.py"
    parts: list[str] = []

    current = py_file.parent
    while current != root and current.name.isidentifier():
        parts.append(current.name)
        current = current.parent

    # parts is ordered from innermost to outermost; reverse to get top-down order
    parts.reverse()

    if is_init:
        # The module name IS the containing directory; package_parts are all
        # ancestors above it that are also packages.
        package_parts = tuple(parts[:-1]) if parts else ()
        dotted_name = ".".join(parts) if parts else py_file.parent.name
    else:
        package_parts = tuple(parts)
        dotted_name = ".".join([*parts, py_file.stem]) if parts else py_file.stem

    return dotted_name, package_parts


def _make_module(py_file: Path, root: Path) -> DiscoveredModule:
    """Build a :class:`DiscoveredModule` from a ``.py`` file path.

    Args:
        py_file: Absolute path to the ``.py`` source file.
        root: The top-level search root passed to :func:`discover`.
            The walk stops when *current* reaches this directory.

    Returns:
        A fully populated :class:`DiscoveredModule` instance.
    """
    is_init = py_file.name == "__init__.py"
    dotted_name, package_parts = _compute_dotted_name(py_file, root)

    return DiscoveredModule(
        dotted_name=dotted_name,
        source_path=py_file,
        is_init=is_init,
        package_parts=package_parts,
    )


def _discover_single_file(root: Path) -> tuple[DiscoveredModule, ...]:
    """Return a one-tuple for a single ``.py`` file input.

    Args:
        root: Path to a single ``.py`` source file.

    Returns:
        A one-tuple containing a :class:`DiscoveredModule` with
        ``package_parts = ()``, ``is_init = False``, and
        ``dotted_name = root.stem``.
    """
    module = DiscoveredModule(
        dotted_name=root.stem,
        source_path=root,
        is_init=False,
        package_parts=(),
    )
    return (module,)


def _discover_directory(root: Path, config: Config) -> tuple[DiscoveredModule, ...]:
    """Walk *root* once and return a tuple of all non-test Python modules found.

    The *name_root* passed to :func:`_make_module` is chosen based on whether
    *root* itself is a proper Python package (contains ``__init__.py``) or a
    namespace container such as a ``src/`` layout directory.  When *root* is a
    package, its parent is used so that *root*'s own name becomes part of every
    dotted module name.  When *root* is a namespace container, *root* itself is
    used so that its name is omitted from dotted names.

    Args:
        root: The package directory (or namespace container) to walk.
        config: Runtime configuration carrying the test-module filter pattern.

    Returns:
        A tuple of :class:`DiscoveredModule` values, one per qualifying
        ``.py`` file found under *root*.
    """
    # If root itself is a package, its name should appear in every dotted name,
    # so the naming root must be root's parent.  Otherwise (src/-layout or
    # plain namespace container), root's name must NOT appear, so root itself
    # is the naming root.
    name_root = root.parent if (root / "__init__.py").exists() else root

    results: list[DiscoveredModule] = []

    for dirpath, dirnames, filenames in root.walk():
        # Mutate dirnames in-place to prune unwanted subtrees.
        dirnames[:] = [d for d in dirnames if not _should_prune(d)]

        for filename in filenames:
            if not filename.endswith(".py"):
                continue

            py_file = dirpath / filename

            if config.test_module_pattern.search(str(py_file.as_posix())):
                continue

            results.append(_make_module(py_file, name_root))

    return tuple(results)


def discover(root: Path, config: Config) -> tuple[DiscoveredModule, ...]:
    """Discover all Python modules under *root*, filtered by *config*.

    Performs exactly one :meth:`~pathlib.Path.walk` call when *root* is a
    directory. Test modules are excluded via
    :attr:`~sheridan.iceberg._config.Config.test_module_pattern`.

    Args:
        root: A path to either a single ``.py`` file or a package directory.
        config: Runtime configuration used to filter test modules and control
            other discovery behaviour.

    Returns:
        A tuple of :class:`DiscoveredModule` values describing every
        qualifying Python source file found under *root*.

    Raises:
        InvalidPathError: If *root* does not exist on the filesystem.
    """
    if not root.exists():
        raise InvalidPathError(f"Path does not exist: {root}")

    if root.is_file():
        return _discover_single_file(root)

    return _discover_directory(root, config)
