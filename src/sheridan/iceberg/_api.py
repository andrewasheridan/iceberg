"""Public entry point for iceberg."""

__all__ = ["get_public_api"]

from pathlib import Path

from sheridan.iceberg._config import Config, load_config
from sheridan.iceberg._exceptions import InvalidPathError
from sheridan.iceberg._models import Package
from sheridan.iceberg._orchestrator import build_package


def get_public_api(path: Path, *, config: Config | None = None) -> Package:
    """Return a snapshot of the public API rooted at ``path``.

    Args:
        path: File or directory to snapshot.
        config: Optional explicit configuration; when omitted, walks
            up from ``path`` looking for ``.iceberg.toml`` /
            ``pyproject.toml``.

    Returns:
        A ``Package`` describing the public API surface rooted at ``path``.

    Raises:
        InvalidPathError: If ``path`` does not exist.
    """
    if not path.exists():
        raise InvalidPathError(f"path does not exist: {path}")
    effective_config = config if config is not None else load_config(path)
    return build_package(path, effective_config)
