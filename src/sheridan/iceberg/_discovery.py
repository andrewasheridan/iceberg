"""Find the Python source modules on the filesystem in one pass.

The module walks through a package directory (or accepts one ``.py`` file). It
makes a tuple of :class:`DiscoveredModule` values, one for each Python module to
visit. It removes the test modules with
:attr:`~sheridan.iceberg._config.Config.test_module_pattern`.
"""

__all__ = ["DiscoveredModule", "discover"]

import keyword
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from sheridan.iceberg._config import Config
from sheridan.iceberg._exceptions import InvalidPathError
from sheridan.iceberg._models import _is_public_module_stem


@dataclass(frozen=True, slots=True)
class DiscoveredModule:
    """One Python source file that the discovery found.

    Attributes:
        dotted_name: The fully qualified dotted module name, for example
            ``pkg.sub.mod``.
        source_path: The absolute path to the ``.py`` file on disk.
        is_init: ``True`` if the file is an ``__init__.py``.
        package_parts: A tuple of the names of the parent directories that make
            the dotted prefix. It does not include the stem of the module. It
            is empty for top-level modules.
    """

    dotted_name: str
    """The fully qualified dotted module name, for example ``"pkg.sub.mod"``."""

    source_path: Path
    """The absolute path to the ``.py`` source file on disk."""

    is_init: bool
    """``True`` if the file is an ``__init__.py``. ``False`` if it is a different file."""

    package_parts: tuple[str, ...]
    """The names of the parent directories that make the dotted prefix, without the module stem."""

    @property
    def is_public(self) -> bool:
        *_, stem = self.dotted_name.split(".")
        return _is_public_module_stem(stem)


_PRUNED_DIRS = frozenset(
    {"__pycache__", ".venv", ".git", "build", "dist", "venv", "env", "node_modules", "site-packages"}
)
"""The directory names that the filesystem walk always skips."""


def _is_importable_name(name: str) -> bool:
    """Check if *name* can be a component of an import statement.

    Args:
        name: A bare directory name or file stem.

    Returns:
        ``True`` if *name* is a valid Python identifier and is not a keyword.
    """
    return name.isidentifier() and not keyword.iskeyword(name)


def _should_prune(name: str) -> bool:
    """Check if the walk must skip a directory name.

    Args:
        name: The bare directory name (not a full path).

    Returns:
        ``True`` for these names:

        - A name in :data:`_PRUNED_DIRS` (``__pycache__``, ``build``,
          ``dist``, ``venv`` and other names).
        - A name that you cannot import (not an identifier, or a keyword).
          Examples are ``.git`` and names that end with ``.egg-info``.

        Modules in such a directory are not source, or you cannot import them.
        Thus, the walk skips them silently.
    """
    return name in _PRUNED_DIRS or not _is_importable_name(name)


def _is_excluded(path: Path, root: Path, patterns: tuple[str, ...]) -> bool:
    """Check if *path* matches one of the user's ``exclude`` glob patterns.

    Args:
        path: A directory or file below *root*.
        root: The analyzed directory. The patterns are relative to it.
        patterns: Glob patterns from :attr:`~sheridan.iceberg._config.Config.exclude`.

    Returns:
        ``True`` if the POSIX path of *path* relative to *root* fully matches
        one of the patterns.
    """
    relative = PurePosixPath(path.relative_to(root).as_posix())

    return any(relative.full_match(pattern) for pattern in patterns)


