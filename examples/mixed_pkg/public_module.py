"""Public module within mixed_pkg."""

__all__ = ["PublicThing", "public_fn"]


class PublicThing:
    """A public class in the public module."""

    pass


def public_fn() -> None:
    """A public function in the public module."""
    ...
