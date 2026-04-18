"""End-to-end functional tests for get_public_api.

These tests build realistic package trees under tmp_path and verify that the
full discover → visit → resolve_init → assemble pipeline produces the expected
public API surface.  No mocking; config=Config(max_workers=1) is used to avoid
needing a config file on disk and to keep worker-process overhead minimal.
"""

from pathlib import Path

import pytest

from sheridan.iceberg._api import get_public_api
from sheridan.iceberg._config import Config
from sheridan.iceberg._exceptions import InvalidPathError
from sheridan.iceberg._models import Class, Function, Module, Package

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CFG = Config(max_workers=1)


def _function_names(module: Module) -> set[str]:
    return {f.name for f in module.functions}


def _class_names(module: Module) -> set[str]:
    return {c.name for c in module.classes}


def _all_modules(pkg: Package) -> list[Module]:
    """Flatten all modules from a Package trie into a list."""
    result: list[Module] = list(pkg.modules)
    for sub in pkg.subpackages:
        result.extend(_all_modules(sub))
    return result


def _all_function_names(pkg: Package) -> set[str]:
    return {f.name for mod in _all_modules(pkg) for f in mod.functions}


def _all_class_names(pkg: Package) -> set[str]:
    return {c.name for mod in _all_modules(pkg) for c in mod.classes}


def _find_module(pkg: Package, dotted_name: str) -> Module | None:
    """Return the first Module whose name matches dotted_name anywhere in the trie."""
    for mod in _all_modules(pkg):
        if mod.name == dotted_name:
            return mod
    return None


# ---------------------------------------------------------------------------
# Scenario: invalid path raises InvalidPathError
# ---------------------------------------------------------------------------


def test_nonexistent_path_raises_invalid_path_error(tmp_path: Path) -> None:
    nonexistent = tmp_path / "does_not_exist"
    with pytest.raises(InvalidPathError):
        get_public_api(nonexistent, config=_CFG)


# ---------------------------------------------------------------------------
# Scenario 1: Single-module package (one .py file as the root)
# ---------------------------------------------------------------------------


def test_single_file_returns_package_with_one_module(tmp_path: Path) -> None:
    """A single .py file produces a one-module Package with the file's stem as name."""
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

    pkg = get_public_api(src, config=_CFG)

    assert pkg.name == "utils"
    assert pkg.path == src
    assert len(pkg.modules) == 1
    assert pkg.subpackages == ()

    mod = pkg.modules[0]
    assert mod.name == "utils"
    assert "helper" in _function_names(mod)
    assert "_private" not in _function_names(mod)
    assert "Converter" in _class_names(mod)


# ---------------------------------------------------------------------------
# Scenario 2: Flat single-module package directory
# ---------------------------------------------------------------------------


def test_flat_package_single_module(tmp_path: Path) -> None:
    """A package with just __init__.py and one sibling module."""
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

    pkg = get_public_api(pkg_dir, config=_CFG)

    assert pkg.name == "mypkg"
    assert pkg.subpackages == ()

    # greet must be reachable somewhere in the trie
    assert "greet" in _all_function_names(pkg)
    assert "_internal" not in _all_function_names(pkg)


# ---------------------------------------------------------------------------
# Scenario 3: Multi-module package with __init__ re-exports
# ---------------------------------------------------------------------------


def test_multi_module_package_with_init_reexports(tmp_path: Path) -> None:
    """__init__.py re-exports from multiple siblings; all names must appear."""
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

    pkg = get_public_api(pkg_dir, config=_CFG)

    assert pkg.name == "shapes"
    all_classes = _all_class_names(pkg)
    all_funcs = _all_function_names(pkg)

    assert "Circle" in all_classes
    assert "Rectangle" in all_classes
    assert "area" in all_funcs


# ---------------------------------------------------------------------------
# Scenario 4: Class defined in submodule, re-exported via __init__
# ---------------------------------------------------------------------------


def test_class_in_submodule_reexported_via_init(tmp_path: Path) -> None:
    """A class defined in a submodule and re-exported in __init__ must be reachable."""
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

    pkg = get_public_api(pkg_dir, config=_CFG)

    # When __all__ is defined, private sub-modules are filtered; only the
    # resolved init module is exposed at the package level.
    assert len(pkg.modules) == 1
    init_mod = pkg.modules[0]
    assert init_mod.name == "transport"
    assert "HttpClient" in _class_names(init_mod)

    # http.py is not in __all__, so it is suppressed from the trie.
    assert _find_module(pkg, "transport.http") is None
    assert pkg.subpackages == ()


