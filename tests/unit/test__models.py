"""Tests for the frozen dataclass models in sheridan.iceberg._models."""

import dataclasses
from pathlib import Path

import pytest

from sheridan.iceberg._models import (
    Assignment,
    Class,
    Function,
    Module,
    Package,
    Parameter,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

ALL_CLASSES = [Parameter, Function, Assignment, Class, Module, Package]


def _make_parameter(
    name: str = "x",
    annotation: str | None = "int",
    default: str | None = None,
) -> Parameter:
    return Parameter(name=name, annotation=annotation, default=default)


def _make_function(
    name: str = "f",
    positional_parameters: tuple[Parameter, ...] = (),
    keyword_parameters: frozenset[Parameter] = frozenset(),
    var_positional: Parameter | None = None,
    var_keyword: Parameter | None = None,
    returns: str | None = None,
    is_async: bool = False,
) -> Function:
    return Function(
        name=name,
        positional_parameters=positional_parameters,
        keyword_parameters=keyword_parameters,
        var_positional=var_positional,
        var_keyword=var_keyword,
        returns=returns,
        is_async=is_async,
    )


def _make_assignment(
    name: str = "X",
    annotation: str | None = "int",
    value_repr: str | None = "42",
) -> Assignment:
    return Assignment(name=name, annotation=annotation, value_repr=value_repr)


def _make_class(
    name: str = "MyClass",
    assignments: tuple[Assignment, ...] = (),
    methods: tuple[Function, ...] = (),
    nested_classes: tuple[Class, ...] = (),
) -> Class:
    return Class(
        name=name,
        assignments=assignments,
        methods=methods,
        nested_classes=nested_classes,
    )


def _make_module(
    name: str = "my_module",
    assignments: tuple[Assignment, ...] = (),
    classes: tuple[Class, ...] = (),
    functions: tuple[Function, ...] = (),
) -> Module:
    return Module(
        name=name,
        assignments=assignments,
        classes=classes,
        functions=functions,
    )


def _make_package(
    name: str = "my_package",
    path: Path = Path("/fake/path"),
    modules: tuple[Module, ...] = (),
    subpackages: tuple[Package, ...] = (),
) -> Package:
    return Package(
        name=name,
        path=path,
        modules=modules,
        subpackages=subpackages,
    )


# ---------------------------------------------------------------------------
# 1. is_dataclass returns True for each of the six classes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", ALL_CLASSES)
def test_is_dataclass(cls: type) -> None:
    assert dataclasses.is_dataclass(cls) is True


# ---------------------------------------------------------------------------
# 2. FrozenInstanceError is raised on field assignment
# ---------------------------------------------------------------------------


def test_parameter_frozen() -> None:
    p = _make_parameter()
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.name = "y"  # type: ignore[misc]


def test_function_frozen() -> None:
    f = _make_function()
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.name = "g"  # type: ignore[misc]


def test_assignment_frozen() -> None:
    a = _make_assignment()
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.name = "Z"  # type: ignore[misc]


def test_class_frozen() -> None:
    c = _make_class()
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.name = "Other"  # type: ignore[misc]


def test_module_frozen() -> None:
    m = _make_module()
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.name = "other_module"  # type: ignore[misc]


def test_package_frozen() -> None:
    pkg = _make_package()
    with pytest.raises(dataclasses.FrozenInstanceError):
        pkg.name = "other_package"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 3. Each class has a non-empty __slots__
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", ALL_CLASSES)
def test_has_nonempty_slots(cls: type) -> None:
    assert hasattr(cls, "__slots__")
    assert len(cls.__slots__) > 0


# ---------------------------------------------------------------------------
# 4. Function can be constructed with all parameter kinds
# ---------------------------------------------------------------------------


def test_function_all_parameter_kinds() -> None:
    pos_only = _make_parameter(name="pos_only", annotation="int")
    pos_or_kw = _make_parameter(name="pos_or_kw", annotation="str")
    kw_only = _make_parameter(name="kw_only", annotation="float", default="0.0")
    var_pos = Parameter(name="args", annotation=None, default=None)
    var_kw = Parameter(name="kwargs", annotation=None, default=None)

    f = Function(
        name="full_function",
        positional_parameters=(pos_only, pos_or_kw),
        keyword_parameters=frozenset({kw_only}),
        var_positional=var_pos,
        var_keyword=var_kw,
        returns="None",
        is_async=True,
    )

    assert f.name == "full_function"
    assert f.positional_parameters == (pos_only, pos_or_kw)
    assert kw_only in f.keyword_parameters
    assert f.var_positional == var_pos
    assert f.var_keyword == var_kw
    assert f.returns == "None"
    assert f.is_async is True


# ---------------------------------------------------------------------------
# 5. Two Functions with keyword parameters in different order compare equal
# ---------------------------------------------------------------------------


def test_function_keyword_order_independent_equality() -> None:
    kw_a = _make_parameter(name="alpha", annotation="int")
    kw_b = _make_parameter(name="beta", annotation="str")

    f1 = _make_function(keyword_parameters=frozenset({kw_a, kw_b}))
    f2 = _make_function(keyword_parameters=frozenset({kw_b, kw_a}))

    assert f1 == f2


# ---------------------------------------------------------------------------
# 6. Two Functions with positional parameters in different order compare unequal
# ---------------------------------------------------------------------------


def test_function_positional_order_sensitive_equality() -> None:
    p1 = _make_parameter(name="first", annotation="int")
    p2 = _make_parameter(name="second", annotation="str")

    f_ab = _make_function(positional_parameters=(p1, p2))
    f_ba = _make_function(positional_parameters=(p2, p1))

    assert f_ab != f_ba


# ---------------------------------------------------------------------------
# 7. Parameter instances are hashable
# ---------------------------------------------------------------------------


def test_parameter_hashable_in_set() -> None:
    p1 = _make_parameter(name="a", annotation="int")
    p2 = _make_parameter(name="b", annotation="str", default="'hello'")
    p3 = _make_parameter(name="a", annotation="int")  # duplicate of p1

    s: set[Parameter] = {p1, p2, p3}
    assert len(s) == 2


def test_parameter_hashable_in_frozenset() -> None:
    p1 = _make_parameter(name="x", annotation="int")
    p2 = _make_parameter(name="y", annotation="str")

    fs: frozenset[Parameter] = frozenset({p1, p2})
    assert p1 in fs
    assert p2 in fs
