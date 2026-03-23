"""Utility functions for the geometry package."""

__all__ = [
    "distance",
]

import math

from geometry.point import Point


def distance(p1: Point, p2: Point) -> float:
    """Return the Euclidean distance between two points.

    This is the public entry-point for distance calculations.  Internally it
    delegates to :func:`_euclidean`, which is a private helper excluded from
    ``__all__``.

    Args:
        p1: The first point.
        p2: The second point.

    Returns:
        The straight-line distance between *p1* and *p2*.
    """
    return _euclidean(p1.x, p1.y, p2.x, p2.y)


def _euclidean(x1: float, y1: float, x2: float, y2: float) -> float:
    """Compute the raw Euclidean distance from component coordinates.

    This helper is intentionally private — it is not listed in ``__all__``
    and therefore does not appear in the ``iceberg show`` output.

    Args:
        x1: x-coordinate of the first point.
        y1: y-coordinate of the first point.
        x2: x-coordinate of the second point.
        y2: y-coordinate of the second point.

    Returns:
        The Euclidean distance as a float.
    """
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
