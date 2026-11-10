"""Test sheridan.iceberg._orchestrator (build_package) and
sheridan.iceberg._api (get_public_api).
"""

import ast
import os
import re
import subprocess
import sys
import warnings
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from sheridan.iceberg._api import get_public_api
from sheridan.iceberg._config import Config
from sheridan.iceberg._discovery import discover
from sheridan.iceberg._exceptions import IcebergError, ParseError, SourceReadError
from sheridan.iceberg._models import Diagnostic, Function, Module, Package, Reference
from sheridan.iceberg._orchestrator import (
    _child_names_by_package,
    _error_diagnostic,
    _evaluate_all,
    build_package,
    unresolved_name_warnings,
)


def _write(path: Path, text: str = "") -> Path:
    """Write *text* to *path*. Make the parent directories if necessary."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _default_config() -> Config:
    """Build a Config with all the default values and max_workers=1, so that the result is deterministic."""
    return Config(max_workers=1)


def _build_dir(path: Path, config: Config) -> Package:
    """Build a package directory, and narrow the ``Package | Module`` result."""
    result = build_package(path, config)

    assert isinstance(result, Package)
    return result


def _all_module_names(pkg: Package) -> set[str]:
    """Collect all the Module.name values of a Package trie recursively."""
    names: set[str] = {m.name for m in pkg.modules}
    for sub in pkg.subpackages:
        names |= _all_module_names(sub)

    return names


def test_single_file_returns_module(tmp_path: Path) -> None:
    """One .py file gives a bare Module (not a Package) with name == stem."""
    py_file = _write(
        tmp_path / "mymodule.py",
        "def greet() -> str:\n    return 'hello'\n",
    )
    config = _default_config()

    result = build_package(py_file, config)

    assert isinstance(result, Module)
    assert result.name == "mymodule"


def test_single_file_module_has_correct_name(tmp_path: Path) -> None:
    """One .py file gives a Module with a name that is the same as the file stem."""
    py_file = _write(tmp_path / "utils.py", "CONSTANT = 42\n")
    config = _default_config()

    result = build_package(py_file, config)

    assert isinstance(result, Module)
    assert result.name == "utils"


def test_flat_package_modules_populated(tmp_path: Path) -> None:
    """A flat __init__.py and 2 siblings → Package.modules is not empty."""
    pkg = tmp_path / "mypkg"
    _write(pkg / "__init__.py", "")
    _write(pkg / "alpha.py", "def alpha() -> int:\n    return 1\n")
    _write(pkg / "beta.py", "def beta() -> int:\n    return 2\n")
    config = _default_config()

    result = build_package(pkg, config)

    assert isinstance(result, Package)
    assert result.name == "mypkg"
    # The trie must have modules at the root level (the init and the siblings are there)
    all_names = _all_module_names(result)
    assert "mypkg.alpha" in all_names
    assert "mypkg.beta" in all_names


def test_flat_package_subpackages_empty(tmp_path: Path) -> None:
    """A flat package has no subpackages."""
    pkg = tmp_path / "mypkg"
    _write(pkg / "__init__.py", "")
    _write(pkg / "mod_a.py", "X = 1\n")
    _write(pkg / "mod_b.py", "Y = 2\n")
    config = _default_config()

    result = _build_dir(pkg, config)

    assert result.subpackages == ()


def test_nested_package_three_levels_deep(tmp_path: Path) -> None:
    """root → root.sub → root.sub.leaf: the trie depth is 3 (root.sub.sub is there)."""
    pkg = tmp_path / "root"
    _write(pkg / "__init__.py", "")
    _write(pkg / "sub" / "__init__.py", "")
    _write(pkg / "sub" / "leaf.py", "LEAF = True\n")
    config = _default_config()

    result = _build_dir(pkg, config)

    # Root Package
    assert result.name == "root"
    # One subpackage at depth 1
    assert len(result.subpackages) == 1
    sub = result.subpackages[0]
    assert sub.name == "root.sub"
    # The modules of sub must include the leaf module
    sub_module_names = {m.name for m in sub.modules}
    assert "root.sub.leaf" in sub_module_names


def test_nested_trie_root_subpackage_name(tmp_path: Path) -> None:
    """The sub-Package in the trie has the fully qualified name."""
    pkg = tmp_path / "mypkg"
    _write(pkg / "__init__.py", "")
    _write(pkg / "inner" / "__init__.py", "")
    _write(pkg / "inner" / "core.py", "def run() -> None: ...\n")
    config = _default_config()

    result = _build_dir(pkg, config)

    sub = result.subpackages[0]
    assert sub.name == "mypkg.inner"


def test_init_reexport_function_appears_in_init_module(tmp_path: Path) -> None:
    """If __init__.py contains `from .sibling import fn`, the resolved Module of
    the init must contain fn in its functions tuple."""
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

    result = _build_dir(pkg, config)

    # Find the init Module (with the name "mypkg")
    init_module: Module | None = None
    for mod in result.modules:
        if mod.name == "mypkg":
            init_module = mod
            break

    assert init_module is not None, "init module 'mypkg' not found in Package.modules"
    fn_names = {fn.name for fn in init_module.functions}
    assert "helper" in fn_names, f"expected 'helper' in functions; got {fn_names}"


def test_init_reexport_function_is_correct_type(tmp_path: Path) -> None:
    """The re-exported symbol must be a Function instance, not only a name."""
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

    result = _build_dir(pkg, config)

    init_module = next((m for m in result.modules if m.name == "mypkg"), None)
    assert init_module is not None
    assert any(isinstance(fn, Function) and fn.name == "compute" for fn in init_module.functions)


def test_explicit_config_bypasses_file_discovery(tmp_path: Path) -> None:
    """If get_public_api gets config=, it does not look for an .iceberg.toml."""
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py", "")
    _write(pkg / "mod.py", "VALUE = 1\n")

    # Put a broken .iceberg.toml here. A read of this file causes an error.
    (tmp_path / ".iceberg.toml").write_text(
        "unknown_key = true\n",
        encoding="utf-8",
    )

    explicit_config = Config(max_workers=1)

    # Must NOT raise ConfigError, although .iceberg.toml is not valid. config= is
    # explicit, so the code never calls load_config.
    result = get_public_api(pkg, config=explicit_config)

    assert isinstance(result, Package)
    assert result.name == "pkg"


def test_explicit_config_max_workers_respected(tmp_path: Path) -> None:
    """get_public_api accepts Config(max_workers=1), and the result is still a valid Package."""
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


@pytest.mark.parametrize("module_count", [8, 10])
def test_many_modules_all_appear_in_result(tmp_path: Path, module_count: int) -> None:
    """With 8 or more .py modules that are not init modules, the Package trie includes each module."""
    pkg = tmp_path / "bigpkg"
    _write(pkg / "__init__.py", "")

    expected_names: set[str] = set()
    for i in range(module_count):
        name = f"module_{i:02d}"
        _write(pkg / f"{name}.py", f"VALUE_{i} = {i}\n")
        expected_names.add(f"bigpkg.{name}")

    config = Config(max_workers=1)
    result = _build_dir(pkg, config)

    all_names = _all_module_names(result)
    missing = expected_names - all_names
    assert not missing, f"These modules were not found in the result: {sorted(missing)}"


def test_eight_modules_parallel_path(tmp_path: Path) -> None:
    """A package with 8 modules and max_workers > 1 runs the code path of the process pool."""
    pkg = tmp_path / "parallel_pkg"
    _write(pkg / "__init__.py", "")

    expected: set[str] = set()
    for i in range(8):
        mod_name = f"worker_{i}"
        _write(pkg / f"{mod_name}.py", f"N = {i}\n")
        expected.add(f"parallel_pkg.{mod_name}")

    config = Config(max_workers=2)
    result = _build_dir(pkg, config)

    all_names = _all_module_names(result)
    assert expected.issubset(all_names), f"Missing modules: {sorted(expected - all_names)}"


def test_process_pool_gives_same_package_as_in_process(tmp_path: Path) -> None:
    """The process pool and the in-process path give equal results.

    The non-init modules define ``__all__``, and one of them extends it with
    ``__all__ += _base.__all__``. Thus, the workers must get the parsed trees
    and ``known_all`` from the parent process.
    """
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py", "from ._combined import *\nfrom .public import Thing\n")
    _write(
        pkg / "_base.py",
        '__all__ = ["base_fn"]\n\ndef base_fn() -> int: ...\n\ndef base_helper() -> int: ...\n',
    )
    _write(
        pkg / "_combined.py",
        "from . import _base\n"
        "from ._base import *\n"
        '__all__ = ["combined_fn"]\n'
        "__all__ += _base.__all__\n"
        "\n"
        "def combined_fn() -> int: ...\n",
    )
    _write(
        pkg / "public.py",
        '__all__ = ["Thing"]\n\nclass Thing: ...\n\ndef not_exported() -> None: ...\n',
    )
    _write(pkg / "sub" / "__init__.py", "from ._impl import *\n")
    _write(
        pkg / "sub" / "_impl.py",
        '__all__ = ["impl_fn"]\n\ndef impl_fn() -> str: ...\n\ndef impl_helper() -> str: ...\n',
    )

    in_process = _build_dir(pkg, Config(max_workers=1))
    pooled = _build_dir(pkg, Config(max_workers=2))

    assert pooled == in_process

    # Make sure that the comparison is not trivial: `__all__ +=` moved base_fn up.
    init_module = next(m for m in in_process.modules if m.name == "pkg")
    assert {f.name for f in init_module.functions} == {"base_fn", "combined_fn"}


def test_default_config_safe_in_unguarded_script(tmp_path: Path) -> None:
    """A plain script with no ``if __name__ == "__main__":`` guard must work.

    With the spawn and forkserver start methods, worker processes import
    ``__main__`` again. Thus, a process pool here crashes with BrokenProcessPool.
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


