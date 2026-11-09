"""Public entry points for iceberg."""

__all__ = ["get_public_api", "get_public_api_report"]

from pathlib import Path

from sheridan.iceberg._config import Config, load_config
from sheridan.iceberg._exceptions import InvalidPathError
from sheridan.iceberg._models import Diagnostic, Module, Package, Report
from sheridan.iceberg._orchestrator import build_package, unresolved_name_warnings


def get_public_api(path: Path, *, config: Config | None = None) -> Package | Module:
    """Snapshot the public API rooted at ``path``.

    Args:
        path: File or directory to snapshot.
        config: Optional explicit configuration; when omitted, walks
            up from ``path`` looking for ``.iceberg.toml`` /
            ``pyproject.toml``.

    Returns:
        A ``Package`` describing the public API surface rooted at ``path``.

    Raises:
        InvalidPathError: If ``path`` does not exist, or is a file that
            does not end in ``.py``.
    """
    return get_public_api_report(path, config=config).api


def get_public_api_report(path: Path, *, config: Config | None = None, keep_going: bool = False) -> Report:
    """Snapshot the public API rooted at ``path`` and report the problems found.

    Args:
        path: File or directory to snapshot.
        config: Optional explicit configuration; when omitted, walks
            up from ``path`` looking for ``.iceberg.toml`` /
            ``pyproject.toml``.
        keep_going: Skip modules under a directory that cannot be read or
            parsed, and report each one as an ``"error"`` diagnostic, instead
            of raising on the first one.

    Returns:
        A ``Report`` holding the API (a ``Package``, or a ``Module`` for a
        single file) and its diagnostics: errors for skipped modules, then a
        warning for each exported name that no import binds.

    Raises:
        InvalidPathError: If ``path`` does not exist, or is a file that
            does not end in ``.py``.
        ParseError: If a module cannot be parsed, unless *keep_going* is set
            and ``path`` is a directory.
        SourceReadError: If a module cannot be read, unless *keep_going* is
            set and ``path`` is a directory.
    """
    path = Path(path).resolve()
    if not path.exists():
        raise InvalidPathError(f"path does not exist: {path}")
    if path.is_file() and path.suffix != ".py":
        raise InvalidPathError(f"not a .py file: {path} (expected a .py file or a Python package directory)")

    effective_config = config or load_config(path)
    errors: list[Diagnostic] | None = [] if keep_going else None
    api = build_package(path, effective_config, errors=errors)
    return Report(api=api, diagnostics=(*(errors or ()), *unresolved_name_warnings(api, path)))
