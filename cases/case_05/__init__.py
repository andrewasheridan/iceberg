"""Case 05 - re-exports Foo and bar_func from the private _impl module."""

from ._impl import Foo, bar_func

__all__ = ["Foo", "bar_func"]