# ---------------------------------------------------------------------------
# Scenario 5: Nested subpackage — class defined three levels deep
# ---------------------------------------------------------------------------


def test_nested_subpackage_class_reachable(tmp_path: Path) -> None:
    """A class inside a nested subpackage is present in the trie."""
    root_dir = tmp_path / "mylib"
    sub_dir = root_dir / "storage"
    root_dir.mkdir()
    sub_dir.mkdir()

    # No __all__ on the root init: subpackages are included in the trie as-is.
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

    pkg = get_public_api(root_dir, config=_CFG)

    assert pkg.name == "mylib"

    # Without __all__ on the root init, the storage subpackage is included.
    assert len(pkg.subpackages) == 1
    storage_pkg = pkg.subpackages[0]
    assert storage_pkg.name == "mylib.storage"

    # Within mylib.storage, __all__ = ["Store"] is defined, so only the
    # resolved init module is exposed (backend.py is filtered out).
    assert storage_pkg.subpackages == ()
    assert len(storage_pkg.modules) == 1
    storage_init = storage_pkg.modules[0]
    assert storage_init.name == "mylib.storage"
    assert "Store" in _class_names(storage_init)


# ---------------------------------------------------------------------------
# Scenario 6: Package with __all__ on __init__ and locally-defined function
# ---------------------------------------------------------------------------


def test_locally_defined_function_in_init_reachable(tmp_path: Path) -> None:
    """A function defined directly in __init__.py appears in the init Module."""
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

    pkg = get_public_api(pkg_dir, config=_CFG)

    init_mod = _find_module(pkg, "utils")
    assert init_mod is not None
    assert "add" in _function_names(init_mod)
    assert "PI" in {a.name for a in init_mod.assignments}


# ---------------------------------------------------------------------------
# Scenario 7: Module with no public symbols produces empty collections
# ---------------------------------------------------------------------------


def test_module_with_only_private_names_has_empty_collections(tmp_path: Path) -> None:
    """A module exporting only private names produces empty functions/classes."""
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

    pkg = get_public_api(pkg_dir, config=_CFG)

    impl_mod = _find_module(pkg, "internals.impl")
    assert impl_mod is not None
    assert impl_mod.functions == ()
    assert impl_mod.classes == ()


# ---------------------------------------------------------------------------
# Scenario 8: Package returns correct Package.path
# ---------------------------------------------------------------------------


def test_package_path_matches_directory(tmp_path: Path) -> None:
    """Package.path must equal the directory passed to get_public_api."""
    pkg_dir = tmp_path / "mything"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")

    pkg = get_public_api(pkg_dir, config=_CFG)

    assert pkg.path == pkg_dir


# ---------------------------------------------------------------------------
# Scenario 9: Async function is captured correctly
# ---------------------------------------------------------------------------


def test_async_function_is_captured(tmp_path: Path) -> None:
    """An async function in a module is included and marked is_async=True."""
    src = tmp_path / "fetcher.py"
    src.write_text(
        """\
async def fetch(url: str) -> bytes:
    return b""
""",
        encoding="utf-8",
    )

    pkg = get_public_api(src, config=_CFG)

    mod = pkg.modules[0]
    func_map: dict[str, Function] = {f.name: f for f in mod.functions}
    assert "fetch" in func_map
    assert func_map["fetch"].is_async is True


# ---------------------------------------------------------------------------
# Scenario 10: Return-type annotation is preserved end-to-end
# ---------------------------------------------------------------------------


def test_function_return_annotation_preserved(tmp_path: Path) -> None:
    """Return annotations on functions survive the full pipeline."""
    src = tmp_path / "math_utils.py"
    src.write_text(
        """\
def square(n: int) -> int:
    return n * n
""",
        encoding="utf-8",
    )

    pkg = get_public_api(src, config=_CFG)

    mod = pkg.modules[0]
    func_map: dict[str, Function] = {f.name: f for f in mod.functions}
    assert func_map["square"].returns == "int"


# ---------------------------------------------------------------------------
# Scenario 11: Class methods are captured on re-exported class
# ---------------------------------------------------------------------------


def test_class_methods_present_after_reexport(tmp_path: Path) -> None:
    """Methods on a class re-exported via __init__ are preserved on the Class object."""
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

    pkg = get_public_api(pkg_dir, config=_CFG)

    init_mod = _find_module(pkg, "services")
    assert init_mod is not None
    class_map: dict[str, Class] = {c.name: c for c in init_mod.classes}
    assert "AuthService" in class_map
    method_names = {m.name for m in class_map["AuthService"].methods}
    assert "login" in method_names
    assert "logout" in method_names
