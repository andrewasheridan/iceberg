"""Mixed package fixture with public and private modules."""

from mixed_pkg.public_module import PublicThing

__all__ = ["PublicThing", "public_module"]