def test_hyphenated_directory_does_not_create_phantom_root(tmp_path: Path) -> None:
    """A subdirectory with a hyphen in its name does not add a second root or an empty root name."""
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


def test_non_identifier_root_directory_keeps_its_subpackages(tmp_path: Path) -> None:
    """The packages below a root that is not an identifier become subpackages of the root."""
    root = tmp_path / "my-project"
    _write(root / "core.py", "def f() -> None: ...\n")
    _write(root / "pkg" / "__init__.py", "from .api import g\n")
    _write(root / "pkg" / "api.py", "def g() -> None: ...\n")

    result = build_package(root, _default_config())

    assert isinstance(result, Package)
    assert result.name == "my-project"
    assert [subpackage.name for subpackage in result.subpackages] == ["pkg"]


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
    """iceberg reports a dynamic __all__ one time. Then it uses the underscore rule."""
    pkg = tmp_path / "mypkg"
    _write(pkg / "__init__.py", "")
    _write(pkg / "core.py", "__all__ = ['run']\n__all__ += make()\ndef run(): ...\ndef other(): ...\n")

    with pytest.warns(UserWarning, match=r"core\.py:2: cannot evaluate __all__") as record:
        result = build_package(pkg, _default_config())

    assert len(record) == 1
    assert isinstance(result, Package)
    core = next(mod for mod in result.modules if mod.name == "mypkg.core")

    assert {fn.name for fn in core.functions} == {"run", "other"}


