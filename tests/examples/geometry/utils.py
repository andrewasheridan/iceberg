__all__ = [
    "distance",
]


from geometry.point import Point


def distance(p1: Point, p2: Point) -> float: ...


def _euclidean(x1: float, y1: float, x2: float, y2: float) -> float: ...
