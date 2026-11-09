"""An alias package fixture. It re-exports a class from a private module under a different name."""

from alias_pkg._beta import Beta as Delta

__all__ = ["Delta"]
