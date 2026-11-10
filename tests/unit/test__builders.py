"""Test sheridan.iceberg._builders."""

import ast

import pytest

from sheridan.iceberg._builders import (
    _MAX_DEFAULT_LENGTH,
    _decorator_name,
    _is_property_accessor,
    _value_source,
    build_class,
)
from sheridan.iceberg._models import Assignment


def _function(source: str) -> ast.FunctionDef:
    node = ast.parse(source).body[0]

    assert isinstance(node, ast.FunctionDef)
    return node


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("overload", "overload"),
        ("functools.cached_property", "cached_property"),
        ("lru_cache(maxsize=None)", "lru_cache"),
        ("functools.lru_cache(maxsize=None)", "lru_cache"),
        ("handlers[0]", None),
    ],
)
def test_decorator_name(source: str, expected: str | None) -> None:
    assert _decorator_name(ast.parse(source, mode="eval").body) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("@p.setter\ndef p(self, value): ...", True),
        ("@p.getter\ndef p(self): ...", True),
        ("@p.deleter\ndef p(self): ...", True),
        ("@staticmethod\n@p.setter\ndef p(self, value): ...", True),
        ("@q.setter\ndef p(self, value): ...", False),
        ("@p.cache\ndef p(self): ...", False),
        ("@property\ndef p(self): ...", False),
        ("def p(self): ...", False),
    ],
)
def test_is_property_accessor(source: str, expected: bool) -> None:
    assert _is_property_accessor(_function(source)) is expected


def test_value_source_keeps_a_default_at_the_length_limit() -> None:
    text = "x" * (_MAX_DEFAULT_LENGTH - 2)
    node = ast.Constant(value=text)

    assert _value_source(node) == repr(text)
    assert len(repr(text)) == _MAX_DEFAULT_LENGTH


def test_value_source_replaces_a_default_over_the_length_limit() -> None:
    assert _value_source(ast.Constant(value="x" * _MAX_DEFAULT_LENGTH)) == "..."


def test_build_class_collects_type_alias_statements() -> None:
    node = ast.parse("class C:\n    type Alias = int\n").body[0]

    assert isinstance(node, ast.ClassDef)
    assert build_class(node).assignments == (Assignment(name="Alias", annotation="TypeAlias"),)
