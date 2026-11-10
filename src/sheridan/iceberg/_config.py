"""Load the runtime configuration of the iceberg package.

The module looks for the configuration in ``.iceberg.toml`` or in a
``[tool.iceberg]`` table in ``pyproject.toml``. It starts at the given path and
goes up through the parent directories. If it finds no configuration file, it
uses the built-in default values.
"""

__all__ = ["Config", "load_config", "load_config_file"]

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from sheridan.iceberg._exceptions import ConfigError

_DEFAULT_TEST_MODULE_PATTERN = r"(^|/)tests?(/|$)|(^|/)test_[^/]*\.py$|_test\.py$"
"""The default regex that identifies the paths of test modules, if the configuration gives none."""

_ALLOWED_KEYS = frozenset({"test_module_pattern", "max_workers", "exclude"})
"""The set of known keys in the ``[tool.iceberg]`` or ``.iceberg.toml`` configuration table."""


def _default_test_pattern() -> re.Pattern[str]:
    """Compile the default test module pattern.

    Returns:
        A compiled ``re.Pattern`` that matches the usual paths of test modules.
    """
    return re.compile(_DEFAULT_TEST_MODULE_PATTERN)


@dataclass(frozen=True, slots=True)
class Config:
    """The runtime configuration of iceberg.

    Attributes:
        test_module_pattern: The compiled regular expression that identifies
            test modules. iceberg searches for it in the POSIX path of each
            file, relative to the parent of the analyzed directory (for example
            ``pkg/sub/mod.py``). The public API does not include matched paths.
        max_workers: The number of worker processes that parse modules. With
            the default value ``1``, iceberg parses in the same process. This
            is the fastest for usual packages. With values above ``1``, iceberg
            parses in a process pool. This helps only for very large trees. The
            script that calls iceberg must then be safe to import (it must use
            ``if __name__ == "__main__":``).
        exclude: Glob patterns. iceberg compares them with the POSIX path of
            each directory and file, relative to the analyzed directory (for
            example ``sub/mod.py``). It uses
            :meth:`pathlib.PurePath.full_match`, so ``**`` matches zero or more
            directories. iceberg does not go into matched directories, and it
            skips matched files.
    """

    test_module_pattern: re.Pattern[str] = field(default_factory=_default_test_pattern)
    """The compiled regex that iceberg compares with module paths to identify test files."""

    max_workers: int = 1
    """The number of worker processes that parse modules. With ``1`` (the default), the parse is in-process."""

    exclude: tuple[str, ...] = ()
    """Glob patterns, relative to the analyzed directory, for the paths to skip."""


def _build_config(table: dict[str, object]) -> Config:
    """Build a :class:`Config` from a raw TOML mapping.

    Args:
        table: The parsed TOML table with the iceberg configuration keys.

    Returns:
        A fully validated :class:`Config` instance.

    Raises:
        ConfigError: If the table has unknown keys, if a value has an incorrect
            type, or if the function cannot compile a value as a regular
            expression.
    """
    unknown = set(table.keys()) - _ALLOWED_KEYS
    if unknown:
        raise ConfigError(
            f"Unknown configuration key(s): {sorted(unknown)}. Allowed keys are: {sorted(_ALLOWED_KEYS)}."
        )

    pattern: re.Pattern[str]
    if "test_module_pattern" in table:
        pattern_value = table["test_module_pattern"]

        if not isinstance(pattern_value, str):
            raise ConfigError(f"'test_module_pattern' must be a string, not {type(pattern_value).__name__!r}.")

        try:
            pattern = re.compile(pattern_value)
        except re.error as exc:
            raise ConfigError(f"'test_module_pattern' is not a valid regular expression: {exc}") from exc
    else:
        pattern = _default_test_pattern()

    max_workers: int
    if "max_workers" in table:
        workers_value = table["max_workers"]

        # bool is a subclass of int. Without this check, `max_workers = true` gives 1.
        if isinstance(workers_value, bool) or not isinstance(workers_value, int):
            raise ConfigError(f"'max_workers' must be an integer, not {type(workers_value).__name__!r}.")

        if workers_value < 1:
            raise ConfigError(f"'max_workers' must be a positive integer, not {workers_value!r}.")

        max_workers = workers_value
    else:
        max_workers = 1

    exclude: tuple[str, ...] = ()
    if "exclude" in table:
        exclude_value = table["exclude"]

        if not isinstance(exclude_value, list) or not all(isinstance(item, str) for item in exclude_value):
            raise ConfigError(f"'exclude' must be a list of strings, not {exclude_value!r}.")

        exclude = tuple(exclude_value)

    return Config(
        test_module_pattern=pattern,
        max_workers=max_workers,
        exclude=exclude,
    )


