"""Functional tests for the public surface of sheridan.iceberg."""

import importlib
import types
from pathlib import Path

import pytest

from sheridan.iceberg._config import Config

_CFG = Config(max_workers=1)


def test_import_succeeds() -> None:
    """Importing sheridan.iceberg must not raise."""
    module = importlib.import_module("sheridan.iceberg")
    assert isinstance(module, types.ModuleType)


def test_all_equals_expected_names() -> None:
    """__all__ must contain exactly the documented public names."""
    import sheridan.iceberg as iceberg

    expected: set[str] = {
        "get_public_api",
        "Package",
        "Module",
        "Class",
        "Function",
        "Parameter",
        "Assignment",
        "IcebergError",
        "InvalidPathError",
        "ParseError",
        "ConfigError",
        "utilities",
    }
    assert set(iceberg.__all__) == expected


@pytest.mark.parametrize(
    "name",
    [
        "get_public_api",
        "Package",
        "Module",
        "Class",
        "Function",
        "Parameter",
        "Assignment",
        "IcebergError",
        "InvalidPathError",
        "ParseError",
        "ConfigError",
    ],
)
def test_all_names_are_accessible_as_attributes(name: str) -> None:
    """Every name in __all__ must be accessible as an attribute of the module."""
    import sheridan.iceberg as iceberg

    assert hasattr(iceberg, name), f"sheridan.iceberg has no attribute {name!r}"
    # getattr must not raise
    attr = getattr(iceberg, name)
    assert attr is not None


# ---------------------------------------------------------------------------
# Design-contract tests for naming boundary and return types
# ---------------------------------------------------------------------------


def test_single_file_returns_bare_module(tmp_path: Path) -> None:
    """A single .py file must return a bare Module, not a Package."""
    from sheridan.iceberg._models import Module
    from sheridan.iceberg._orchestrator import build_package

    src = tmp_path / "mymod.py"
    src.write_text("def greet() -> str:\n    return 'hello'\n", encoding="utf-8")

    result = build_package(src, _CFG)

    assert isinstance(result, Module), f"Expected Module, got {type(result).__name__}"


def test_single_file_module_name_is_stem(tmp_path: Path) -> None:
    """The Module returned for a single file carries the file's stem as its name."""
    from sheridan.iceberg._models import Module
    from sheridan.iceberg._orchestrator import build_package

    src = tmp_path / "utils.py"
    src.write_text("CONSTANT = 42\n", encoding="utf-8")

    result = build_package(src, _CFG)

    assert isinstance(result, Module)
    assert result.name == "utils"


def test_directory_returns_package(tmp_path: Path) -> None:
    """A directory root must return a Package."""
    from sheridan.iceberg._models import Package
    from sheridan.iceberg._orchestrator import build_package

    pkg_dir = tmp_path / "mypkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")

    result = build_package(pkg_dir, _CFG)

    assert isinstance(result, Package), f"Expected Package, got {type(result).__name__}"


def test_directory_package_name_equals_dir_stem(tmp_path: Path) -> None:
    """Package.name must equal the directory stem, not include any parent components."""
    from sheridan.iceberg._models import Package
    from sheridan.iceberg._orchestrator import build_package

    pkg_dir = tmp_path / "widgets"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")

    result = build_package(pkg_dir, _CFG)

    assert isinstance(result, Package)
    assert result.name == "widgets"


def test_naming_boundary_is_root_parent(tmp_path: Path) -> None:
    """root.parent is always the naming boundary.

    When the caller passes ``src/sheridan``, module names start with
    ``sheridan.*``, not ``src.sheridan.*``.
    """
    from sheridan.iceberg._models import Package
    from sheridan.iceberg._orchestrator import build_package

    # Build: src/sheridan/tools.py
    src = tmp_path / "src"
    sheridan_ns = src / "sheridan"
    sheridan_ns.mkdir(parents=True)
    (sheridan_ns / "tools.py").write_text("def helper() -> None:\n    pass\n", encoding="utf-8")

    # Pass src/sheridan as the root → name_root = src → names start with sheridan.*
    result = build_package(sheridan_ns, _CFG)

    assert isinstance(result, Package)
    assert result.name == "sheridan", f"Expected 'sheridan', got {result.name!r}"

    all_module_names = {m.name for m in result.modules}
    assert any(n.startswith("sheridan.") or n == "sheridan" for n in all_module_names)
    assert not any(n.startswith("src.") for n in all_module_names)


def test_package_name_is_root_dir_name(tmp_path: Path) -> None:
    """Package.name is the root directory name regardless of the parent directory.

    Passing ``src/mypkg`` yields a package named ``mypkg`` because root.parent
    is the naming boundary and the parent's name never appears in the result.
    """
    from sheridan.iceberg._models import Package
    from sheridan.iceberg._orchestrator import build_package

    src = tmp_path / "src"
    pkg = src / "mypkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "core.py").write_text("def run() -> None:\n    pass\n", encoding="utf-8")

    result = build_package(pkg, _CFG)

    assert isinstance(result, Package)
    assert result.name == "mypkg"
