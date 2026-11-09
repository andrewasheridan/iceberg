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


# ---------------------------------------------------------------------------
# ParseError location attributes
# ---------------------------------------------------------------------------


def test_parse_error_location_defaults_to_none() -> None:
    err = ParseError("syntax problem")
    assert (err.path, err.lineno, err.offset) == (None, None, None)
    assert str(err) == "syntax problem"


def test_parse_error_str_includes_full_location() -> None:
    err = ParseError("invalid syntax", path="src/pkg/mod.py", lineno=12, offset=5)
    assert (err.path, err.lineno, err.offset) == ("src/pkg/mod.py", 12, 5)
    assert str(err) == "src/pkg/mod.py:12:5: invalid syntax"


def test_parse_error_str_omits_missing_parts() -> None:
    assert str(ParseError("bad", path="mod.py", lineno=3)) == "mod.py:3: bad"
    assert str(ParseError("bad", path="mod.py")) == "mod.py: bad"
    assert str(ParseError("bad", lineno=3, offset=1)) == "3:1: bad"


def test_parse_error_from_syntax_error_uses_filename_from_exception() -> None:
    with pytest.raises(SyntaxError) as info:
        compile("def f(:\n", "src/pkg/mod.py", "exec")
    err = ParseError.from_syntax_error(info.value)
    assert err.path == "src/pkg/mod.py"
    assert err.lineno == 1
    assert err.offset == info.value.offset
    assert str(err).startswith(f"src/pkg/mod.py:1:{info.value.offset}: ")
    assert err.message == info.value.msg


def test_parse_error_from_syntax_error_ignores_unknown_filename() -> None:
    with pytest.raises(SyntaxError) as info:
        compile("def f(:\n", "<unknown>", "exec")
    assert ParseError.from_syntax_error(info.value).path is None
