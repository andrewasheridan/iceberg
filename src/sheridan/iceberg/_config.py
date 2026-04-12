"""Runtime configuration loading for the iceberg package.

Searches for configuration in ``.iceberg.toml`` or a ``[tool.iceberg]`` table
inside ``pyproject.toml``, walking upward from the given start path. Falls back
to built-in defaults when no configuration file is found.
"""

__all__ = ["Config", "load_config"]

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from sheridan.iceberg._exceptions import ConfigError

_DEFAULT_TEST_MODULE_PATTERN = r"(^|/)tests?(/|$)|(^|/)test_[^/]*\.py$|_test\.py$"
"""Default regex pattern used to identify test module paths when none is configured."""

_ALLOWED_KEYS = frozenset({"test_module_pattern", "include_subpackages_in_all", "max_workers"})
"""Set of recognised keys in the ``[tool.iceberg]`` / ``.iceberg.toml`` configuration table."""


def _default_test_pattern() -> re.Pattern[str]:
    """Return the compiled default test module pattern.

    Returns:
        A compiled ``re.Pattern`` matching common test module path conventions.
    """
    return re.compile(_DEFAULT_TEST_MODULE_PATTERN)


@dataclass(frozen=True, slots=True)
class Config:
    """Runtime configuration for iceberg.

    Attributes:
        test_module_pattern: Compiled regular expression used to identify test
            modules by their file path. Matched paths are excluded from the
            public API surface.
        include_subpackages_in_all: When ``True``, subpackage names are
            included when synthesising ``__all__`` for a package.
        max_workers: Maximum number of worker threads used for parallel
            processing. ``None`` lets the executor choose based on CPU count.
    """

    test_module_pattern: re.Pattern[str] = field(default_factory=_default_test_pattern)
    """Compiled regex matched against module paths to identify test files."""

    include_subpackages_in_all: bool = True
    """When ``True``, subpackage names are included in synthesised ``__all__`` lists."""

    max_workers: int | None = None
    """Maximum worker threads for parallel processing; ``None`` defers to the executor default."""


def _build_config(table: dict[str, object]) -> Config:
    """Construct a :class:`Config` from a raw TOML mapping.

    Args:
        table: The parsed TOML table containing iceberg configuration keys.

    Returns:
        A fully validated :class:`Config` instance.

    Raises:
        ConfigError: If the table contains unknown keys, or if any value has
            an incorrect type or cannot be compiled as a regular expression.
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
            raise ConfigError(f"'test_module_pattern' must be a string, got {type(pattern_value).__name__!r}.")

        try:
            pattern = re.compile(pattern_value)
        except re.error as exc:
            raise ConfigError(f"'test_module_pattern' is not a valid regular expression: {exc}") from exc
    else:
        pattern = _default_test_pattern()

    include_subpackages: bool
    if "include_subpackages_in_all" in table:
        include_value = table["include_subpackages_in_all"]

        if not isinstance(include_value, bool):
            raise ConfigError(f"'include_subpackages_in_all' must be a boolean, got {type(include_value).__name__!r}.")

        include_subpackages = include_value
    else:
        include_subpackages = True

    max_workers: int | None
    if "max_workers" in table:
        workers_value = table["max_workers"]

        if not isinstance(workers_value, int):
            raise ConfigError(f"'max_workers' must be an integer, got {type(workers_value).__name__!r}.")

        if workers_value < 1:
            raise ConfigError(f"'max_workers' must be a positive integer, got {workers_value!r}.")

        max_workers = workers_value
    else:
        max_workers = None

    return Config(
        test_module_pattern=pattern,
        include_subpackages_in_all=include_subpackages,
        max_workers=max_workers,
    )


def _parse_toml(text: str, source: Path) -> dict[str, object]:
    """Parse a TOML string, wrapping errors as :class:`ConfigError`.

    Args:
        text: Raw TOML source text.
        source: Path to the file being parsed, used in error messages.

    Returns:
        The parsed TOML document as a nested mapping.

    Raises:
        ConfigError: If the text is not valid TOML.
    """
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Failed to parse TOML in {source}: {exc}") from exc


def _read_text(path: Path) -> str:
    """Read a file's text contents, wrapping errors as :class:`ConfigError`.

    Args:
        path: Absolute path to the file to read.

    Returns:
        The full text content of the file.

    Raises:
        ConfigError: If the file cannot be read.
    """
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Failed to read configuration file {path}: {exc}") from exc


def _ancestors(start: Path) -> list[Path]:
    """Return ``start`` and all of its parent directories, from deepest to root.

    Args:
        start: The directory from which to begin the upward walk.

    Returns:
        A list of :class:`~pathlib.Path` objects starting at ``start`` and
        ending at the filesystem root.
    """
    resolved = start.resolve()
    base = resolved if resolved.is_dir() else resolved.parent
    return [base, *base.parents]


def load_config(start: Path) -> Config:
    """Load iceberg configuration by searching upward from *start*.

    The search proceeds in two passes:

    1. Walk upward from ``start`` (inclusive) checking each directory for an
       ``.iceberg.toml`` file. The first one found is parsed and returned.
    2. If no ``.iceberg.toml`` is found, walk upward again looking for a
       ``pyproject.toml`` that contains a ``[tool.iceberg]`` table. The first
       match is used.
    3. If neither file is found, return a :class:`Config` built from defaults.

    Args:
        start: The directory (or file path whose parent directory) to begin
            searching from. Typically the path being analysed.

    Returns:
        A :class:`Config` populated from the discovered configuration file, or
        the default :class:`Config` if no configuration is found.

    Raises:
        ConfigError: If a configuration file is found but cannot be read,
            contains invalid TOML, has unknown keys, or has type-incorrect
            values.
    """
    ancestors = _ancestors(start)

    for directory in ancestors:
        candidate = directory / ".iceberg.toml"
        if candidate.is_file():
            text = _read_text(candidate)
            doc = _parse_toml(text, candidate)
            return _build_config(doc)

    for directory in ancestors:
        candidate = directory / "pyproject.toml"
        if candidate.is_file():
            text = _read_text(candidate)
            doc = _parse_toml(text, candidate)
            tool_section = doc.get("tool", {})
            if not isinstance(tool_section, dict):
                raise ConfigError(
                    f"Expected '[tool]' to be a table in {candidate}, got {type(tool_section).__name__!r}."
                )
            if "iceberg" not in tool_section:
                continue
            iceberg_section = tool_section["iceberg"]
            if not isinstance(iceberg_section, dict):
                raise ConfigError(
                    f"Expected '[tool.iceberg]' to be a table in {candidate}, got {type(iceberg_section).__name__!r}."
                )
            return _build_config(iceberg_section)

    return Config()
