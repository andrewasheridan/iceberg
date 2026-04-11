"""Orchestrator facade exposing the top-level ``get_public_api`` entry point."""

from pathlib import Path

from sheridan.iceberg._exceptions import InvalidPathError
from sheridan.iceberg._models import Package

__all__ = ["get_public_api"]


def get_public_api(path: Path) -> Package:
    """Return the public API snapshot for a Python package or module.

    Args:
        path: Filesystem path to a Python package directory or ``.py`` file.

    Returns:
        A ``Package`` instance describing the public API surface.

    Raises:
        InvalidPathError: If ``path`` does not exist on the filesystem.
        NotImplementedError: This function is not yet implemented.
    """
    if not path.exists():
        raise InvalidPathError(f"Path does not exist: {path}")
    raise NotImplementedError
