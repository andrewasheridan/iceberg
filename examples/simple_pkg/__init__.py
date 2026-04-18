"""Simple flat package fixture for functional tests."""

from simple_pkg._models import MyClass
from simple_pkg._utils import my_func

__all__ = ["MyClass", "my_func"]
