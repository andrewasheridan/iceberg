"""Dataclass models representing the public API surface captured by iceberg."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Package"]


@dataclass(frozen=True, slots=True)
class Package:
    """A Python package's public API surface.

    This is a stub; fields will be added in the models implementation step.
    """
