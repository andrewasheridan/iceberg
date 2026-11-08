"""Case 07 - foo."""


def make_point(x: float, y: float, /, label: str = "") -> str:
    """Case 07 - make_point.

    Demonstrates positional-only parameters (the ``/`` separator).
    ``x`` and ``y`` are positional-only; ``label`` is positional-or-keyword.
    """


def join_strings(*parts: str, separator: str = ", ") -> str:
    """Case 07 - join_strings.

    Demonstrates a var-positional ``*args`` parameter with a type annotation,
    plus a keyword-only parameter after it.
    """


def format_record(id: int, /, *fields: str, prefix: str = "", sep: str = "|") -> str:
    """Case 07 - format_record.

    Combines positional-only (``id``), var-positional (``*fields``),
    and keyword-only (``prefix``, ``sep``) parameters.
    """


def full_spectrum(a: int, b: int, /, c: int, *args: float, key: str = "x", **kwargs: bool) -> None:
    """Case 07 - full_spectrum.

    Exercises every parameter form in a single function:
    positional-only (``a``, ``b``), positional-or-keyword (``c``),
    var-positional (``*args``), keyword-only (``key``), and
    var-keyword (``**kwargs``).
    """
