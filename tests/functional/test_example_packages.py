"""Functional tests using fixture packages in tests/fixtures/.

Each test exercises get_public_api against a real on-disk fixture package and
verifies the three behaviours introduced by __all__-driven filtering:

1. Private modules (e.g. _models, _utils, _private) do NOT appear in
   Package.modules.  Only the init module (or a module whose name is in
   __all__) appears.
2. Private subpackages (e.g. _private_sub) do NOT appear in
   Package.subpackages.  Only subpackages named in __all__ appear.
3. Symbols listed in __init__.__all__ are hoisted into the package-level
   Module (the resolved init module, always the first and only entry in
   Package.modules when __all__ is defined).
"""

import re
from pathlib import Path

import pytest

from sheridan.iceberg import get_public_api
from sheridan.iceberg._config import Config
from sheridan.iceberg._models import Module, Package

# ---------------------------------------------------------------------------
# Shared config — single worker keeps process overhead minimal in tests.
# ---------------------------------------------------------------------------

_CFG = Config(max_workers=1, test_module_pattern=re.compile(r"(^|/)test_[^/]*\.py$|_test\.py$"))

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _module_names(pkg: Package) -> set[str]:
    """Return the set of short module names (last dotted component) at the top level."""
    return {m.name for m in pkg.modules}


def _subpackage_names(pkg: Package) -> set[str]:
    """Return the set of top-level subpackage names (last dotted component)."""
    return {sp.name for sp in pkg.subpackages}


def _class_names(module: Module) -> set[str]:
    return {c.name for c in module.classes}


def _function_names(module: Module) -> set[str]:
    return {f.name for f in module.functions}


# ---------------------------------------------------------------------------
# simple_pkg — flat package, __all__ = ['MyClass', 'my_func']
# private modules: _models, _utils
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def simple_pkg() -> Package:
    path = _FIXTURES_DIR / "simple_pkg"
    return get_public_api(path, config=_CFG)


def test_simple_pkg_name(simple_pkg: Package) -> None:
    assert simple_pkg.name == "simple_pkg"


def test_simple_pkg_no_subpackages(simple_pkg: Package) -> None:
    assert simple_pkg.subpackages == ()


def test_simple_pkg_private_modules_excluded(simple_pkg: Package) -> None:
    """_models and _utils must not appear as modules."""
    names = _module_names(simple_pkg)
    assert "simple_pkg._models" not in names
    assert "simple_pkg._utils" not in names
    # Also check short names just in case
    assert "_models" not in names
    assert "_utils" not in names


def test_simple_pkg_has_exactly_one_module(simple_pkg: Package) -> None:
    """With __all__ defined, only the init module is included."""
    assert len(simple_pkg.modules) == 1


def test_simple_pkg_init_module_name(simple_pkg: Package) -> None:
    """The single module's name should be the package name (the init module)."""
    assert simple_pkg.modules[0].name == "simple_pkg"


def test_simple_pkg_myclass_hoisted(simple_pkg: Package) -> None:
    """MyClass (re-exported from _models) must be hoisted into the init module."""
    init_mod = simple_pkg.modules[0]
    assert "MyClass" in _class_names(init_mod)


def test_simple_pkg_my_func_hoisted(simple_pkg: Package) -> None:
    """my_func (re-exported from _utils) must be hoisted into the init module."""
    init_mod = simple_pkg.modules[0]
    assert "my_func" in _function_names(init_mod)


# ---------------------------------------------------------------------------
# nested_pkg — has public subpackage public_sub/ and private _private_sub/;
# private module _private.py; __all__ = ['PublicSub', 'top_level_func']
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def nested_pkg() -> Package:
    path = _FIXTURES_DIR / "nested_pkg"
    return get_public_api(path, config=_CFG)


def test_nested_pkg_name(nested_pkg: Package) -> None:
    assert nested_pkg.name == "nested_pkg"


def test_nested_pkg_private_module_excluded(nested_pkg: Package) -> None:
    """_private.py must not appear as a module."""
    names = _module_names(nested_pkg)
    assert "nested_pkg._private" not in names
    assert "_private" not in names


def test_nested_pkg_private_subpackage_excluded(nested_pkg: Package) -> None:
    """_private_sub subpackage must not appear in subpackages."""
    names = _subpackage_names(nested_pkg)
    assert "nested_pkg._private_sub" not in names
    assert "_private_sub" not in names


