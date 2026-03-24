"""Two-dimensional geometry primitives.

This package provides core geometric types and utilities for working with
points, circles, and rectangles in the Cartesian plane.

When ``iceberg show`` is run against this package, only the four names listed
in ``__all__`` are reported from ``__init__.py``.  Running with ``--use-ast``
instead reports each submodule (``point``, ``shapes``, ``utils``) individually,
showing their own ``__all__`` surfaces.

Public API:
    - :class:`~geometry.point.Point` — a 2-D coordinate
    - :class:`~geometry.shapes.Circle` — a circle defined by centre and radius
    - :class:`~geometry.shapes.Rectangle` — an axis-aligned rectangle
    - :func:`~geometry.utils.distance` — Euclidean distance between two points
"""

__all__ = [
    "Circle",
    "Point",
    "Rectangle",
    "distance",
]

from geometry.point import Point
from geometry.shapes import Circle, Rectangle
from geometry.utils import distance
