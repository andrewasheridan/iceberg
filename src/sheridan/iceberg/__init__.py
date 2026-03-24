"""sheridan-iceberg: enforce __all__ correctness in Python modules."""

__all__ = [
    "__version__",
    "get_public_api",
]

import importlib.metadata

from sheridan.iceberg.api import get_public_api

try:
    __version__: str = importlib.metadata.version("sheridan-iceberg")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0+unknown"
