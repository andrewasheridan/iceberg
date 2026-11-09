"""Test get_public_api with the fixture packages in tests/fixtures/.

Each test runs get_public_api on a real fixture package on disk. The tests
examine the three effects of the __all__ filter:

1. Package.modules does NOT contain private modules (for example _models,
   _utils, _private). It contains only the init module and the modules with a
   name in __all__.
2. Package.subpackages does NOT contain private subpackages (for example
   _private_sub). It contains only the subpackages with a name in __all__.
3. iceberg moves the symbols in __init__.__all__ up into the package-level
   Module. This is the resolved init module. If the package defines __all__,
   it is the first and only item in Package.modules.
"""

import re
from pathlib import Path

import pytest

from sheridan.iceberg import get_public_api
from sheridan.iceberg._config import Config
from sheridan.iceberg._models import Module, Package

# One worker keeps the process overhead low in tests.
_CFG = Config(max_workers=1, test_module_pattern=re.compile(r"(^|/)test_[^/]*\.py$|_test\.py$"))

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _snapshot_package(path: Path) -> Package:
    """Snapshot a fixture package, and narrow the ``Package | Module`` result."""
    result = get_public_api(path, config=_CFG)

    assert isinstance(result, Package)
    return result


def _module_names(pkg: Package) -> set[str]:
    """Collect the set of short module names (the last dotted component) at the top level."""
    return {m.name for m in pkg.modules}


def _subpackage_names(pkg: Package) -> set[str]:
    """Collect the set of top-level subpackage names (the last dotted component)."""
    return {sp.name for sp in pkg.subpackages}


def _class_names(module: Module) -> set[str]:
    return {c.name for c in module.classes}


def _function_names(module: Module) -> set[str]:
    return {f.name for f in module.functions}


@pytest.fixture(scope="module")
def simple_pkg() -> Package:
    """A flat package with ``__all__ = ['MyClass', 'my_func']`` and the private modules ``_models`` and ``_utils``."""
    path = _FIXTURES_DIR / "simple_pkg"
    return _snapshot_package(path)


def test_simple_pkg_name(simple_pkg: Package) -> None:
    assert simple_pkg.name == "simple_pkg"


def test_simple_pkg_no_subpackages(simple_pkg: Package) -> None:
    assert simple_pkg.subpackages == ()


def test_simple_pkg_private_modules_excluded(simple_pkg: Package) -> None:
    """The modules must not include _models and _utils."""
    names = _module_names(simple_pkg)

    assert "simple_pkg._models" not in names
    assert "simple_pkg._utils" not in names
    # Also examine the short names, as an additional check
    assert "_models" not in names
    assert "_utils" not in names


def test_simple_pkg_has_exactly_one_module(simple_pkg: Package) -> None:
    """If the package defines __all__, the modules include only the init module."""
    assert len(simple_pkg.modules) == 1


def test_simple_pkg_init_module_name(simple_pkg: Package) -> None:
    """The name of the one module must be the package name (the init module)."""
    assert simple_pkg.modules[0].name == "simple_pkg"


def test_simple_pkg_myclass_hoisted(simple_pkg: Package) -> None:
    """iceberg must move MyClass (re-exported from _models) up into the init module."""
    init_mod = simple_pkg.modules[0]
    assert "MyClass" in _class_names(init_mod)


def test_simple_pkg_my_func_hoisted(simple_pkg: Package) -> None:
    """iceberg must move my_func (re-exported from _utils) up into the init module."""
    init_mod = simple_pkg.modules[0]
    assert "my_func" in _function_names(init_mod)


@pytest.fixture(scope="module")
def nested_pkg() -> Package:
    """A package with the public subpackage ``public_sub/``, the private ``_private_sub/`` and ``_private.py``.

    ``__all__ = ['PublicSub', 'top_level_func']``.
    """
    path = _FIXTURES_DIR / "nested_pkg"
    return _snapshot_package(path)


def test_nested_pkg_name(nested_pkg: Package) -> None:
    assert nested_pkg.name == "nested_pkg"


def test_nested_pkg_private_module_excluded(nested_pkg: Package) -> None:
    """The modules must not include _private.py."""
    names = _module_names(nested_pkg)

    assert "nested_pkg._private" not in names
    assert "_private" not in names


def test_nested_pkg_private_subpackage_excluded(nested_pkg: Package) -> None:
    """The subpackages must not include _private_sub."""
    names = _subpackage_names(nested_pkg)

    assert "nested_pkg._private_sub" not in names
    assert "_private_sub" not in names


def test_nested_pkg_public_sub_not_a_subpackage(nested_pkg: Package) -> None:
    """__all__ does not list the directory name of public_sub. Thus, it must not be a subpackage.

    __all__ = ['PublicSub', 'top_level_func'] names the class, not the subpackage directory.
    The design includes only the subpackages with a short name in __all__.
    """
    names = _subpackage_names(nested_pkg)

    assert "nested_pkg.public_sub" not in names
    assert "public_sub" not in names


def test_nested_pkg_top_level_func_hoisted(nested_pkg: Package) -> None:
    """__init__ defines top_level_func directly, and __all__ names it."""
    assert len(nested_pkg.modules) == 1
    init_mod = nested_pkg.modules[0]

    assert "top_level_func" in _function_names(init_mod)


