"""Provide the public entry points of iceberg."""

__all__ = ["get_public_api", "get_public_api_report"]

from pathlib import Path

from sheridan.iceberg._config import Config, load_config
from sheridan.iceberg._exceptions import InvalidPathError
from sheridan.iceberg._models import Diagnostic, Module, Package, Report
from sheridan.iceberg._orchestrator import build_package, unresolved_name_warnings


def get_public_api(path: Path, *, config: Config | None = None) -> Package | Module:
    """Snapshot the public API at ``path``.

    Args:
        path: The file or directory to snapshot.
        config: An optional explicit configuration. If you do not give it,
            the function looks for ``.iceberg.toml`` or ``pyproject.toml`` in
            ``path`` and its parent directories.

    Returns:
        A ``Package`` that describes the public API at ``path``.

    Raises:
        InvalidPathError: If ``path`` does not exist, or if it is a file that
            does not end in ``.py``.
    """
    return get_public_api_report(path, config=config).api


def get_public_api_report(path: Path, *, config: Config | None = None, keep_going: bool = False) -> Report:
    """Snapshot the public API at ``path`` and report the problems that the analysis finds.

    Args:
        path: The file or directory to snapshot.
        config: An optional explicit configuration. If you do not give it,
            the function looks for ``.iceberg.toml`` or ``pyproject.toml`` in
            ``path`` and its parent directories.
        keep_going: If True, skip each module in a directory that the
            function cannot read or parse, and report it as an ``"error"``
            diagnostic. If False, raise an exception at the first bad module.

    Returns:
        A ``Report`` that holds the API and its diagnostics. The API is a
        ``Package``, or a ``Module`` for one file. The diagnostics are errors
        for the skipped modules, then a warning for each exported name that no
        import binds.

    Raises:
        InvalidPathError: If ``path`` does not exist, or if it is a file that
            does not end in ``.py``.
        ParseError: If the function cannot parse a module. This does not
            occur if *keep_going* is True and ``path`` is a directory.
        SourceReadError: If the function cannot read a module. This does not
            occur if *keep_going* is True and ``path`` is a directory.
    """
    path = Path(path).resolve()

    if not path.exists():
        raise InvalidPathError(f"path does not exist: {path}")

    if path.is_file() and path.suffix != ".py":
        raise InvalidPathError(f"not a .py file: {path} (give a .py file or a Python package directory)")

    effective_config = config or load_config(path)
    errors: list[Diagnostic] | None = [] if keep_going else None
    api = build_package(path, effective_config, errors=errors)

    warnings = unresolved_name_warnings(api, path)
    diagnostics = (*(errors or ()), *warnings)

    return Report(api=api, diagnostics=diagnostics)
