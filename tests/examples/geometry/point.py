"""A two-dimensional point in the Cartesian plane."""

__all__ = [
    "Point",
]

import math


class Point:
    """An immutable point in 2-D Cartesian space.

    Attributes:
        x: The horizontal coordinate.
        y: The vertical coordinate.
    """

    def __init__(self, x: float, y: float) -> None:
        """Initialise a Point at coordinates (*x*, *y*).

        Args:
            x: The horizontal coordinate.
            y: The vertical coordinate.
        """
        self.x: float = x
        self.y: float = y

    def translate(self, dx: float, dy: float) -> Point:
        """Return a new Point shifted by (*dx*, *dy*).

        Args:
            dx: Horizontal displacement.
            dy: Vertical displacement.

        Returns:
            A new :class:`Point` with the applied offset.
        """
        return Point(self.x + dx, self.y + dy)

    def distance_to(self, other: Point) -> float:
        """Return the Euclidean distance from this point to *other*.

        Args:
            other: The target point.

        Returns:
            The straight-line distance between the two points.
        """
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)
