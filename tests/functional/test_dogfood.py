"""Run get_public_api on the iceberg package (dogfood test).

This test runs the full pipeline (discover → visit → resolve_init → assemble)
on the real iceberg source tree. It finds changes to the public API. If a name
goes out of the public API (or never goes into it), the test fails. The symbol
does not go away silently.
"""

from pathlib import Path

import pytest

from sheridan.iceberg import Class, Module, Package, get_public_api

# Each name in this list must be in the Package trie that get_public_api gives.
# When the public API gets larger, add the names here. Remove a name only when
# you intentionally remove the symbol.
#
# NOTE: This test WILL FAIL if the public API changes. That is its purpose.
# A change to the API becomes a test failure, not a silent omission.
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
        "Config",
        "ConfigError",
        "Reference",
        "SourceReadError",
        "SnapshotError",
        "load_json",
    }
)


# Resolve the package directory relative to this test file. Then the test works
# from all current directories.
#   tests/functional/test_dogfood.py
#     ^parents[0] = tests/functional
#     ^parents[1] = tests
#     ^parents[2] = repo root
_ICEBERG_SRC: Path = Path(__file__).parents[2] / "src" / "sheridan"


@pytest.fixture(scope="module")
def iceberg_package() -> Package | Module:
    """Analyze the iceberg source tree and make a Package."""
    assert _ICEBERG_SRC.is_dir(), (
        f"Expected iceberg source directory at {_ICEBERG_SRC}; check that the repo layout has not changed."
    )
    return get_public_api(_ICEBERG_SRC)


def _all_modules(pkg: Package) -> list[Module]:
    """Put all the Module objects of a Package trie into a flat list."""
    result: list[Module] = list(pkg.modules)
    for sub in pkg.subpackages:
        result.extend(_all_modules(sub))

    return result


def _collect_public_names(pkg: Package) -> set[str]:
    """Walk through the Package trie and collect the name of each public symbol.

    The function collects the names of:
    - module-level functions
    - module-level classes (and their methods and nested classes, recursively)
    - module-level assignments
    """

    def _collect_class_names(cls: Class) -> set[str]:
        """Collect the class name and the names of the nested classes recursively."""
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


def test_get_public_api_on_iceberg_returns_package(iceberg_package: Package) -> None:
    """get_public_api must be successful and give a Package instance."""
    assert isinstance(iceberg_package, Package)


def test_iceberg_package_name(iceberg_package: Package) -> None:
    """The root Package name must be 'iceberg'."""
    assert iceberg_package.name == "sheridan.iceberg"


def test_iceberg_package_path(iceberg_package: Package) -> None:
    """Package.path must resolve to the iceberg source directory."""
    assert iceberg_package.path.resolve() == (_ICEBERG_SRC / "iceberg").resolve()


def test_expected_public_names_present(iceberg_package: Package) -> None:
    """Each name in EXPECTED_PUBLIC_NAMES must be in the trie.

    This test finds public symbols that a change removed accidentally. If a
    name goes out of the trie and EXPECTED_PUBLIC_NAMES does not change, this
    test fails.
    """
    collected = _collect_public_names(iceberg_package)
    missing = EXPECTED_PUBLIC_NAMES - collected

    assert not missing, (
        f"The following expected public names were not found in the iceberg "
        f"package trie: {sorted(missing)}.  Either the symbols were removed "
        f"from the implementation or EXPECTED_PUBLIC_NAMES needs updating."
    )


def test_expected_public_names_present_when_rooted_at_inner_package() -> None:
    """If you give iceberg ``src/sheridan/iceberg`` (not ``src/sheridan``), it
    must still resolve the ``from sheridan.iceberg... import`` re-exports in
    the ``__init__.py`` of the package.
    """
    api = get_public_api(_ICEBERG_SRC / "iceberg")

    assert isinstance(api, Package)
    assert api.name == "iceberg"
    missing = EXPECTED_PUBLIC_NAMES - _collect_public_names(api)

    assert not missing, f"Missing when rooted at the inner package: {sorted(missing)}"
    assert api.references == ()
