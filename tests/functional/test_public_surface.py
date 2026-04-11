"""Functional tests for the public surface of sheridan.iceberg."""

import importlib
import types

import pytest


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
        "IcebergError",
        "InvalidPathError",
        "ParseError",
        "ConfigError",
    }
    assert set(iceberg.__all__) == expected


@pytest.mark.parametrize(
    "name",
    [
        "get_public_api",
        "Package",
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
