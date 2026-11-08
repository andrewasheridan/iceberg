"""Tests for sheridan.iceberg._utilities (collect_imports and resolve_relative)."""

import ast

import pytest

from sheridan.iceberg._utilities import collect_imports, resolve_relative


def _imports(source: str, package: str = "pkg") -> dict[str, tuple[str, str | None]]:
    return collect_imports(ast.parse(source), package)


# ---------------------------------------------------------------------------
# resolve_relative
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("package", "module", "level", "expected"),
    [
        ("pkg", None, 1, "pkg"),
        ("pkg", "core", 1, "pkg.core"),
        ("pkg.sub", "core", 2, "pkg.core"),
        ("pkg.sub.deep", None, 3, "pkg"),
        ("", "core", 1, "core"),
    ],
)
def test_resolve_relative(package: str, module: str | None, level: int, expected: str) -> None:
    assert resolve_relative(package, module, level) == expected


# ---------------------------------------------------------------------------
# collect_imports
# ---------------------------------------------------------------------------


def test_from_import_absolute() -> None:
    assert _imports("from math import sqrt") == {"sqrt": ("math", "sqrt")}


def test_from_import_aliased() -> None:
    assert _imports("from collections import OrderedDict as Ordered") == {"Ordered": ("collections", "OrderedDict")}


def test_from_import_relative_is_absolutized() -> None:
    assert _imports("from ._core import area", package="pkg.sub") == {"area": ("pkg.sub._core", "area")}


def test_plain_import() -> None:
    assert _imports("import json") == {"json": ("json", None)}


def test_plain_import_dotted_binds_top_level() -> None:
    assert _imports("import os.path") == {"os": ("os", None)}


def test_plain_import_aliased() -> None:
    assert _imports("import numpy.linalg as la") == {"la": ("numpy.linalg", None)}


def test_star_import_ignored() -> None:
    assert _imports("from os import *") == {}


def test_try_except_imports_collected_first_binding_wins() -> None:
    source = """
try:
    from ._fast import parse
except ImportError:
    from ._slow import parse
finally:
    from ._final import done
"""
    assert _imports(source) == {"parse": ("pkg._fast", "parse"), "done": ("pkg._final", "done")}


def test_try_else_and_try_star_collected() -> None:
    source = """
try:
    pass
except ImportError:
    pass
else:
    from .a import x
try:
    pass
except* ValueError:
    from .b import y
"""
    assert _imports(source) == {"x": ("pkg.a", "x"), "y": ("pkg.b", "y")}


def test_if_branches_collected() -> None:
    source = """
import sys
if sys.version_info >= (3, 15):
    from .new import thing
else:
    from .old import other
"""
    result = _imports(source)
    assert result["thing"] == ("pkg.new", "thing")
    assert result["other"] == ("pkg.old", "other")


def test_function_and_class_bodies_ignored() -> None:
    source = """
def f():
    from math import sqrt

class C:
    import json
"""
    assert _imports(source) == {}