def test_reexport_chain_through_regular_modules_resolved(tmp_path: Path) -> None:
    """pkg re-exports X from _a, which re-exports it from _b, which defines it."""
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py", 'from ._a import X\n__all__ = ["X"]\n')
    _write(pkg / "_a.py", 'from ._b import X\n__all__ = ["X"]\n')
    _write(pkg / "_b.py", "class X:\n    pass\n")

    result = build_package(pkg, _default_config())

    assert isinstance(result, Package)
    (init,) = result.modules

    assert [cls.name for cls in init.classes] == ["X"]
    assert init.references == ()


def test_reexport_cycle_through_regular_modules_left_unresolved(tmp_path: Path) -> None:
    """An import cycle of two modules stops, and X stays a Reference."""
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py", 'from ._a import X\n__all__ = ["X"]\n')
    _write(pkg / "_a.py", 'from ._b import X\n__all__ = ["X"]\n')
    _write(pkg / "_b.py", 'from ._a import X\n__all__ = ["X"]\n')

    result = build_package(pkg, _default_config())

    assert isinstance(result, Package)
    (init,) = result.modules

    assert init.classes == ()
    assert [ref.name for ref in init.references] == ["X"]


@pytest.mark.parametrize(
    "c_source",
    [
        '__all__ = ["X", "f"]\nclass X: ...\ndef f(): ...\ndef g(): ...\n',
        "class X: ...\ndef f(): ...\ndef _g(): ...\n",
    ],
    ids=["with-all", "without-all"],
)
def test_init_star_import_from_tree_resolved(tmp_path: Path, c_source: str) -> None:
    """`from ._c import *` binds the __all__ of _c, or its public names."""
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py", 'from ._c import *\n__all__ = ["X", "f"]\n')
    _write(pkg / "_c.py", c_source)

    result = build_package(pkg, _default_config())

    assert isinstance(result, Package)
    init = _init_module(result, "pkg")

    assert [cls.name for cls in init.classes] == ["X"]
    assert [fn.name for fn in init.functions] == ["f"]
    assert init.references == ()


