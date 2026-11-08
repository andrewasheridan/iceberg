"""Case 04 - foo."""
# foo, bar, baz, qux, quux, corge, grault, garply, waldo, fred, plugh, xyzzy, and thud.

from typing import Any, TypeAlias


def foo():
    """Case 04 - foo.bar.

    A function with no arguments or type hints.
    """


async def bar() -> None:
    """Case 04 - foo.bar.

    Async function with no arguments or type hints.
    """


def baz() -> None:
    """Case 04 - foo.baz.

    A function with no arguments, with a return type.
    """


def qux(snap, crackle: int, pop="popped", **kwargs) -> None:
    """Case 04 - foo.qux.

    A function with arguments (various styles), with a return type.
    """


def quux(*, snap: float, crackle: int, pop: str = "popped", **kwargs: Any) -> None:
    """Case 04 - foo.quux.

    A function with only kwargs (various styles), with a return type.
    - Kwargs will be sorted alphabetically in output.
    """


corge = "corge"
"""Case 04 - foo.corge.
A public assignment (no type hint)."""

type grault = int
"""Case 04 - foo.type.graut.

A public type-alias (new style).
"""

garply: TypeAlias = int | float  #  noqa: UP040
"""Case 04 - foo.type.garply.

A public type-alias (old style).
"""


class Waldo:
    """Case 04 - foo.waldo."""

    def __init__(self) -> None:
        """Case 04 - foo.waldo.init."""

    @staticmethod
    def foo() -> None:
        """Case 04 - foo.waldo.foo."""

    @classmethod
    def bar(cls):
        """Case 04 - foo.waldo.bar."""

    class Fred:
        """Case 04 - foo.Waldo.Fred."""

        async def foo(self) -> None:
            """Case 04 - foo.waldo.Fred.foo."""
