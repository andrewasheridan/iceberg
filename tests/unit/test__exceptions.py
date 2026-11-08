"""Tests for sheridan.iceberg._exceptions."""

import pytest

from sheridan.iceberg._exceptions import (
    ConfigError,
    IcebergError,
    InvalidPathError,
    ParseError,
)

# ---------------------------------------------------------------------------
# Subclass relationships
# ---------------------------------------------------------------------------


def test_iceberg_error_is_subclass_of_exception() -> None:
    assert issubclass(IcebergError, Exception)


def test_invalid_path_error_is_subclass_of_iceberg_error() -> None:
    assert issubclass(InvalidPathError, IcebergError)


def test_parse_error_is_subclass_of_iceberg_error() -> None:
    assert issubclass(ParseError, IcebergError)


def test_config_error_is_subclass_of_iceberg_error() -> None:
    assert issubclass(ConfigError, IcebergError)


# ---------------------------------------------------------------------------
# Raise-and-catch
# ---------------------------------------------------------------------------


def test_iceberg_error_can_be_raised_and_caught() -> None:
    with pytest.raises(IcebergError):
        raise IcebergError("base error")


def test_invalid_path_error_can_be_raised_and_caught() -> None:
    with pytest.raises(InvalidPathError):
        raise InvalidPathError("bad path")


def test_parse_error_can_be_raised_and_caught() -> None:
    with pytest.raises(ParseError):
        raise ParseError("syntax problem")


def test_config_error_can_be_raised_and_caught() -> None:
    with pytest.raises(ConfigError):
        raise ConfigError("bad config")


# ---------------------------------------------------------------------------
# Subclass instances are also catchable as IcebergError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc_class",
    [InvalidPathError, ParseError, ConfigError],
)
def test_subclass_caught_as_iceberg_error(exc_class: type) -> None:
    with pytest.raises(IcebergError):
        raise exc_class("caught as base")