def test_nested_pkg_public_sub_not_a_subpackage(nested_pkg: Package) -> None:
    """public_sub's directory name is not listed in __all__, so it must not appear as a subpackage.

    __all__ = ['PublicSub', 'top_level_func'] names the class, not the subpackage directory.
    Per the design contract, only subpackages whose short name appears in __all__ are included.
    """
    names = _subpackage_names(nested_pkg)
    assert "nested_pkg.public_sub" not in names
    assert "public_sub" not in names


def test_nested_pkg_top_level_func_hoisted(nested_pkg: Package) -> None:
    """top_level_func is defined directly in __init__ and named in __all__."""
    assert len(nested_pkg.modules) == 1
    init_mod = nested_pkg.modules[0]
    assert "top_level_func" in _function_names(init_mod)


def test_nested_pkg_no_subpackages(nested_pkg: Package) -> None:
    """With __all__ listing only symbols (not subpackage names), subpackages is empty."""
    assert nested_pkg.subpackages == ()


# ---------------------------------------------------------------------------
# reexport_pkg — re-exports Alpha, Beta, gamma from private submodules;
# __all__ = ['Alpha', 'Beta', 'gamma']
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def reexport_pkg() -> Package:
    path = _FIXTURES_DIR / "reexport_pkg"
    return get_public_api(path, config=_CFG)


def test_reexport_pkg_name(reexport_pkg: Package) -> None:
    assert reexport_pkg.name == "reexport_pkg"


def test_reexport_pkg_no_subpackages(reexport_pkg: Package) -> None:
    assert reexport_pkg.subpackages == ()


def test_reexport_pkg_private_modules_excluded(reexport_pkg: Package) -> None:
    """_alpha, _beta, _gamma must not appear as top-level modules."""
    names = _module_names(reexport_pkg)
    for private in ("_alpha", "_beta", "_gamma", "reexport_pkg._alpha", "reexport_pkg._beta", "reexport_pkg._gamma"):
        assert private not in names


def test_reexport_pkg_has_exactly_one_module(reexport_pkg: Package) -> None:
    assert len(reexport_pkg.modules) == 1


def test_reexport_pkg_alpha_hoisted(reexport_pkg: Package) -> None:
    """Alpha must be hoisted into the init module."""
    init_mod = reexport_pkg.modules[0]
    assert "Alpha" in _class_names(init_mod)


def test_reexport_pkg_beta_hoisted(reexport_pkg: Package) -> None:
    """Beta must be hoisted into the init module."""
    init_mod = reexport_pkg.modules[0]
    assert "Beta" in _class_names(init_mod)


def test_reexport_pkg_gamma_hoisted(reexport_pkg: Package) -> None:
    """gamma must be hoisted into the init module."""
    init_mod = reexport_pkg.modules[0]
    assert "gamma" in _function_names(init_mod)


# ---------------------------------------------------------------------------
# mixed_pkg — public_module.py is in __all__; _private_module.py is not;
# __all__ = ['PublicThing', 'public_module']
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mixed_pkg() -> Package:
    path = _FIXTURES_DIR / "mixed_pkg"
    return get_public_api(path, config=_CFG)


def test_mixed_pkg_name(mixed_pkg: Package) -> None:
    assert mixed_pkg.name == "mixed_pkg"


def test_mixed_pkg_private_module_excluded(mixed_pkg: Package) -> None:
    """_private_module must not appear anywhere in the package."""
    names = _module_names(mixed_pkg)
    assert "_private_module" not in names
    assert "mixed_pkg._private_module" not in names


def test_mixed_pkg_public_thing_hoisted(mixed_pkg: Package) -> None:
    """PublicThing is re-exported via __init__; it must be on the init module."""
    init_mod = mixed_pkg.modules[0]
    assert "PublicThing" in _class_names(init_mod)


@pytest.mark.parametrize("private_name", ["_private_module", "mixed_pkg._private_module"])
def test_mixed_pkg_private_module_not_in_any_module(mixed_pkg: Package, private_name: str) -> None:
    """_private_module must not be the name of any Module in the trie."""
    all_mod_names = {m.name for m in mixed_pkg.modules}
    assert private_name not in all_mod_names
