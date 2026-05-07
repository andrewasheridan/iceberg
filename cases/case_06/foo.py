"""Case 06 - foo."""


class Widget:
    """Case 06 - Widget.

    Demonstrates class-level assignments and the visibility of private members
    inside a class body.
    """

    MAX_SIZE: int = 100
    """Maximum permitted size."""

    DEFAULT_NAME = "widget"
    """Default widget name (no type annotation)."""

    count: int = 0
    """Number of Widget instances created."""

    _registry: list = []  # noqa: RUF012
    """Private registry (underscore-prefixed class variable)."""

    def __init__(self, name: str = "widget", size: int = 10) -> None:
        """Case 06 - Widget.__init__."""

    def resize(self, new_size: int) -> None:
        """Case 06 - Widget.resize."""

    def describe(self) -> str:
        """Case 06 - Widget.describe."""

    def _validate(self, size: int) -> bool:
        """Case 06 - Widget._validate (private method)."""


def create_widget(name: str, size: int = 10) -> Widget:
    """Case 06 - create_widget."""