def test_init_star_import_without_all_exports_star_names(tmp_path: Path) -> None:
    """An init without __all__ re-exports the public names that a star import binds."""
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py", "from ._c import *\n")
    _write(pkg / "_c.py", '__all__ = ["f"]\ndef f(): ...\ndef g(): ...\n')

    result = build_package(pkg, _default_config())

    assert isinstance(result, Package)
    assert [fn.name for fn in _init_module(result, "pkg").functions] == ["f"]


def test_regular_module_star_import_from_tree_resolved(tmp_path: Path) -> None:
    """iceberg resolves a star import in a regular module. Thus, an init that imports from it finds X."""
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py", 'from ._a import X\n__all__ = ["X"]\n')
    _write(pkg / "_a.py", 'from ._b import *\n__all__ = ["X"]\n')
    _write(pkg / "_b.py", "class X: ...\n")

    result = build_package(pkg, _default_config())

    assert isinstance(result, Package)
    init = _init_module(result, "pkg")

    assert [cls.name for cls in init.classes] == ["X"]
    assert init.references == ()


def test_init_star_import_from_outside_tree_is_candidate(tmp_path: Path) -> None:
    """A star import from outside the tree stays unresolved, and the reference names the module."""
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py", 'from os.path import *\nfrom ._c import *\n__all__ = ["join", "f"]\n')
    _write(pkg / "_c.py", "def f(): ...\n")

    result = build_package(pkg, _default_config())

    assert isinstance(result, Package)
    init = _init_module(result, "pkg")

    assert [fn.name for fn in init.functions] == ["f"]
    assert init.references == (Reference(name="join", module="os.path", attribute="join"),)


@pytest.mark.parametrize("max_workers", [1, 2])
def test_each_file_is_parsed_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, max_workers: int) -> None:
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py", "from ._a import A\nfrom .sub import B\n__all__ = ['A', 'B']\n")
    _write(pkg / "_a.py", "__all__ = ['A']\nclass A: ...\n")
    _write(pkg / "_c.py", "def c() -> None: ...\n")
    _write(pkg / "sub" / "__init__.py", "from ._b import B\n")
    _write(pkg / "sub" / "_b.py", "class B: ...\n")
    parsed: Counter[str] = Counter()
    real_parse = ast.parse

    def spy(source: str, filename: str = "<unknown>", *args: Any, **kwargs: Any) -> Any:
        # The counter puts the parses of other files, or parses without a filename, under that name.
        path = Path(filename)
        parsed[path.relative_to(pkg).as_posix() if path.is_relative_to(pkg) else filename] += 1
        return real_parse(source, filename, *args, **kwargs)

    monkeypatch.setattr(ast, "parse", spy)
    # Worker processes do not see the patch. Thus, with workers, the counter
    # counts only the files that this process parses.
    _build_dir(pkg, Config(max_workers=max_workers))
    expected = {"__init__.py": 1, "_a.py": 1, "sub/__init__.py": 1}
    if max_workers == 1:
        expected |= {"_c.py": 1, "sub/_b.py": 1}

    assert parsed == expected


