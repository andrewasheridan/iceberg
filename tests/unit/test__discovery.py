"""Test sheridan.iceberg._discovery (DiscoveredModule and discover)."""

import re
from pathlib import Path

import pytest

from sheridan.iceberg._config import Config
from sheridan.iceberg._discovery import DiscoveredModule, _compute_dotted_name, discover
from sheridan.iceberg._exceptions import InvalidPathError


def _write(path: Path, text: str = "") -> Path:
    """Write *text* to *path*. Make the parent directories if necessary."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _by_dotted(modules: tuple[DiscoveredModule, ...]) -> dict[str, DiscoveredModule]:
    """Index a discovery result by dotted_name, so that the order has no effect on searches."""
    return {m.dotted_name: m for m in modules}


def _default_config() -> Config:
    """Build a Config with all the default values."""
    return Config()


def test_single_file_returns_one_module(tmp_path: Path) -> None:
    """One .py file gives exactly one DiscoveredModule."""
    py_file = _write(tmp_path / "mymodule.py")
    config = _default_config()

    result = discover(py_file, config)

    assert len(result) == 1
    module = result[0]

    assert module.dotted_name == "mymodule"
    assert module.source_path == py_file
    assert module.is_init is False
    assert module.package_parts == ()


def test_flat_package_produces_correct_modules(tmp_path: Path) -> None:
    """A flat package: __init__.py and its siblings give the correct dotted names and package_parts."""
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py")
    _write(pkg / "mod_a.py")
    _write(pkg / "mod_b.py")
    config = _default_config()

    result = discover(pkg, config)
    by_name = _by_dotted(result)

    assert set(by_name.keys()) == {"pkg", "pkg.mod_a", "pkg.mod_b"}

    # __init__.py: is_init=True, package_parts has no parent directories above pkg
    init_mod = by_name["pkg"]

    assert init_mod.is_init is True
    assert init_mod.package_parts == ()
    assert init_mod.source_path == pkg / "__init__.py"

    # sibling modules: is_init=False, package_parts = ("pkg",)
    for name in ("pkg.mod_a", "pkg.mod_b"):
        mod = by_name[name]
        assert mod.is_init is False
        assert mod.package_parts == ("pkg",)


def test_nested_package_three_levels_deep(tmp_path: Path) -> None:
    """pkg/__init__.py, pkg/sub/__init__.py and pkg/sub/leaf.py all get the correct metadata."""
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

    # Subpackage __init__.py
    sub_mod = by_name["pkg.sub"]

    assert sub_mod.is_init is True
    assert sub_mod.package_parts == ("pkg",)
    assert sub_mod.source_path == pkg / "sub" / "__init__.py"

    # Leaf module in the subpackage
    leaf_mod = by_name["pkg.sub.leaf"]

    assert leaf_mod.is_init is False
    assert leaf_mod.package_parts == ("pkg", "sub")
    assert leaf_mod.source_path == pkg / "sub" / "leaf.py"


def test_root_name_is_first_dotted_component(tmp_path: Path) -> None:
    """The name of the root directory is the first component of each dotted name.

    root.parent is the limit for names. Thus, the result has only names at root or below it.
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


def test_tests_subdirectory_is_skipped(tmp_path: Path) -> None:
    """A tests/ subdirectory in a package gives no DiscoveredModules."""
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py")
    _write(pkg / "core.py")
    # tests/ in the package. The default pattern must skip all of it.
    _write(pkg / "tests" / "test_core.py")
    _write(pkg / "tests" / "__init__.py")
    config = _default_config()

    result = discover(pkg, config)
    by_name = _by_dotted(result)

    # The result must not include items from tests/
    assert all("test" not in name for name in by_name)
    assert set(by_name.keys()) == {"pkg", "pkg.core"}


