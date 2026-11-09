"""Test get_public_api from end to end.

These tests build realistic package trees in tmp_path. They make sure that the
full pipeline (discover → visit → resolve_init → assemble) gives the expected
public API. The tests do not use mocks. They use config=Config(max_workers=1).
Thus, they do not need a configuration file on disk, and the overhead of
worker processes is minimal.
"""

from pathlib import Path

import pytest

from sheridan.iceberg._api import get_public_api
from sheridan.iceberg._config import Config
from sheridan.iceberg._exceptions import InvalidPathError
from sheridan.iceberg._models import Class, Function, Module, Package

_CFG = Config(max_workers=1)


def _snapshot_package(path: Path) -> Package:
    """Snapshot a package directory, and narrow the ``Package | Module`` result."""
    result = get_public_api(path, config=_CFG)

    assert isinstance(result, Package)
    return result


def _function_names(module: Module) -> set[str]:
    return {f.name for f in module.functions}


def _class_names(module: Module) -> set[str]:
    return {c.name for c in module.classes}


def _all_modules(pkg: Package) -> list[Module]:
    """Put all the modules of a Package trie into a flat list."""
    result: list[Module] = list(pkg.modules)
    for sub in pkg.subpackages:
        result.extend(_all_modules(sub))

    return result


def _all_function_names(pkg: Package) -> set[str]:
    return {f.name for mod in _all_modules(pkg) for f in mod.functions}


def _all_class_names(pkg: Package) -> set[str]:
    return {c.name for mod in _all_modules(pkg) for c in mod.classes}


def _find_module(pkg: Package, dotted_name: str) -> Module | None:
    """Find the first Module in the trie with a name that matches dotted_name."""
    for mod in _all_modules(pkg):
        if mod.name == dotted_name:
            return mod

    return None


def test_nonexistent_path_raises_invalid_path_error(tmp_path: Path) -> None:
    nonexistent = tmp_path / "does_not_exist"
    with pytest.raises(InvalidPathError):
        get_public_api(nonexistent, config=_CFG)


def test_single_file_returns_module(tmp_path: Path) -> None:
    """One .py file gives a Module. The name of the Module is the stem of the file."""
    src = tmp_path / "utils.py"
    src.write_text(
        """\
def helper(x: int) -> int:
    return x + 1


def _private() -> None:
    pass


class Converter:
    def convert(self) -> str:
        return ""
""",
        encoding="utf-8",
    )

    result = get_public_api(src, config=_CFG)

    assert isinstance(result, Module)
    assert result.name == "utils"
    assert "helper" in _function_names(result)
    assert "_private" not in _function_names(result)
    assert "Converter" in _class_names(result)


def test_flat_package_single_module(tmp_path: Path) -> None:
    """A package with only __init__.py and one sibling module."""
    pkg_dir = tmp_path / "mypkg"
    pkg_dir.mkdir()

    (pkg_dir / "__init__.py").write_text(
        """\
from .core import greet

__all__ = ["greet"]
""",
        encoding="utf-8",
    )
    (pkg_dir / "core.py").write_text(
        """\
def greet(name: str) -> str:
    return f"Hello, {name}"


def _internal() -> None:
    pass
""",
        encoding="utf-8",
    )

    pkg = _snapshot_package(pkg_dir)

    assert pkg.name == "mypkg"
    assert pkg.subpackages == ()

    # The trie must have greet at some level
    assert "greet" in _all_function_names(pkg)
    assert "_internal" not in _all_function_names(pkg)


def test_multi_module_package_with_init_reexports(tmp_path: Path) -> None:
    """__init__.py re-exports names from many siblings. The result must include all the names."""
    pkg_dir = tmp_path / "shapes"
    pkg_dir.mkdir()

    (pkg_dir / "__init__.py").write_text(
        """\
from .circle import Circle
from .rectangle import Rectangle, area

__all__ = ["Circle", "Rectangle", "area"]
""",
        encoding="utf-8",
    )
    (pkg_dir / "circle.py").write_text(
        """\
class Circle:
    def __init__(self, radius: float) -> None:
        self.radius = radius
""",
        encoding="utf-8",
    )
    (pkg_dir / "rectangle.py").write_text(
        """\
class Rectangle:
    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height


def area(width: float, height: float) -> float:
    return width * height
""",
        encoding="utf-8",
    )

    pkg = _snapshot_package(pkg_dir)

    assert pkg.name == "shapes"
    all_classes = _all_class_names(pkg)
    all_funcs = _all_function_names(pkg)

    assert "Circle" in all_classes
    assert "Rectangle" in all_classes
    assert "area" in all_funcs


def test_class_in_submodule_reexported_via_init(tmp_path: Path) -> None:
    """The result must include a class that a submodule defines and __init__ re-exports."""
    pkg_dir = tmp_path / "transport"
    pkg_dir.mkdir()

    (pkg_dir / "__init__.py").write_text(
        """\
from .http import HttpClient

__all__ = ["HttpClient"]
""",
        encoding="utf-8",
    )
    (pkg_dir / "http.py").write_text(
        """\
class HttpClient:
    def get(self, url: str) -> bytes:
        return b""

    def post(self, url: str, body: bytes) -> bytes:
        return b""
""",
        encoding="utf-8",
    )

    pkg = _snapshot_package(pkg_dir)

    # If the package defines __all__, iceberg removes the private submodules. Only the
    # resolved init module is at the package level.
    assert len(pkg.modules) == 1
    init_mod = pkg.modules[0]

    assert init_mod.name == "transport"
    assert "HttpClient" in _class_names(init_mod)

    # __all__ does not include http.py. Thus, the trie does not include it.
    assert _find_module(pkg, "transport.http") is None
    assert pkg.subpackages == ()