class TestKeepGoing:
    """With an ``errors`` list, iceberg skips and records the modules that fail."""

    @pytest.mark.parametrize("max_workers", [1, 2])
    def test_syntax_error_module_is_skipped(self, tmp_path: Path, max_workers: int) -> None:
        _write(tmp_path / "pkg" / "__init__.py")
        _write(tmp_path / "pkg" / "good.py", "def ok() -> None: ...\n")
        bad = _write(tmp_path / "pkg" / "bad.py", "x = 1\nprint 'py2'\n")
        errors: list[Diagnostic] = []

        result = build_package(tmp_path / "pkg", Config(max_workers=max_workers), errors=errors)

        assert isinstance(result, Package)
        assert _all_module_names(result) == {"pkg", "pkg.good"}
        assert len(errors) == 1
        error = errors[0]

        assert (error.severity, error.module, error.path, error.lineno) == ("error", "pkg.bad", bad, 2)
        assert str(bad) not in error.message

    def test_without_errors_list_syntax_error_raises(self, tmp_path: Path) -> None:
        _write(tmp_path / "pkg" / "__init__.py")
        _write(tmp_path / "pkg" / "bad.py", "print 'py2'\n")

        with pytest.raises(ParseError):
            build_package(tmp_path / "pkg", _default_config())

    def test_unreadable_module_is_skipped_once(self, tmp_path: Path) -> None:
        _write(tmp_path / "pkg" / "__init__.py")
        bad = tmp_path / "pkg" / "bad.py"
        bad.write_bytes(b"\xff\n")
        errors: list[Diagnostic] = []

        build_package(tmp_path / "pkg", _default_config(), errors=errors)

        assert [(error.module, error.path, error.lineno) for error in errors] == [("pkg.bad", bad, None)]
        assert errors[0].message.startswith("cannot decode file")

    def test_without_errors_list_unreadable_module_raises(self, tmp_path: Path) -> None:
        _write(tmp_path / "pkg" / "__init__.py")
        (tmp_path / "pkg" / "bad.py").write_bytes(b"\xff\n")

        with pytest.raises(SourceReadError):
            build_package(tmp_path / "pkg", _default_config(), errors=None)

    def test_broken_init_is_skipped(self, tmp_path: Path) -> None:
        _write(tmp_path / "pkg" / "__init__.py")
        _write(tmp_path / "pkg" / "sub" / "__init__.py", "def (:\n")
        _write(tmp_path / "pkg" / "sub" / "mod.py", "def f() -> None: ...\n")
        errors: list[Diagnostic] = []

        result = build_package(tmp_path / "pkg", _default_config(), errors=errors)

        assert isinstance(result, Package)
        assert _all_module_names(result) == {"pkg", "pkg.sub.mod"}
        assert [error.module for error in errors] == ["pkg.sub"]

    def test_errors_are_sorted_by_module(self, tmp_path: Path) -> None:
        _write(tmp_path / "pkg" / "__init__.py", "def (:\n")
        _write(tmp_path / "pkg" / "b.py", "def (:\n")
        _write(tmp_path / "pkg" / "a.py", "def (:\n")
        errors: list[Diagnostic] = []

        build_package(tmp_path / "pkg", _default_config(), errors=errors)

        assert [error.module for error in errors] == ["pkg", "pkg.a", "pkg.b"]


