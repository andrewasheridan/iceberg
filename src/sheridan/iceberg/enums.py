"""Enumerations used across sheridan-iceberg."""

__all__ = [
    "ShowFormat",
]

from enum import StrEnum, auto


class ShowFormat(StrEnum):
    """Supported output formats for the show command."""

    tree = auto()
    json = auto()
