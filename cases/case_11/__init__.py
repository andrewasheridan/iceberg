"""Case 11 - re-exports names whose definitions live outside the package."""

import json
from collections import OrderedDict as Ordered
from math import sqrt

from ._core import area

__all__ = ["Ordered", "area", "json", "lazy_thing", "sqrt"]


def __getattr__(name: str) -> object:
    """Case 11 - provides ``lazy_thing`` dynamically."""
    if name == "lazy_thing":
        return object()
    raise AttributeError(name)