class TestUnresolvedNameWarnings:
    """iceberg reports only the references that no import binds."""

    def test_package_warnings_point_at_each_module(self, tmp_path: Path) -> None:
        init = _write(tmp_path / "pkg" / "__init__.py", '__all__ = ["sqrt", "lazy", "sub"]\nfrom math import sqrt\n')
        mod = _write(tmp_path / "pkg" / "sub" / "mod.py", '__all__ = ["ghost"]\n')
        _write(tmp_path / "pkg" / "sub" / "__init__.py")
        api = build_package(tmp_path / "pkg", _default_config())

        warnings_found = unresolved_name_warnings(api, tmp_path / "pkg")

        assert [(w.severity, w.module, w.path, w.message) for w in warnings_found] == [
            ("warning", "pkg", init, "'lazy' is exported but never bound"),
            ("warning", "pkg.sub.mod", mod, "'ghost' is exported but never bound"),
        ]

    def test_single_module_uses_given_path(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "solo.py", '__all__ = ["ghost"]\n')
        api = build_package(path, _default_config())

        assert [(w.module, w.path) for w in unresolved_name_warnings(api, path)] == [("solo", path)]

    def test_warnings_are_sorted_by_module_name(self, tmp_path: Path) -> None:
        _write(tmp_path / "pkg" / "__init__.py")
        _write(tmp_path / "pkg" / "b.py", '__all__ = ["ghost_b"]\n')
        _write(tmp_path / "pkg" / "sub" / "__init__.py", '__all__ = ["ghost_sub"]\n')
        api = build_package(tmp_path / "pkg", _default_config())

        assert [w.module for w in unresolved_name_warnings(api, tmp_path / "pkg")] == ["pkg.b", "pkg.sub"]

    def test_resolved_reference_before_an_unresolved_one(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "solo.py", '__all__ = ["a", "ghost"]\nfrom math import sqrt as a\n')
        api = build_package(path, _default_config())

        assert [w.message for w in unresolved_name_warnings(api, path)] == ["'ghost' is exported but never bound"]

    def test_no_references_no_warnings(self, tmp_path: Path) -> None:
        _write(tmp_path / "pkg" / "__init__.py", "def f() -> None: ...\n")

        assert unresolved_name_warnings(build_package(tmp_path / "pkg", _default_config()), tmp_path / "pkg") == []


def test_error_diagnostic_without_message_attribute_uses_str() -> None:
    diagnostic = _error_diagnostic("pkg.mod", Path("mod.py"), IcebergError("boom"))

    assert (diagnostic.message, diagnostic.lineno) == ("boom", None)


