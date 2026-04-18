"""Nested package fixture with public and private subpackages."""

from nested_pkg.public_sub import PublicSub

__all__ = ["PublicSub", "top_level_func"]


def top_level_func() -> None:
    """A function defined directly on the top-level package."""
    ...
