"""Tests for sheridan.iceberg._orchestrator (build_package) and
sheridan.iceberg._api (get_public_api).
"""

import subprocess
import sys
import warnings
from pathlib import Path

import pytest

from sheridan.iceberg._api import get_public_api
from sheridan.iceberg._config import Config
from sheridan.iceberg._models import Function, Module, Package
from sheridan.iceberg._orchestrator import build_package

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, text: str = "") -> Path:
    """Write *text* to *path*, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _default_config() -> Config:
    """Build a Config with all defaults and max_workers=1 for determinism."""
    return Config(max_workers=1)


def _all_module_names(pkg: Package) -> set[str]:
    """Recursively collect all Module.name values from a Package trie."""
    names: set[str] = {m.name for m in pkg.modules}
    for sub in pkg.subpackages:
        names |= _all_module_names(sub)
    return names


# ---------------------------------------------------------------------------
# Scenario 1 — Single .py file → one-module Package
# ---------------------------------------------------------------------------


def test_single_file_returns_module(tmp_path: Path) -> None:
    """A single .py file produces a bare Module (not a Package) with name == stem."""
    py_file = _write(
        tmp_path / "mymodule.py",
        "def greet() -> str:\n    return 'hello'\n",
    )
    config = _default_config()

    result = build_package(py_file, config)

    assert isinstance(result, Module)
    assert result.name == "mymodule"


def test_single_file_module_has_correct_name(tmp_path: Path) -> None:
    """A single .py file returns a Module whose name equals the file stem."""
    py_file = _write(tmp_path / "utils.py", "CONSTANT = 42\n")
    config = _default_config()

    result = build_package(py_file, config)

    assert isinstance(result, Module)
    assert result.name == "utils"


# ---------------------------------------------------------------------------
# Scenario 2 — Flat package → Package with modules, subpackages empty
# ---------------------------------------------------------------------------


def test_flat_package_modules_populated(tmp_path: Path) -> None:
    """Flat __init__.py + 2 siblings → Package.modules is non-empty."""
    pkg = tmp_path / "mypkg"
    _write(pkg / "__init__.py", "")
    _write(pkg / "alpha.py", "def alpha() -> int:\n    return 1\n")
    _write(pkg / "beta.py", "def beta() -> int:\n    return 2\n")
    config = _default_config()

    result = build_package(pkg, config)

    assert isinstance(result, Package)
    assert result.name == "mypkg"
    # The trie must have modules at the root level (init + siblings both placed here)
    all_names = _all_module_names(result)
    assert "mypkg.alpha" in all_names
    assert "mypkg.beta" in all_names


def test_flat_package_subpackages_empty(tmp_path: Path) -> None:
    """A flat package has no sub-packages."""
    pkg = tmp_path / "mypkg"
    _write(pkg / "__init__.py", "")
    _write(pkg / "mod_a.py", "X = 1\n")
    _write(pkg / "mod_b.py", "Y = 2\n")
    config = _default_config()

    result = build_package(pkg, config)

    assert result.subpackages == ()


# ---------------------------------------------------------------------------
# Scenario 3 — Three-level nested package → correct trie depth
# ---------------------------------------------------------------------------


def test_nested_package_three_levels_deep(tmp_path: Path) -> None:
    """root → root.sub → root.sub.leaf: trie depth is 3 (root.sub.sub present)."""
    pkg = tmp_path / "root"
    _write(pkg / "__init__.py", "")
    _write(pkg / "sub" / "__init__.py", "")
    _write(pkg / "sub" / "leaf.py", "LEAF = True\n")
    config = _default_config()

    result = build_package(pkg, config)

    # Root Package
    assert result.name == "root"
    # One sub-package at depth 1
    assert len(result.subpackages) == 1
    sub = result.subpackages[0]
    assert sub.name == "root.sub"
    # leaf module must appear in sub's modules
    sub_module_names = {m.name for m in sub.modules}
    assert "root.sub.leaf" in sub_module_names


def test_nested_trie_root_subpackage_name(tmp_path: Path) -> None:
    """The sub-Package inside the trie carries the fully-qualified name."""
    pkg = tmp_path / "mypkg"
    _write(pkg / "__init__.py", "")
    _write(pkg / "inner" / "__init__.py", "")
    _write(pkg / "inner" / "core.py", "def run() -> None: ...\n")
    config = _default_config()

    result = build_package(pkg, config)

    sub = result.subpackages[0]
    assert sub.name == "mypkg.inner"


# ---------------------------------------------------------------------------
# Scenario 4 — __init__.py re-exports a function from a sibling
# ---------------------------------------------------------------------------


def test_init_reexport_function_appears_in_init_module(tmp_path: Path) -> None:
    """When __init__.py does `from .sibling import fn`, the resolved Module
    for the init entry must contain fn in its functions tuple."""
    pkg = tmp_path / "mypkg"
    _write(
        pkg / "sibling.py",
        "def helper() -> str:\n    return 'hi'\n",
    )
    _write(
        pkg / "__init__.py",
        "__all__ = ['helper']\nfrom .sibling import helper\n",
    )
    config = _default_config()

    result = build_package(pkg, config)

    # Locate the init Module (named "mypkg")
    init_module: Module | None = None
    for mod in result.modules:
        if mod.name == "mypkg":
            init_module = mod
            break

    assert init_module is not None, "init module 'mypkg' not found in Package.modules"
    fn_names = {fn.name for fn in init_module.functions}
    assert "helper" in fn_names, f"expected 'helper' in functions; got {fn_names}"


def test_init_reexport_function_is_correct_type(tmp_path: Path) -> None:
    """The re-exported symbol must be a Function instance, not just a name."""
    pkg = tmp_path / "mypkg"
    _write(
        pkg / "util.py",
        "def compute(x: int) -> int:\n    return x * 2\n",
    )
    _write(
        pkg / "__init__.py",
        "from .util import compute\n",
    )
    config = _default_config()

    result = build_package(pkg, config)

    init_module = next((m for m in result.modules if m.name == "mypkg"), None)
    assert init_module is not None
    assert any(isinstance(fn, Function) and fn.name == "compute" for fn in init_module.functions)


# ---------------------------------------------------------------------------
# Scenario 5 — Explicit config= passed to get_public_api bypasses discovery
# ---------------------------------------------------------------------------


def test_explicit_config_bypasses_file_discovery(tmp_path: Path) -> None:
    """When config= is supplied to get_public_api, no .iceberg.toml is sought."""
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py", "")
    _write(pkg / "mod.py", "VALUE = 1\n")

    # Plant a broken .iceberg.toml that would fail if read
    (tmp_path / ".iceberg.toml").write_text(
        "unknown_key = true\n",
        encoding="utf-8",
    )

    explicit_config = Config(max_workers=1)

    # Should NOT raise ConfigError even though .iceberg.toml is invalid,
    # because config= is explicit and load_config is never called.
    result = get_public_api(pkg, config=explicit_config)

    assert isinstance(result, Package)
    assert result.name == "pkg"


def test_explicit_config_max_workers_respected(tmp_path: Path) -> None:
    """Config(max_workers=1) is accepted and the result is still a valid Package."""
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py", "")
    _write(pkg / "a.py", "def f() -> None: ...\n")
    _write(pkg / "b.py", "def g() -> None: ...\n")

    config = Config(max_workers=1)
    result = build_package(pkg, config)

    assert isinstance(result, Package)
    all_names = _all_module_names(result)
    assert "pkg.a" in all_names
    assert "pkg.b" in all_names


# ---------------------------------------------------------------------------
# Scenario 6 — ≥ 8 non-init modules all appear in the result
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_count", [8, 10])
def test_many_modules_all_appear_in_result(tmp_path: Path, module_count: int) -> None:
    """With ≥8 non-init .py modules, every module appears in the Package trie."""
    pkg = tmp_path / "bigpkg"
    _write(pkg / "__init__.py", "")

    expected_names: set[str] = set()
    for i in range(module_count):
        name = f"module_{i:02d}"
        _write(pkg / f"{name}.py", f"VALUE_{i} = {i}\n")
        expected_names.add(f"bigpkg.{name}")

    config = Config(max_workers=1)
    result = build_package(pkg, config)

    all_names = _all_module_names(result)
    missing = expected_names - all_names
    assert not missing, f"These modules were not found in the result: {sorted(missing)}"


def test_eight_modules_parallel_path(tmp_path: Path) -> None:
    """8-module package with max_workers > 1 exercises the process pool path."""
    pkg = tmp_path / "parallel_pkg"
    _write(pkg / "__init__.py", "")

    expected: set[str] = set()
    for i in range(8):
        mod_name = f"worker_{i}"
        _write(pkg / f"{mod_name}.py", f"N = {i}\n")
        expected.add(f"parallel_pkg.{mod_name}")

    config = Config(max_workers=2)
    result = build_package(pkg, config)

    all_names = _all_module_names(result)
    assert expected.issubset(all_names), f"Missing modules: {sorted(expected - all_names)}"


def test_default_config_safe_in_unguarded_script(tmp_path: Path) -> None:
    """A plain script with no ``if __name__ == "__main__":`` guard must work.

    Worker processes re-import ``__main__`` under the spawn / forkserver start
    methods, so a process pool here would crash with BrokenProcessPool.
    """
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py", "")
    _write(pkg / "mod.py", "def f() -> None: ...\n")
    script = _write(
        tmp_path / "script.py",
        "from pathlib import Path\n"
        "from sheridan.iceberg import get_public_api\n"
        f"print(get_public_api(Path({str(pkg)!r})).name)\n",
    )

    completed = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=60, check=False)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "pkg"


# ---------------------------------------------------------------------------
# Paths that are not Python identifiers
# ---------------------------------------------------------------------------


def test_hyphenated_directory_does_not_create_phantom_root(tmp_path: Path) -> None:
    """A hyphenated subdirectory does not add a second root or an empty root name."""
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py")
    _write(pkg / "core.py", "def f() -> None: ...\n")
    _write(pkg / "my-dir" / "thing.py", "def h() -> None: ...\n")
    _write(pkg / "my-script.py", "def g() -> None: ...\n")

    result = build_package(pkg, _default_config())

    assert isinstance(result, Package)
    assert result.name == "pkg"
    assert _all_module_names(result) == {"pkg", "pkg.core"}


def test_non_identifier_root_directory_has_non_empty_name(tmp_path: Path) -> None:
    """A root directory that is not an identifier still gives the root package a name."""
    root = tmp_path / "my-project"
    _write(root / "core.py", "def f() -> None: ...\n")

    result = build_package(root, _default_config())

    assert isinstance(result, Package)
    assert result.name == "my-project"


# ---------------------------------------------------------------------------
# __all__ built up from other modules
# ---------------------------------------------------------------------------


def _init_module(result: Package, name: str) -> Module:
    return next(mod for mod in result.modules if mod.name == name)


@pytest.mark.parametrize("max_workers", [1, 2])
def test_init_all_extended_with_submodule_all(tmp_path: Path, max_workers: int) -> None:
    """`__all__ += sub.__all__` uses the __all__ of a module in the analyzed tree."""
    pkg = tmp_path / "mypkg"
    _write(
        pkg / "core.py",
        "__all__ = ['run']\n__all__.append('stop')\ndef run(): ...\ndef stop(): ...\ndef hidden(): ...\n",
    )
    _write(
        pkg / "__init__.py",
        "from . import core\nfrom .core import run, stop\n"
        "__all__ = ['VERSION']\n__all__ += core.__all__\nVERSION = '1'\n",
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = build_package(pkg, Config(max_workers=max_workers))

    assert isinstance(result, Package)
    init = _init_module(result, "mypkg")
    assert {fn.name for fn in init.functions} == {"run", "stop"}
    assert {a.name for a in init.assignments} == {"VERSION"}


def test_unevaluable_all_warns_and_falls_back(tmp_path: Path) -> None:
    """A dynamic __all__ is reported once, then underscore inference is used."""
    pkg = tmp_path / "mypkg"
    _write(pkg / "__init__.py", "")
    _write(pkg / "core.py", "__all__ = ['run']\n__all__ += make()\ndef run(): ...\ndef other(): ...\n")

    with pytest.warns(UserWarning, match=r"core\.py:2: cannot evaluate __all__") as record:
        result = build_package(pkg, _default_config())

    assert len(record) == 1
    assert isinstance(result, Package)
    core = next(mod for mod in result.modules if mod.name == "mypkg.core")
    assert {fn.name for fn in core.functions} == {"run", "other"}
