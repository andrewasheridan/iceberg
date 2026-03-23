__all__ = [
    "Circle",
    "Rectangle",
]


from geometry.point import Point


class _Shape:
    @property
    def area(self) -> float: ...

    @property
    def perimeter(self) -> float: ...


class Circle(_Shape):
    DEFAULT_SEGMENTS: int = 64

    def __init__(self, centre: Point, radius: float) -> None:
        self.centre: Point = centre
        self.radius: float = radius

    @property
    def area(self) -> float: ...

    @property
    def perimeter(self) -> float: ...

    def contains(self, point: Point) -> bool: ...

    @classmethod
    def unit(cls) -> Circle: ...

    @staticmethod
    def is_valid_radius(r: float) -> bool: ...


class Rectangle(_Shape):
    MIN_SIDE: float = 0.0

    def __init__(self, top_left: Point, bottom_right: Point) -> None:
        self.top_left: Point = top_left
        self.bottom_right: Point = bottom_right

    @property
    def width(self) -> float: ...

    @property
    def height(self) -> float: ...

    @property
    def area(self) -> float: ...

    @property
    def perimeter(self) -> float: ...

    def contains(self, point: Point) -> bool: ...
