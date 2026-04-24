"""Dogfood test: run get_public_api against the iceberg package itself.

This test exercises the full discover → visit → resolve_init → assemble
pipeline on the real iceberg source tree.  It acts as a surface-drift guard:
if a name is removed from (or never added to) the public API, the test fails
loudly instead of silently losing the symbol.
"""

from pathlib import Path

import pytest

from sheridan.iceberg import Class, Module, Package, get_public_api

# ---------------------------------------------------------------------------
# Expected public surface
# ---------------------------------------------------------------------------

# Every name listed here must be reachable somewhere in the Package trie
# returned by get_public_api.  Add names here when the public surface grows;
# remove them only when a symbol is intentionally dropped.
#
# NOTE: This test WILL FAIL if the public surface changes — that is the point.
# Surface drift becomes a test failure rather than a silent omission.
EXPECTED_PUBLIC_NAMES: frozenset[str] = frozenset(
    {
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
    }
)

# ---------------------------------------------------------------------------
# Path fixture
# ---------------------------------------------------------------------------

# Resolve the package directory relative to this test file so the test works
# regardless of the working directory the test runner is invoked from.
#   tests/functional/test_dogfood.py
#     ^parents[0] = tests/functional
#     ^parents[1] = tests
#     ^parents[2] = repo root
_ICEBERG_SRC: Path = Path(__file__).parents[2] / "src" / "sheridan"


@pytest.fixture(scope="module")
def iceberg_package() -> Package | Module:
    """Return the Package produced by analyzing the iceberg source tree."""
    assert _ICEBERG_SRC.is_dir(), (
        f"Expected iceberg source directory at {_ICEBERG_SRC}; check that the repo layout has not changed."
    )
    return get_public_api(_ICEBERG_SRC)


# ---------------------------------------------------------------------------
# Trie-walking helpers
# ---------------------------------------------------------------------------


def _all_modules(pkg: Package) -> list[Module]:
    """Flatten all Module objects from a Package trie into a list."""
    result: list[Module] = list(pkg.modules)
    for sub in pkg.subpackages:
        result.extend(_all_modules(sub))
    return result


def _collect_public_names(pkg: Package) -> set[str]:
    """Walk the Package trie and collect every public symbol name.

    Collects names from:
    - module-level functions
    - module-level classes (and their methods and nested classes, recursively)
    - module-level assignments
    """

    def _collect_class_names(cls: Class) -> set[str]:
        """Recursively collect the class name plus nested class names."""
        names: set[str] = {cls.name}
        for nested in cls.nested_classes:
            names |= _collect_class_names(nested)
        return names

    names: set[str] = set()
    for mod in _all_modules(pkg):
        for fn in mod.functions:
            names.add(fn.name)
        for cls in mod.classes:
            names |= _collect_class_names(cls)
        for assignment in mod.assignments:
            names.add(assignment.name)
    return names


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_get_public_api_on_iceberg_returns_package(iceberg_package: Package) -> None:
    """get_public_api must succeed and return a Package instance."""
    assert isinstance(iceberg_package, Package)


def test_iceberg_package_name(iceberg_package: Package) -> None:
    """The root Package name must be 'iceberg'."""
    assert iceberg_package.name == "sheridan.iceberg"


def test_iceberg_package_path(iceberg_package: Package) -> None:
    """Package.path must resolve to the iceberg source directory."""
    assert iceberg_package.path.resolve() == (_ICEBERG_SRC / "iceberg").resolve()


def test_expected_public_names_present(iceberg_package: Package) -> None:
    """Every name in EXPECTED_PUBLIC_NAMES must be present in the trie.

    This guards against accidental removal of public symbols.  If a name
    disappears from the trie without a corresponding update to
    EXPECTED_PUBLIC_NAMES, this test will fail.
    """
    collected = _collect_public_names(iceberg_package)
    missing = EXPECTED_PUBLIC_NAMES - collected
    assert not missing, (
        f"The following expected public names were not found in the iceberg "
        f"package trie: {sorted(missing)}.  Either the symbols were removed "
        f"from the implementation or EXPECTED_PUBLIC_NAMES needs updating."
    )
