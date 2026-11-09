"""Case 14 - overloaded functions and methods."""

from typing import overload


@overload
def area(side: int) -> int: ...
@overload
def area(width: float, height: float) -> float: ...
def area(*args: float) -> float:
    """Multiply the first and last argument."""
    return args[0] * args[-1]


class Canvas:
    """A canvas with an overloaded method."""

    @overload
    def draw(self, shape: str) -> None: ...
    @overload
    def draw(self, shape: str, color: str) -> None: ...
    def draw(self, shape: str, color: str = "black") -> None:
        """Draw nothing."""
