"""Circle and Rectangle shape classes for the geometry package."""

__all__ = [
    "Circle",
    "Rectangle",
]

import math

from geometry.point import Point


class _Shape:
    """Abstract base for closed 2-D shapes.

    This class is intentionally private (leading underscore) and therefore
    excluded from ``__all__``.  It exists only to share the ``area`` and
    ``perimeter`` property interface between concrete subclasses.
    """

    @property
    def area(self) -> float:
        """The area enclosed by the shape."""
        raise NotImplementedError

    @property
    def perimeter(self) -> float:
        """The length of the shape's boundary."""
        raise NotImplementedError


class Circle(_Shape):
    """A circle defined by a centre point and a radius.

    Attributes:
        DEFAULT_SEGMENTS: Default number of segments used in approximations.
        centre: The centre point of the circle.
        radius: The radius of the circle (must be positive).
    """

    DEFAULT_SEGMENTS: int = 64

    def __init__(self, centre: Point, radius: float) -> None:
        """Initialise a Circle.

        Args:
            centre: The centre point of the circle.
            radius: The radius; must be strictly positive.

        Raises:
            ValueError: If *radius* is not positive.
        """
        if radius <= 0:
            raise ValueError(f"radius must be positive, got {radius}")
        self.centre: Point = centre
        self.radius: float = radius

    @property
    def area(self) -> float:
        """The area enclosed by the circle (π r²)."""
        return math.pi * self.radius**2

    @property
    def perimeter(self) -> float:
        """The circumference of the circle (2π r)."""
        return 2 * math.pi * self.radius

    def contains(self, point: Point) -> bool:
        """Return True if *point* lies inside or on the circle boundary.

        Args:
            point: The point to test.

        Returns:
            ``True`` when the point is within the circle.
        """
        return self.centre.distance_to(point) <= self.radius

    @classmethod
    def unit(cls) -> Circle:
        """Return a unit circle centred at the origin.

        Returns:
            A :class:`Circle` with centre ``(0, 0)`` and radius ``1``.
        """
        return cls(centre=Point(0.0, 0.0), radius=1.0)

    @staticmethod
    def is_valid_radius(r: float) -> bool:
        """Return True if *r* is an acceptable radius value.

        Args:
            r: The candidate radius.

        Returns:
            ``True`` when *r* is strictly greater than zero.
        """
        return r > 0


class Rectangle(_Shape):
    """An axis-aligned rectangle defined by two corner points.

    Attributes:
        MIN_SIDE: The minimum allowed length for either side.
        top_left: The top-left corner of the rectangle.
        bottom_right: The bottom-right corner of the rectangle.
    """

    MIN_SIDE: float = 0.0

    def __init__(self, top_left: Point, bottom_right: Point) -> None:
        """Initialise a Rectangle from its two defining corners.

        Args:
            top_left: The top-left corner (smaller x, larger y).
            bottom_right: The bottom-right corner (larger x, smaller y).

        Raises:
            ValueError: If the corners do not form a valid rectangle.
        """
        if top_left.x >= bottom_right.x or top_left.y >= bottom_right.y:
            raise ValueError("top_left must be strictly above and left of bottom_right")
        self.top_left: Point = top_left
        self.bottom_right: Point = bottom_right

    @property
    def width(self) -> float:
        """The horizontal extent of the rectangle."""
        return self.bottom_right.x - self.top_left.x

    @property
    def height(self) -> float:
        """The vertical extent of the rectangle."""
        return self.bottom_right.y - self.top_left.y

    @property
    def area(self) -> float:
        """The area enclosed by the rectangle (width * height)."""
        return self.width * self.height

    @property
    def perimeter(self) -> float:
        """The total length of the rectangle's boundary (2 * (width + height))."""
        return 2 * (self.width + self.height)

    def contains(self, point: Point) -> bool:
        """Return True if *point* lies inside or on the rectangle boundary.

        Args:
            point: The point to test.

        Returns:
            ``True`` when the point is within the bounding box.
        """
        return self.top_left.x <= point.x <= self.bottom_right.x and self.top_left.y <= point.y <= self.bottom_right.y