def _parse_toml(text: str, source: Path) -> dict[str, object]:
    """Parse a TOML string, and wrap the errors in :class:`ConfigError`.

    Args:
        text: The raw TOML source text.
        source: The path to the file that the function parses. Error messages
            use this path.

    Returns:
        The parsed TOML document as a nested mapping.

    Raises:
        ConfigError: If the text is not valid TOML.
    """
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Cannot parse the TOML in {source}: {exc}") from exc


def _read_text(path: Path) -> str:
    """Read the text of a file, and wrap the errors in :class:`ConfigError`.

    Args:
        path: The absolute path to the file to read.

    Returns:
        The full text of the file.

    Raises:
        ConfigError: If the function cannot read the file.
    """
    try:
        # pragma: no mutate start, codec names ignore case, and the locale encoding of the test machines is UTF-8
        return path.read_text(encoding="utf-8")
        # pragma: no mutate end
    except OSError as exc:
        raise ConfigError(f"Cannot read the configuration file {path}: {exc}") from exc


def _ancestors(start: Path) -> list[Path]:
    """List ``start`` and all its parent directories, from the deepest to the root.

    Args:
        start: The directory where the upward search starts.

    Returns:
        A list of :class:`~pathlib.Path` objects. The list starts at ``start``
        and stops at the root of the filesystem.
    """
    resolved = start.resolve()
    # pragma: no mutate start, a file contains no configuration file, thus the search also continues at the parent
    base = resolved if resolved.is_dir() else resolved.parent
    # pragma: no mutate end

    return [base, *base.parents]


def _pyproject_section(candidate: Path) -> dict[str, object] | None:
    """Extract the ``[tool.iceberg]`` table from a ``pyproject.toml`` file.

    Args:
        candidate: The path to the ``pyproject.toml`` file.

    Returns:
        The ``[tool.iceberg]`` table, or ``None`` if the file has no such table.

    Raises:
        ConfigError: If the function cannot read the file, if the file has
            TOML errors, or if ``[tool]`` or ``[tool.iceberg]`` is not a table.
    """
    doc = _parse_toml(_read_text(candidate), candidate)
    tool_section = doc.get("tool", {})

    if not isinstance(tool_section, dict):
        raise ConfigError(f"'[tool]' in {candidate} must be a table, not {type(tool_section).__name__!r}.")

    if "iceberg" not in tool_section:
        return None

    iceberg_section = tool_section["iceberg"]
    if not isinstance(iceberg_section, dict):
        raise ConfigError(f"'[tool.iceberg]' in {candidate} must be a table, not {type(iceberg_section).__name__!r}.")

    return iceberg_section


def load_config(start: Path) -> Config:
    """Load the iceberg configuration. Search *start* and its parent directories.

    The search starts at ``start`` and goes up. It examines each directory,
    the nearest one first:

    1. If the directory has an ``.iceberg.toml`` file, the function parses and
       uses it.
    2. If the directory has no ``.iceberg.toml`` but has a ``pyproject.toml``,
       this directory is the project root. The search stops there. The
       function uses the ``[tool.iceberg]`` table of the file. If there is no
       table, it uses the default values.
    3. If the function finds no file, it uses the default values.

    Args:
        start: The directory where the search starts. If it is a file path,
            the search starts at its parent directory. Usually, this is the
            analyzed path.

    Returns:
        A :class:`Config` with the values from the configuration file that the
        search found. If the search found no file, the default :class:`Config`.

    Raises:
        ConfigError: If the function finds a configuration file but cannot read
            it, or if the file has TOML errors, unknown keys or values of the
            wrong type.
    """
    for directory in _ancestors(start):
        candidate = directory / ".iceberg.toml"
        if candidate.is_file():
            return _build_config(_parse_toml(_read_text(candidate), candidate))

        candidate = directory / "pyproject.toml"
        if candidate.is_file():
            section = _pyproject_section(candidate)
            return Config() if section is None else _build_config(section)

    return Config()


def load_config_file(path: Path) -> Config:
    """Load the iceberg configuration from one named file. Do not search.

    If the name of the file is ``pyproject.toml``, the function reads its
    ``[tool.iceberg]`` table. If there is no table, it uses the default values.
    The function reads all other files in the same way as an ``.iceberg.toml``
    file, with the keys at the top level.

    Args:
        path: The path to the configuration file.

    Returns:
        A :class:`Config` with the values from the file.

    Raises:
        ConfigError: If the file does not exist, if the function cannot read
            it, or if the file has TOML errors, unknown keys or values of the
            wrong type.
    """
    if not path.is_file():
        raise ConfigError(f"The configuration file does not exist: {path}")

    if path.name == "pyproject.toml":
        section = _pyproject_section(path)
        return Config() if section is None else _build_config(section)

    return _build_config(_parse_toml(_read_text(path), path))
