"""Tests for sheridan.iceberg._discovery (DiscoveredModule and discover)."""

from pathlib import Path

import pytest

from sheridan.iceberg._config import Config
from sheridan.iceberg._discovery import DiscoveredModule, discover
from sheridan.iceberg._exceptions import InvalidPathError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, text: str = "") -> Path:
    """Write *text* to *path*, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _by_dotted(modules: tuple[DiscoveredModule, ...]) -> dict[str, DiscoveredModule]:
    """Index a discovery result by dotted_name for order-independent lookups."""
    return {m.dotted_name: m for m in modules}


def _default_config() -> Config:
    """Return a Config with all defaults."""
    return Config()


# ---------------------------------------------------------------------------
# Scenario 1 — Single .py file
# ---------------------------------------------------------------------------


def test_single_file_returns_one_module(tmp_path: Path) -> None:
    """A single .py file produces exactly one DiscoveredModule."""
    py_file = _write(tmp_path / "mymodule.py")
    config = _default_config()

    result = discover(py_file, config)

    assert len(result) == 1
    module = result[0]
    assert module.dotted_name == "mymodule"
    assert module.source_path == py_file
    assert module.is_init is False
    assert module.package_parts == ()


# ---------------------------------------------------------------------------
# Scenario 2 — Flat package
# ---------------------------------------------------------------------------


def test_flat_package_produces_correct_modules(tmp_path: Path) -> None:
    """Flat package: __init__.py + siblings yield correct dotted names and package_parts."""
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py")
    _write(pkg / "mod_a.py")
    _write(pkg / "mod_b.py")
    config = _default_config()

    result = discover(pkg, config)
    by_name = _by_dotted(result)

    assert set(by_name.keys()) == {"pkg", "pkg.mod_a", "pkg.mod_b"}

    # __init__.py: is_init=True, package_parts has no ancestors above pkg
    init_mod = by_name["pkg"]
    assert init_mod.is_init is True
    assert init_mod.package_parts == ()
    assert init_mod.source_path == pkg / "__init__.py"

    # sibling modules: is_init=False, package_parts = ("pkg",)
    for name in ("pkg.mod_a", "pkg.mod_b"):
        mod = by_name[name]
        assert mod.is_init is False
        assert mod.package_parts == ("pkg",)


# ---------------------------------------------------------------------------
# Scenario 3 — Nested package three levels deep
# ---------------------------------------------------------------------------


def test_nested_package_three_levels_deep(tmp_path: Path) -> None:
    """pkg/__init__.py, pkg/sub/__init__.py, pkg/sub/leaf.py all get correct metadata."""
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py")
    _write(pkg / "sub" / "__init__.py")
    _write(pkg / "sub" / "leaf.py")
    config = _default_config()

    result = discover(pkg, config)
    by_name = _by_dotted(result)

    assert set(by_name.keys()) == {"pkg", "pkg.sub", "pkg.sub.leaf"}

    # Top-level __init__.py
    pkg_mod = by_name["pkg"]
    assert pkg_mod.is_init is True
    assert pkg_mod.package_parts == ()
    assert pkg_mod.source_path == pkg / "__init__.py"

    # Sub-package __init__.py
    sub_mod = by_name["pkg.sub"]
    assert sub_mod.is_init is True
    assert sub_mod.package_parts == ("pkg",)
    assert sub_mod.source_path == pkg / "sub" / "__init__.py"

    # Leaf module inside sub-package
    leaf_mod = by_name["pkg.sub.leaf"]
    assert leaf_mod.is_init is False
    assert leaf_mod.package_parts == ("pkg", "sub")
    assert leaf_mod.source_path == pkg / "sub" / "leaf.py"


# ---------------------------------------------------------------------------
# Scenario 4 — src/ layout
# ---------------------------------------------------------------------------


def test_root_name_is_first_dotted_component(tmp_path: Path) -> None:
    """The root directory name is the first component of every dotted name.

    root.parent is the naming boundary, so only names at or below root appear.
    """
    src = tmp_path / "src"
    _write(src / "pkg" / "__init__.py")
    _write(src / "pkg" / "mod.py")
    config = _default_config()

    result = discover(src / "pkg", config)
    by_name = _by_dotted(result)

    assert set(by_name.keys()) == {"pkg", "pkg.mod"}

    pkg_mod = by_name["pkg"]
    assert pkg_mod.is_init is True
    assert pkg_mod.package_parts == ()

    mod = by_name["pkg.mod"]
    assert mod.is_init is False
    assert mod.package_parts == ("pkg",)


# ---------------------------------------------------------------------------
# Scenario 5 — tests/ subdirectory skipped
# ---------------------------------------------------------------------------


def test_tests_subdirectory_is_skipped(tmp_path: Path) -> None:
    """A tests/ subdirectory inside a package produces no DiscoveredModules."""
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py")
    _write(pkg / "core.py")
    # tests/ inside the package — should be entirely skipped by default pattern
    _write(pkg / "tests" / "test_core.py")
    _write(pkg / "tests" / "__init__.py")
    config = _default_config()

    result = discover(pkg, config)
    by_name = _by_dotted(result)

    # Nothing from tests/ should appear
    assert all("test" not in name for name in by_name)
    assert set(by_name.keys()) == {"pkg", "pkg.core"}


# ---------------------------------------------------------------------------
# Scenario 6 — test_*.py and *_test.py files skipped at any depth
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename",
    [
        "test_something.py",
        "something_test.py",
        "test_core.py",
        "integration_test.py",
    ],
)
def test_test_files_are_skipped_at_any_depth(tmp_path: Path, filename: str) -> None:
    """Files matching test_*.py or *_test.py are excluded regardless of depth."""
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py")
    _write(pkg / "real_module.py")
    # Place test file at top-level of package
    _write(pkg / filename)
    # Also place at a nested depth
    _write(pkg / "sub" / "__init__.py")
    _write(pkg / "sub" / filename)
    config = _default_config()

    result = discover(pkg, config)
    dotted_names = {m.dotted_name for m in result}

    # Verify no test-named module appears
    stem = Path(filename).stem
    assert f"pkg.{stem}" not in dotted_names
    assert f"pkg.sub.{stem}" not in dotted_names
    # Real modules do appear
    assert "pkg" in dotted_names
    assert "pkg.real_module" in dotted_names


# ---------------------------------------------------------------------------
# Scenario 7 — __pycache__ directory ignored
# ---------------------------------------------------------------------------


def test_pycache_directory_is_ignored(tmp_path: Path) -> None:
    """No .py files from __pycache__ appear in the discovery result."""
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py")
    _write(pkg / "real.py")
    # Place a .py file inside __pycache__ (unusual, but tests pruning logic)
    _write(pkg / "__pycache__" / "real.cpython-312.py")
    config = _default_config()

    result = discover(pkg, config)
    by_name = _by_dotted(result)

    assert set(by_name.keys()) == {"pkg", "pkg.real"}
    # Confirm no source_path points into __pycache__
    for mod in result:
        assert "__pycache__" not in mod.source_path.parts


# ---------------------------------------------------------------------------
# Scenario 8 — Non-existent root raises InvalidPathError
# ---------------------------------------------------------------------------


def test_nonexistent_root_raises_invalid_path_error(tmp_path: Path) -> None:
    """discover() raises InvalidPathError when the root path does not exist."""
    missing = tmp_path / "does_not_exist"
    config = _default_config()

    with pytest.raises(InvalidPathError):
        discover(missing, config)


def test_nonexistent_root_error_message_contains_path(tmp_path: Path) -> None:
    """The InvalidPathError message includes the missing path for diagnostics."""
    missing = tmp_path / "no_such_dir"
    config = _default_config()

    with pytest.raises(InvalidPathError, match=str(missing)):
        discover(missing, config)


# ---------------------------------------------------------------------------
# DiscoveredModule dataclass invariants
# ---------------------------------------------------------------------------


def test_discovered_module_is_frozen(tmp_path: Path) -> None:
    """DiscoveredModule instances are immutable (frozen dataclass)."""
    import dataclasses

    py_file = _write(tmp_path / "mod.py")
    config = _default_config()
    result = discover(py_file, config)
    module = result[0]

    assert dataclasses.is_dataclass(module)
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        module.dotted_name = "other"  # type: ignore[misc]


def test_discovered_module_has_slots() -> None:
    """DiscoveredModule uses __slots__ for memory efficiency."""
    assert hasattr(DiscoveredModule, "__slots__")


# ---------------------------------------------------------------------------
# Scenario 9 — Namespace package as root includes namespace in dotted names
# ---------------------------------------------------------------------------


def test_namespace_package_as_root_includes_namespace_in_dotted_name(
    tmp_path: Path,
) -> None:
    """A namespace-package root (no __init__.py) has its name included in all dotted names.

    The path is authoritative: root.parent is the naming boundary regardless of
    whether root contains an __init__.py.
    """
    acme = tmp_path / "acme"
    _write(acme / "widgets" / "__init__.py")
    _write(acme / "widgets" / "core.py", "def make_widget(name: str) -> str: ...")
    config = Config(max_workers=1)

    result = discover(acme, config)
    dotted_names = {m.dotted_name for m in result}

    # The namespace prefix must appear in every dotted name
    assert "acme.widgets" in dotted_names
    assert "acme.widgets.core" in dotted_names

    # Regression guard: no name may start with just "widgets" (without the namespace)
    assert not any(name == "widgets" or name.startswith("widgets.") for name in dotted_names)
