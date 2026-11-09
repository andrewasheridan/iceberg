"""Tests for sheridan.iceberg._utilities."""

import ast
import os
import sys
import warnings
from pathlib import Path

import pytest

from sheridan.iceberg._exceptions import SourceReadError
from sheridan.iceberg._utilities import (
    bound_names,
    collect_imports,
    extract_all,
    infer_all,
    read_source,
    resolve_relative,
    star_candidate,
)


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


def test_star_import_binds_known_exports() -> None:
    tree = ast.parse("from ._c import *\nfrom os import *")
    exports = {"pkg._c": frozenset({"b", "a"})}
    assert collect_imports(tree, "pkg", exports.get) == {"a": ("pkg._c", "a"), "b": ("pkg._c", "b")}


def test_star_import_explicit_import_first_wins() -> None:
    tree = ast.parse("from ._d import a\nfrom ._c import *")
    exports = {"pkg._c": frozenset({"a"})}
    assert collect_imports(tree, "pkg", exports.get) == {"a": ("pkg._d", "a")}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import os", None),
        ("from ._c import *", None),
        ("from os import *", "os"),
        ("from os import *\nfrom sys import *\nfrom ._c import *", "sys"),
        ("try:\n    from .._x import *\nexcept ImportError:\n    pass", "_x"),
    ],
)
def test_star_candidate_is_last_unknown_star_module(source: str, expected: str | None) -> None:
    exports = {"pkg._c": frozenset({"a"})}
    assert star_candidate(ast.parse(source), "pkg", exports.get) == expected


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


# ---------------------------------------------------------------------------
# bound_names / infer_all
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a = 1", ["a"]),
        ("a, b = 1, 2", ["a", "b"]),
        ("[a, b] = 1, 2", ["a", "b"]),
        ("c, *rest = 1, 2, 3", ["c", "rest"]),
        ("(a, (b, *c)) = 1, (2, 3)", ["a", "b", "c"]),
        ("a, obj.attr, d[0] = 1, 2, 3", ["a"]),
        ("obj.attr = 1", []),
    ],
)
def test_bound_names(source: str, expected: list[str]) -> None:
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.Assign)
    assert list(bound_names(node.targets[0])) == expected


def test_infer_all_includes_chained_and_unpacked_names() -> None:
    tree = ast.parse("a = b = 1\nc, *rest = 1, 2\nd, _e = 1, 2\n")
    assert infer_all(tree) == frozenset({"a", "b", "c", "rest", "d"})


def test_infer_all_descends_into_if_and_try_blocks() -> None:
    source = """
if TYPE_CHECKING:
    class A: ...
elif x:
    b: int = 1
else:
    type C = int
try:
    def d(): ...
except ImportError:
    e = f = 1
else:
    async def g(): ...
finally:
    _h = 1
"""
    assert infer_all(ast.parse(source)) == frozenset({"A", "b", "C", "d", "e", "f", "g"})


# ---------------------------------------------------------------------------
# extract_all
# ---------------------------------------------------------------------------


def _extract(
    source: str,
    package: str = "pkg",
    known: dict[str, frozenset[str] | None] | None = None,
) -> frozenset[str] | None:
    lookup = None if known is None else known.get
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        return extract_all(ast.parse(source), package, lookup)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("__all__ = ['a', 'b']", {"a", "b"}),
        ("__all__: list[str] = ('a',)", {"a"}),
        ("__all__ = ['a']\n__all__ += ['b']", {"a", "b"}),
        ("__all__ = ['a']\n__all__ += ('b', 'c')", {"a", "b", "c"}),
        ("__all__ = ['a']\n__all__.extend(['b'])", {"a", "b"}),
        ("__all__ = ['a']\n__all__.append('b')", {"a", "b"}),
        ("__all__ = ['a'] + ['b'] + ('c',)", {"a", "b", "c"}),
        ("__all__ = ['a']\n__all__ = __all__ + ['b']", {"a", "b"}),
        ("__all__ = ['a']\n__all__ = ['b']", {"b"}),
        ("x = 1", None),
    ],
)
def test_extract_all_applies_literal_statements_in_order(source: str, expected: set[str] | None) -> None:
    result = _extract(source)
    assert result == (None if expected is None else frozenset(expected))