def test_nested_pkg_public_sub_hoisted(nested_pkg: Package) -> None:
    """__init__ imports PublicSub from the public_sub subpackage, and __all__ names it. iceberg must move it up."""
    init_mod = nested_pkg.modules[0]
    assert "PublicSub" in _class_names(init_mod)


def test_nested_pkg_no_subpackages(nested_pkg: Package) -> None:
    """If __all__ lists only symbols (not subpackage names), subpackages is empty."""
    assert nested_pkg.subpackages == ()


@pytest.fixture(scope="module")
def reexport_pkg() -> Package:
    """A package that re-exports ``Alpha``, ``Beta`` and ``gamma`` from private submodules."""
    path = _FIXTURES_DIR / "reexport_pkg"
    return _snapshot_package(path)


def test_reexport_pkg_name(reexport_pkg: Package) -> None:
    assert reexport_pkg.name == "reexport_pkg"


def test_reexport_pkg_no_subpackages(reexport_pkg: Package) -> None:
    assert reexport_pkg.subpackages == ()


def test_reexport_pkg_private_modules_excluded(reexport_pkg: Package) -> None:
    """The top-level modules must not include _alpha, _beta and _gamma."""
    names = _module_names(reexport_pkg)
    for private in ("_alpha", "_beta", "_gamma", "reexport_pkg._alpha", "reexport_pkg._beta", "reexport_pkg._gamma"):
        assert private not in names


def test_reexport_pkg_has_exactly_one_module(reexport_pkg: Package) -> None:
    assert len(reexport_pkg.modules) == 1


def test_reexport_pkg_alpha_hoisted(reexport_pkg: Package) -> None:
    """iceberg must move Alpha up into the init module."""
    init_mod = reexport_pkg.modules[0]
    assert "Alpha" in _class_names(init_mod)


def test_reexport_pkg_beta_hoisted(reexport_pkg: Package) -> None:
    """iceberg must move Beta up into the init module."""
    init_mod = reexport_pkg.modules[0]
    assert "Beta" in _class_names(init_mod)


def test_reexport_pkg_gamma_hoisted(reexport_pkg: Package) -> None:
    """iceberg must move gamma up into the init module."""
    init_mod = reexport_pkg.modules[0]
    assert "gamma" in _function_names(init_mod)


@pytest.fixture(scope="module")
def mixed_pkg() -> Package:
    """A package with an ``__all__`` that lists ``public_module`` but not ``_private_module``.

    ``__all__ = ['PublicThing', 'public_module']``.
    """
    path = _FIXTURES_DIR / "mixed_pkg"
    return _snapshot_package(path)


def test_mixed_pkg_name(mixed_pkg: Package) -> None:
    assert mixed_pkg.name == "mixed_pkg"


def test_mixed_pkg_private_module_excluded(mixed_pkg: Package) -> None:
    """The package must not include _private_module at any level."""
    names = _module_names(mixed_pkg)

    assert "_private_module" not in names
    assert "mixed_pkg._private_module" not in names


def test_mixed_pkg_public_thing_hoisted(mixed_pkg: Package) -> None:
    """__init__ re-exports PublicThing. Thus, the init module must have it."""
    init_mod = mixed_pkg.modules[0]
    assert "PublicThing" in _class_names(init_mod)


@pytest.mark.parametrize("private_name", ["_private_module", "mixed_pkg._private_module"])
def test_mixed_pkg_private_module_not_in_any_module(mixed_pkg: Package, private_name: str) -> None:
    """No Module in the trie can have the name _private_module."""
    all_mod_names = {m.name for m in mixed_pkg.modules}
    assert private_name not in all_mod_names


def test_mixed_pkg_public_module_present(mixed_pkg: Package) -> None:
    """__all__ lists public_module. Thus, the package must have it as a Module."""
    assert "mixed_pkg.public_module" in _module_names(mixed_pkg)


def test_mixed_pkg_public_module_has_members(mixed_pkg: Package) -> None:
    """public_module must show its public members."""
    public_mod = next(m for m in mixed_pkg.modules if m.name == "mixed_pkg.public_module")
    assert "public_fn" in _function_names(public_mod)


@pytest.fixture(scope="module")
def alias_pkg() -> Package:
    """A package that re-exports ``Beta`` from ``_beta`` as ``Delta``. ``__all__ = ['Delta']``."""
    path = _FIXTURES_DIR / "alias_pkg"
    return _snapshot_package(path)


def test_alias_pkg_has_exactly_one_module(alias_pkg: Package) -> None:
    assert len(alias_pkg.modules) == 1


def test_alias_pkg_private_module_excluded(alias_pkg: Package) -> None:
    names = _module_names(alias_pkg)

    assert "_beta" not in names
    assert "alias_pkg._beta" not in names


def test_alias_pkg_class_hoisted_under_alias(alias_pkg: Package) -> None:
    """iceberg must show the re-exported class with its alias ``Delta``, not with its source name ``Beta``."""
    init_mod = alias_pkg.modules[0]

    assert _class_names(init_mod) == {"Delta"}