@pytest.mark.parametrize("ancestor", ["tests", "test"])
def test_test_directory_above_root_does_not_exclude_modules(tmp_path: Path, ancestor: str) -> None:
    """discover matches the pattern relative to the root. Thus, it ignores a tests/ directory above the root."""
    pkg = tmp_path / ancestor / "proj" / "pkg"
    _write(pkg / "__init__.py")
    _write(pkg / "mod.py", "def f(): pass\n")
    _write(pkg / "tests" / "test_mod.py")

    result = discover(pkg, _default_config())

    assert set(_by_dotted(result)) == {"pkg", "pkg.mod"}


def test_pattern_sees_root_name_in_relative_path(tmp_path: Path) -> None:
    """The relative path that discover compares with the pattern starts with the name of the root."""
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py")
    _write(pkg / "mod.py")
    _write(pkg / "sub" / "__init__.py")
    config = Config(test_module_pattern=re.compile(r"^pkg/sub/"))

    result = discover(pkg, config)

    assert set(_by_dotted(result)) == {"pkg", "pkg.mod"}


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
    """discover skips files that match test_*.py or *_test.py at all depths."""
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py")
    _write(pkg / "real_module.py")
    # Put a test file at the top level of the package
    _write(pkg / filename)
    # Also put one at a nested depth
    _write(pkg / "sub" / "__init__.py")
    _write(pkg / "sub" / filename)
    config = _default_config()

    result = discover(pkg, config)
    dotted_names = {m.dotted_name for m in result}

    # Make sure that the result has no module with a test name
    stem = Path(filename).stem
    assert f"pkg.{stem}" not in dotted_names
    assert f"pkg.sub.{stem}" not in dotted_names
    # The result includes the real modules
    assert "pkg" in dotted_names
    assert "pkg.real_module" in dotted_names


def test_pycache_directory_is_ignored(tmp_path: Path) -> None:
    """The discovery result has no .py files from __pycache__."""
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py")
    _write(pkg / "real.py")
    # Put a .py file in __pycache__. This is unusual, but it tests the logic that skips directories.
    _write(pkg / "__pycache__" / "real.cpython-312.py")
    config = _default_config()

    result = discover(pkg, config)
    by_name = _by_dotted(result)

    assert set(by_name.keys()) == {"pkg", "pkg.real"}
    # Make sure that no source_path points into __pycache__
    for mod in result:
        assert "__pycache__" not in mod.source_path.parts


def test_nonexistent_root_raises_invalid_path_error(tmp_path: Path) -> None:
    """discover() raises InvalidPathError if the root path does not exist."""
    missing = tmp_path / "does_not_exist"
    config = _default_config()

    with pytest.raises(InvalidPathError):
        discover(missing, config)


def test_nonexistent_root_error_message_contains_path(tmp_path: Path) -> None:
    """The InvalidPathError message includes the missing path, for diagnosis."""
    missing = tmp_path / "no_such_dir"
    config = _default_config()

    with pytest.raises(InvalidPathError, match=re.escape(str(missing))):
        discover(missing, config)


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
    """DiscoveredModule uses __slots__, so that it uses less memory."""
    assert hasattr(DiscoveredModule, "__slots__")


def test_namespace_package_as_root_includes_namespace_in_dotted_name(
    tmp_path: Path,
) -> None:
    """All dotted names include the name of a namespace-package root (no __init__.py).

    The path has authority. root.parent is the limit for names, also if root
    has no __init__.py.
    """
    acme = tmp_path / "acme"
    _write(acme / "widgets" / "__init__.py")
    _write(acme / "widgets" / "core.py", "def make_widget(name: str) -> str: ...")
    config = Config(max_workers=1)

    result = discover(acme, config)
    dotted_names = {m.dotted_name for m in result}

    # Each dotted name must include the namespace prefix
    assert "acme.widgets" in dotted_names
    assert "acme.widgets.core" in dotted_names

    # Regression check: no name can start with only "widgets" (without the namespace)
    assert not any(name == "widgets" or name.startswith("widgets.") for name in dotted_names)