def _compute_dotted_name(py_file: Path, root: Path) -> tuple[str, tuple[str, ...]]:
    """Compute the dotted module name and the package_parts of a ``.py`` file.

    The function starts at the parent directory of the file and goes up. It
    collects the directory names until it gets to *root*, or to a component
    that is not a valid Python identifier. Thus, it works for usual packages
    (with ``__init__.py``) and for namespace packages (directories without
    ``__init__.py``). An example of a namespace package is the ``sheridan/``
    layer in ``src/sheridan/iceberg/``.

    Args:
        py_file: The absolute path to the ``.py`` source file.
        root: The top-level search root that :func:`discover` got. The walk
            stops when *current* gets to this directory.

    Returns:
        A tuple ``(dotted_name, package_parts)``. ``dotted_name`` is the fully
        qualified module name. ``package_parts`` is the tuple of the names of
        the parent directories that make the dotted prefix. It has all the
        components, but not the component of the module.
    """
    is_init = py_file.name == "__init__.py"
    parts: list[str] = []

    current = py_file.parent
    while current != root and current.name.isidentifier():
        parts.append(current.name)
        current = current.parent

    # parts goes from the innermost to the outermost directory. Reverse it to get top-down order.
    parts.reverse()

    if is_init:
        # The module name is the name of the directory that holds the file.
        # package_parts are all the parent directories above it that are also packages.
        package_parts = tuple(parts[:-1])
        dotted_name = ".".join(parts) if parts else py_file.parent.name
    else:
        package_parts = tuple(parts)
        dotted_name = ".".join([*parts, py_file.stem])

    return dotted_name, package_parts


def _make_module(py_file: Path, root: Path) -> DiscoveredModule:
    """Build a :class:`DiscoveredModule` from a ``.py`` file path.

    Args:
        py_file: The absolute path to the ``.py`` source file.
        root: The top-level search root that :func:`discover` got.
            The walk stops when *current* gets to this directory.

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
    """Build a one-tuple for an input that is one ``.py`` file.

    Args:
        root: The path to one ``.py`` source file.

    Returns:
        A one-tuple that holds a :class:`DiscoveredModule` with
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
    """Walk through *root* one time and collect all the Python modules that are not tests.

    The function uses the *root* from the user as it is. It uses
    ``root.parent`` as the limit for names. Thus, the name of *root* is part
    of each dotted module name.

    Args:
        root: The package directory (or namespace container) to walk through.
        config: The runtime configuration with the filter pattern for test
            modules and the ``exclude`` globs. The function searches for the
            test pattern in the POSIX path of each file, relative to
            ``root.parent``. Thus, the path starts with the name of *root*. The
            function compares the ``exclude`` globs with paths relative to
            *root*.

    Returns:
        A tuple of :class:`DiscoveredModule` values, one for each applicable
        ``.py`` file below *root*. The function skips directories below *root*
        and file stems that are not names that you can import. It never skips
        *root*.
    """
    # The path from the user has authority. Always use root.parent, so that
    # the name of root is part of each dotted module name.
    name_root = root.parent

    results: list[DiscoveredModule] = []

    for dirpath, dirnames, filenames in root.walk():
        # Change dirnames in place, so that the walk does not go into unwanted subtrees.
        kept_dirs: list[str] = []
        for d in dirnames:
            if not _should_prune(d) and not _is_excluded(dirpath / d, root, config.exclude):
                kept_dirs.append(d)

        dirnames[:] = kept_dirs

        for filename in filenames:
            if not filename.endswith(".py"):
                continue

            # You cannot import a file such as my-script.py. Skip it silently.
            if not _is_importable_name(filename.removesuffix(".py")):
                continue

            py_file = dirpath / filename

            # Use the path relative to root.parent (with the name of root). Thus,
            # directories above root, such as ~/tests/, never match.
            if config.test_module_pattern.search(py_file.relative_to(name_root).as_posix()):
                continue

            if _is_excluded(py_file, root, config.exclude):
                continue

            results.append(_make_module(py_file, name_root))

    return tuple(results)


def discover(root: Path, config: Config) -> tuple[DiscoveredModule, ...]:
    """Find all the Python modules below *root*, and apply the filters in *config*.

    If *root* is a directory, the function calls :meth:`~pathlib.Path.walk`
    exactly one time. It removes the test modules with
    :attr:`~sheridan.iceberg._config.Config.test_module_pattern`.

    Args:
        root: The path to one ``.py`` file or to a package directory.
        config: The runtime configuration. It sets the filter for test modules
            and other options of the discovery.

    Returns:
        A tuple of :class:`DiscoveredModule` values, one for each applicable
        Python source file below *root*.

    Raises:
        InvalidPathError: If *root* does not exist on the filesystem.
    """
    if not root.exists():
        raise InvalidPathError(f"Path does not exist: {root}")

    if root.is_file():
        return _discover_single_file(root)

    return _discover_directory(root, config)