def test_nested_subpackage_class_reachable(tmp_path: Path) -> None:
    """The trie includes a class in a nested subpackage."""
    root_dir = tmp_path / "mylib"
    sub_dir = root_dir / "storage"
    root_dir.mkdir()
    sub_dir.mkdir()

    # The root init has no __all__. Thus, the trie includes the subpackages without a change.
    (root_dir / "__init__.py").write_text("", encoding="utf-8")
    (sub_dir / "__init__.py").write_text(
        """\
from .backend import Store

__all__ = ["Store"]
""",
        encoding="utf-8",
    )
    (sub_dir / "backend.py").write_text(
        """\
class Store:
    def save(self, key: str, value: object) -> None:
        pass

    def load(self, key: str) -> object:
        return None
""",
        encoding="utf-8",
    )

    pkg = _snapshot_package(root_dir)

    assert pkg.name == "mylib"

    # The root init has no __all__. Thus, the trie includes the storage subpackage.
    assert len(pkg.subpackages) == 1
    storage_pkg = pkg.subpackages[0]
    assert storage_pkg.name == "mylib.storage"

    # mylib.storage defines __all__ = ["Store"]. Thus, the result shows only the
    # resolved init module (iceberg removes backend.py).
    assert storage_pkg.subpackages == ()
    assert len(storage_pkg.modules) == 1
    storage_init = storage_pkg.modules[0]

    assert storage_init.name == "mylib.storage"
    assert "Store" in _class_names(storage_init)


def test_locally_defined_function_in_init_reachable(tmp_path: Path) -> None:
    """The init Module includes a function that __init__.py defines directly."""
    pkg_dir = tmp_path / "utils"
    pkg_dir.mkdir()

    (pkg_dir / "__init__.py").write_text(
        """\
__all__ = ["add", "PI"]

PI: float = 3.14159


def add(a: int, b: int) -> int:
    return a + b
""",
        encoding="utf-8",
    )

    pkg = _snapshot_package(pkg_dir)

    init_mod = _find_module(pkg, "utils")

    assert init_mod is not None
    assert "add" in _function_names(init_mod)
    assert "PI" in {a.name for a in init_mod.assignments}


def test_module_with_only_private_names_has_empty_collections(tmp_path: Path) -> None:
    """A module that exports only private names gives empty functions and classes."""
    pkg_dir = tmp_path / "internals"
    pkg_dir.mkdir()

    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    (pkg_dir / "impl.py").write_text(
        """\
def _do_thing() -> None:
    pass


class _InternalHelper:
    pass
""",
        encoding="utf-8",
    )

    pkg = _snapshot_package(pkg_dir)

    impl_mod = _find_module(pkg, "internals.impl")

    assert impl_mod is not None
    assert impl_mod.functions == ()
    assert impl_mod.classes == ()


def test_package_path_matches_directory(tmp_path: Path) -> None:
    """Package.path must be the same as the directory that get_public_api got."""
    pkg_dir = tmp_path / "mything"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")

    pkg = _snapshot_package(pkg_dir)

    assert pkg.path == pkg_dir


def test_async_function_is_captured(tmp_path: Path) -> None:
    """The result includes an async function in a module, with is_async=True."""
    src = tmp_path / "fetcher.py"
    src.write_text(
        """\
async def fetch(url: str) -> bytes:
    return b""
""",
        encoding="utf-8",
    )

    result = get_public_api(src, config=_CFG)

    assert isinstance(result, Module)
    func_map: dict[str, Function] = {f.name: f for f in result.functions}

    assert "fetch" in func_map
    assert func_map["fetch"].is_async is True


def test_function_return_annotation_preserved(tmp_path: Path) -> None:
    """Return-type annotations of functions stay the same through the full pipeline."""
    src = tmp_path / "math_utils.py"
    src.write_text(
        """\
def square(n: int) -> int:
    return n * n
""",
        encoding="utf-8",
    )

    result = get_public_api(src, config=_CFG)

    assert isinstance(result, Module)
    func_map: dict[str, Function] = {f.name: f for f in result.functions}
    assert func_map["square"].returns == "int"


def test_class_methods_present_after_reexport(tmp_path: Path) -> None:
    """If __init__ re-exports a class, the Class object keeps its methods."""
    pkg_dir = tmp_path / "services"
    pkg_dir.mkdir()

    (pkg_dir / "__init__.py").write_text(
        """\
from .auth import AuthService

__all__ = ["AuthService"]
""",
        encoding="utf-8",
    )
    (pkg_dir / "auth.py").write_text(
        """\
class AuthService:
    def login(self, username: str, password: str) -> bool:
        return True

    def logout(self) -> None:
        pass
""",
        encoding="utf-8",
    )

    pkg = _snapshot_package(pkg_dir)

    init_mod = _find_module(pkg, "services")

    assert init_mod is not None
    class_map: dict[str, Class] = {c.name: c for c in init_mod.classes}

    assert "AuthService" in class_map
    method_names = {m.name for m in class_map["AuthService"].methods}

    assert "login" in method_names
    assert "logout" in method_names