@pytest.mark.parametrize(
    "source",
    [
        "from . import sub\n__all__ = ['a']\n__all__ += sub.__all__",
        "from .sub import __all__ as _sub_all\n__all__ = ['a'] + _sub_all",
        "import pkg.sub as sub\n__all__ = ['a']\n__all__.extend(sub.__all__)",
    ],
)
def test_extract_all_resolves_other_module_all(source: str) -> None:
    assert _extract(source, known={"pkg.sub": frozenset({"x", "y"})}) == {"a", "x", "y"}


@pytest.mark.parametrize(
    "source",
    [
        "__all__ = make()",
        "__all__ = ['a']\n__all__ += make()",
        "__all__ += ['a']",
        "__all__ = ['a']\n__all__.append(name)",
        "__all__ = ['a']\n__all__.remove('a')",
        "from . import sub\n__all__ = ['a']\n__all__ += sub.__all__",
        "import os\n__all__ = ['a'] + os.__all__",
    ],
)
def test_extract_all_warns_when_not_static(source: str) -> None:
    with pytest.warns(UserWarning, match=r"cannot evaluate __all__"):
        assert extract_all(ast.parse(source), "pkg") is None


def test_extract_all_warning_names_path_and_line() -> None:
    tree = ast.parse("__all__ = ['a']\n__all__ += make()")
    with pytest.warns(UserWarning, match=r"^pkg/mod\.py:2: cannot evaluate __all__"):
        extract_all(tree, "pkg", path="pkg/mod.py")


# ---------------------------------------------------------------------------
# read_source
# ---------------------------------------------------------------------------


def test_read_source_reads_utf8(tmp_path: Path) -> None:
    path = tmp_path / "mod.py"
    path.write_bytes('NAME = "café"\n'.encode())
    assert read_source(path) == 'NAME = "café"\n'


def test_read_source_uses_pep263_declaration(tmp_path: Path) -> None:
    path = tmp_path / "mod.py"
    path.write_bytes('# -*- coding: latin-1 -*-\nNAME = "café"\n'.encode("latin-1"))
    assert read_source(path) == '# -*- coding: latin-1 -*-\nNAME = "café"\n'


def test_read_source_bytes_not_valid_for_encoding(tmp_path: Path) -> None:
    path = tmp_path / "mod.py"
    path.write_bytes('NAME = "café"\n'.encode("latin-1"))
    with pytest.raises(SourceReadError, match="cannot decode file") as info:
        read_source(path)
    assert info.value.path == str(path)
    assert str(info.value).startswith(f"{path}: ")


def test_read_source_unknown_encoding(tmp_path: Path) -> None:
    path = tmp_path / "mod.py"
    path.write_bytes(b"# -*- coding: bogus -*-\nx = 1\n")
    with pytest.raises(SourceReadError, match="unknown encoding: bogus"):
        read_source(path)


def test_read_source_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.py"
    with pytest.raises(SourceReadError, match="cannot read file") as info:
        read_source(path)
    assert info.value.path == str(path)


def test_read_source_broken_symlink(tmp_path: Path) -> None:
    path = tmp_path / "link.py"
    path.symlink_to(tmp_path / "missing.py")
    with pytest.raises(SourceReadError, match="cannot read file"):
        read_source(path)


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="needs POSIX permissions as non-root")
def test_read_source_unreadable_file(tmp_path: Path) -> None:
    path = tmp_path / "mod.py"
    path.write_text("x = 1\n")
    path.chmod(0)
    try:
        with pytest.raises(SourceReadError, match="cannot read file") as info:
            read_source(path)
    finally:
        path.chmod(0o644)
    assert info.value.path == str(path)
