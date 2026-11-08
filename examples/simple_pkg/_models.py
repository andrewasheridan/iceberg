"""Internal models for simple_pkg."""

from dataclasses import dataclass

__all__ = ["MyClass"]


@dataclass
class MyClass:
    """A simple dataclass model."""

    name: str
