__all__ = [
    "Point",
]


class Point:
    def __init__(self, x: float, y: float) -> None:
        self.x: float = x
        self.y: float = y

    def translate(self, dx: float, dy: float) -> Point: ...
    def distance_to(self, other: Point) -> float: ...
