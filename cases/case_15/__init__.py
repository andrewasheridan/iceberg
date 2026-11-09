"""Case 15 - __all__ extended inside a try/except ImportError block."""

from ._core import slow

__all__ = ["slow"]

try:
    from ._speedups import fast  # noqa: F401  # exported by the append below, which ruff does not track

    __all__.append("fast")
except ImportError:
    pass