def test_evaluate_all_resolves_relative_import_in_nested_module(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py")
    _write(pkg / "sub" / "__init__.py")
    _write(pkg / "sub" / "other.py", '__all__ = ["x"]\n')
    _write(pkg / "sub" / "mod.py", "from .other import __all__\n")

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        known_all = _evaluate_all(discover(pkg, _default_config()), {})

    assert known_all["pkg.sub.mod"] == {"x"}


def test_child_names_by_package_maps_each_package_to_its_direct_children(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py")
    _write(pkg / "a.py")
    _write(pkg / "sub" / "__init__.py")
    _write(pkg / "sub" / "deep" / "b.py")

    assert _child_names_by_package(discover(pkg, _default_config())) == {
        "pkg": frozenset({"a", "sub"}),
        "pkg.sub": frozenset({"deep"}),
        "pkg.sub.deep": frozenset({"b"}),
    }


def test_nested_package_all_filters_by_short_name(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py")
    _write(pkg / "sub" / "__init__.py", '__all__ = ["mod", "deep"]\n')
    _write(pkg / "sub" / "mod.py", "def f() -> None: ...\n")
    _write(pkg / "sub" / "hidden.py", "def g() -> None: ...\n")
    _write(pkg / "sub" / "deep" / "__init__.py")
    _write(pkg / "sub" / "other" / "__init__.py", "def h() -> None: ...\n")

    result = _build_dir(pkg, _default_config())

    assert _all_module_names(result) == {"pkg", "pkg.sub", "pkg.sub.mod", "pkg.sub.deep"}


def test_single_file_warning_names_the_file(tmp_path: Path) -> None:
    path = _write(tmp_path / "solo.py", "__all__ = make()\n")

    with pytest.warns(UserWarning, match=rf"^{re.escape(str(path))}:1: cannot evaluate __all__"):
        build_package(path, _default_config())


def test_subpackage_init_is_resolved_before_its_parent(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    _write(pkg / "__init__.py", 'from .sub import thing\n__all__ = ["thing"]\n')
    _write(pkg / "sub" / "__init__.py", 'from ._impl import thing\n__all__ = ["thing"]\n')
    _write(pkg / "sub" / "_impl.py", "def thing() -> None: ...\n")

    result = _build_dir(pkg, _default_config())
    init = _init_module(result, "pkg")

    assert [function.name for function in init.functions] == ["thing"]
    assert init.references == ()


def test_reexport_chain_with_absolute_import_through_namespace_parent(tmp_path: Path) -> None:
    pkg = tmp_path / "ns" / "pkg"
    _write(pkg / "__init__.py", 'from ._a import X\n__all__ = ["X"]\n')
    _write(pkg / "_a.py", 'from ns.pkg._b import X\n__all__ = ["X"]\n')
    _write(pkg / "_b.py", "class X:\n    pass\n")

    result = _build_dir(pkg, _default_config())
    (init,) = result.modules

    assert [cls.name for cls in init.classes] == ["X"]
    assert init.references == ()


def _subpackage_names(pkg: Package) -> list[str]:
    return [subpackage.name for subpackage in pkg.subpackages]


class TestRootWithoutTopLevelModule:
    """A root directory that has packages but no ``.py`` file directly in it."""

    def test_regular_packages_are_all_subpackages_of_the_root(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write(src / "alpha" / "__init__.py", "def a() -> None: ...\n")
        _write(src / "beta" / "__init__.py", "def b() -> None: ...\n")

        result = _build_dir(src, _default_config())

        assert result.name == "src"
        assert result.path == src
        assert result.modules == ()
        assert _subpackage_names(result) == ["src.alpha", "src.beta"]

    def test_namespace_packages_are_all_subpackages_of_the_root(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write(src / "alpha" / "core.py", "def a() -> None: ...\n")
        _write(src / "beta" / "core.py", "def b() -> None: ...\n")

        result = _build_dir(src, _default_config())

        assert result.name == "src"
        assert _subpackage_names(result) == ["src.alpha", "src.beta"]
        assert _all_module_names(result) == {"src.alpha.core", "src.beta.core"}

    def test_directories_without_modules_between_root_and_package_become_packages(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write(src / "alpha" / "__init__.py", "def a() -> None: ...\n")
        _write(src / "beta" / "deep" / "inner" / "core.py", "def b() -> None: ...\n")

        result = _build_dir(src, _default_config())
        (_, beta) = result.subpackages
        (deep,) = beta.subpackages
        (inner,) = deep.subpackages

        assert (beta.name, beta.path) == ("src.beta", src / "beta")
        assert (deep.name, deep.path) == ("src.beta.deep", src / "beta" / "deep")
        assert inner.name == "src.beta.deep.inner"
        assert _all_module_names(result) == {"src.alpha", "src.beta.deep.inner.core"}

    def test_top_level_module_and_deep_package_are_connected(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write(src / "top.py", "def t() -> None: ...\n")
        _write(src / "beta" / "deep" / "core.py", "def b() -> None: ...\n")

        result = _build_dir(src, _default_config())

        assert _all_module_names(result) == {"src.top", "src.beta.deep.core"}

    def test_one_package_stays_the_root(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write(src / "ns" / "pkg" / "__init__.py", "def a() -> None: ...\n")

        result = _build_dir(src, _default_config())

        assert result.name == "src.ns.pkg"
        assert result.path == src / "ns" / "pkg"

    def test_result_is_the_same_for_each_hash_seed(self, tmp_path: Path) -> None:
        """The set order changes with ``PYTHONHASHSEED``. Thus, run the CLI in a new process for each seed."""
        src = tmp_path / "src"
        for name in ("alpha", "beta", "gamma"):
            _write(src / name / "__init__.py", f"def {name}() -> None: ...\n")

        outputs: set[str] = set()
        for seed in ("0", "1", "2", "3"):
            completed = subprocess.run(
                [sys.executable, "-m", "sheridan.iceberg", "--no-config", str(src)],
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
                env={**os.environ, "PYTHONHASHSEED": seed},
            )
            outputs.add(completed.stdout)

        (output,) = outputs
        assert "package src.alpha" in output
        assert "package src.beta" in output
        assert "package src.gamma" in output