@pytest.mark.parametrize("dirname", ["my-dir", "1abc", "class", "has space", ".git", ".hidden"])
def test_non_identifier_directory_is_pruned(tmp_path: Path, dirname: str) -> None:
    """discover skips a directory with a name that is not an identifier (or is a keyword), and its contents."""
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py")
    _write(pkg / "core.py")
    _write(pkg / dirname / "thing.py", "def h() -> None: ...")
    _write(pkg / dirname / "inner" / "deep.py")

    result = discover(pkg, _default_config())

    assert set(_by_dotted(result)) == {"pkg", "pkg.core"}


@pytest.mark.parametrize("filename", ["my-script.py", "1abc.py", "import.py", "a.b.py"])
def test_non_identifier_file_is_skipped(tmp_path: Path, filename: str) -> None:
    """discover skips a .py file with a stem that is not an identifier (or is a keyword)."""
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py")
    _write(pkg / "core.py")
    _write(pkg / filename)

    result = discover(pkg, _default_config())

    assert set(_by_dotted(result)) == {"pkg", "pkg.core"}


@pytest.mark.parametrize(
    "dirname",
    ["build", "dist", "venv", "env", "node_modules", "site-packages", "mypkg.egg-info"],
)
def test_common_non_source_directories_are_pruned(tmp_path: Path, dirname: str) -> None:
    """discover does not go into build output, virtual environments and egg-info directories."""
    root = tmp_path / "pkg"
    _write(root / "__init__.py")
    _write(root / dirname / "leaked.py")

    names = set(_by_dotted(discover(root, _default_config())))

    assert names == {"pkg"}


def test_exclude_prunes_matching_directory(tmp_path: Path) -> None:
    """discover does not go into a directory that matches an exclude glob."""
    root = tmp_path / "pkg"
    _write(root / "__init__.py")
    _write(root / "legacy" / "old.py")
    _write(root / "keep.py")

    names = set(_by_dotted(discover(root, Config(exclude=("legacy",)))))

    assert names == {"pkg", "pkg.keep"}


def test_exclude_is_relative_to_analyzed_root(tmp_path: Path) -> None:
    """A pattern without ``**`` only matches at the top of the analyzed directory."""
    root = tmp_path / "pkg"
    _write(root / "__init__.py")
    _write(root / "legacy.py")
    _write(root / "sub" / "legacy.py")

    names = set(_by_dotted(discover(root, Config(exclude=("legacy.py",)))))

    assert names == {"pkg", "pkg.sub.legacy"}


def test_exclude_double_star_matches_at_any_depth(tmp_path: Path) -> None:
    """``**/name`` matches at the top level and in nested directories."""
    root = tmp_path / "pkg"
    _write(root / "__init__.py")
    _write(root / "generated" / "a.py")
    _write(root / "sub" / "generated" / "b.py")
    _write(root / "sub" / "c.py")

    names = set(_by_dotted(discover(root, Config(exclude=("**/generated",)))))

    assert names == {"pkg", "pkg.sub.c"}


def test_exclude_matches_files_with_wildcards(tmp_path: Path) -> None:
    """File globs such as ``**/*_pb2.py`` skip the modules that match."""
    root = tmp_path / "pkg"
    _write(root / "__init__.py")
    _write(root / "msg_pb2.py")
    _write(root / "sub" / "other_pb2.py")
    _write(root / "sub" / "real.py")

    names = set(_by_dotted(discover(root, Config(exclude=("**/*_pb2.py",)))))

    assert names == {"pkg", "pkg.sub.real"}


@pytest.mark.parametrize(
    ("py_file", "expected"),
    [
        (Path("/x/pkg/sub/mod.py"), ("pkg.sub.mod", ("pkg", "sub"))),
        (Path("/x/pkg/sub/__init__.py"), ("pkg.sub", ("pkg",))),
        (Path("/x/my-pkg/mod.py"), ("mod", ())),
        (Path("/x/my-pkg/__init__.py"), ("my-pkg", ())),
    ],
)
def test_compute_dotted_name(py_file: Path, expected: tuple[str, tuple[str, ...]]) -> None:
    assert _compute_dotted_name(py_file, Path("/x")) == expected
