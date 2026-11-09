"""Tests for the AST visitor module sheridan.iceberg._visitor."""

import dataclasses
from pathlib import Path

import pytest

from sheridan.iceberg._exceptions import ParseError
from sheridan.iceberg._models import Assignment, Class, Function, Module, Parameter, Reference
from sheridan.iceberg._visitor import visit_module


def _visit(source: str, name: str = "mymodule") -> Module:
    return visit_module(source, name)


def test_all_filters_out_non_listed_function() -> None:
    source = """
__all__ = ["a"]

def a():
    pass

def b():
    pass
"""
    module = _visit(source)
    names = {f.name for f in module.functions}
    assert "a" in names
    assert "b" not in names


def test_all_filters_out_non_listed_assignment() -> None:
    source = """
__all__ = ["x"]
x: int = 1
y: int = 2
"""
    module = _visit(source)
    names = {a.name for a in module.assignments}
    assert "x" in names
    assert "y" not in names


def test_private_name_in_all_is_exposed() -> None:
    source = """
__all__ = ["_helper"]

def _helper():
    pass

def public():
    pass
"""
    module = _visit(source)
    names = {f.name for f in module.functions}
    assert "_helper" in names
    assert "public" not in names


def test_no_all_excludes_underscore_functions() -> None:
    source = """
def public_fn():
    pass

def _private_fn():
    pass
"""
    module = _visit(source)
    names = {f.name for f in module.functions}
    assert "public_fn" in names
    assert "_private_fn" not in names


def test_no_all_excludes_underscore_classes() -> None:
    source = """
class PublicClass:
    pass

class _PrivateClass:
    pass
"""
    module = _visit(source)
    names = {c.name for c in module.classes}
    assert "PublicClass" in names
    assert "_PrivateClass" not in names


def test_no_all_excludes_underscore_assignments() -> None:
    source = """
X: int = 1
_Y: int = 2
"""
    module = _visit(source)
    names = {a.name for a in module.assignments}
    assert "X" in names
    assert "_Y" not in names


def test_function_all_parameter_kinds() -> None:
    source = """
def full(pos_only: int, /, pos_or_kw: str, *args: float, kw_only: bool = True, **kwargs: bytes) -> None:
    pass
"""
    module = _visit(source)
    assert len(module.functions) == 1
    fn: Function = module.functions[0]

    # positional_parameters covers posonly + pos_or_kw (ordered tuple)
    pos_names = tuple(p.name for p in fn.positional_parameters)
    assert pos_names == ("pos_only", "pos_or_kw")

    pos_annotations = tuple(p.annotation for p in fn.positional_parameters)
    assert pos_annotations == ("int", "str")

    # keyword_parameters is a frozenset
    kw_names = {p.name for p in fn.keyword_parameters}
    assert kw_names == {"kw_only"}
    (kw_param,) = fn.keyword_parameters
    assert kw_param.default == "True"
    assert kw_param.annotation == "bool"

    # var_positional
    assert fn.var_positional is not None
    assert fn.var_positional.name == "args"
    assert fn.var_positional.annotation == "float"
    assert fn.var_positional.default is None

    # var_keyword
    assert fn.var_keyword is not None
    assert fn.var_keyword.name == "kwargs"
    assert fn.var_keyword.annotation == "bytes"
    assert fn.var_keyword.default is None

    assert fn.returns == "None"


def test_function_default_values_captured() -> None:
    source = """
def greet(name: str = "world", count: int = 3) -> str:
    pass
"""
    module = _visit(source)
    fn = module.functions[0]
    defaults = {p.name: p.default for p in fn.positional_parameters}
    assert defaults["name"] == "'world'"
    assert defaults["count"] == "3"


@pytest.mark.parametrize(
    ("default_source", "expected"),
    [
        ("-1", "-1"),
        ("foo()", "foo()"),
        ("[1, 2]", "[1, 2]"),
        ("{'a': 1}", "{'a': 1}"),
        ("lambda v: v", "lambda v: v"),
        ("f'{x}!'", "f'{x}!'"),
    ],
    ids=["unary-minus", "call", "list", "dict", "lambda", "f-string"],
)
def test_function_complex_default_values_captured(default_source: str, expected: str) -> None:
    source = f"""
def fn(a={default_source}, *, b={default_source}):
    pass
"""
    module = _visit(source)
    fn = module.functions[0]
    (positional,) = fn.positional_parameters
    (keyword,) = fn.keyword_parameters
    assert positional.default == expected
    assert keyword.default == expected


def test_function_long_default_is_shortened_but_present() -> None:
    long_list = "[" + ", ".join(str(i) for i in range(100)) + "]"
    source = f"""
def fn(a={long_list}):
    pass
"""
    module = _visit(source)
    (param,) = module.functions[0].positional_parameters
    assert param.default == "..."


def test_function_no_params() -> None:
    source = """
def nothing() -> None:
    pass
"""
    module = _visit(source)
    fn = module.functions[0]
    assert fn.positional_parameters == ()
    assert fn.keyword_parameters == frozenset()
    assert fn.var_positional is None
    assert fn.var_keyword is None
    assert fn.returns == "None"


def test_function_kw_only_without_default() -> None:
    source = """
def fn(*, required: str) -> None:
    pass
"""
    module = _visit(source)
    fn = module.functions[0]
    (kw,) = fn.keyword_parameters
    assert kw.name == "required"
    assert kw.default is None


def test_async_function_is_async_true() -> None:
    source = """
async def fetch(url: str) -> bytes:
    pass
"""
    module = _visit(source)
    assert len(module.functions) == 1
    assert module.functions[0].is_async is True


def test_sync_function_is_async_false() -> None:
    source = """
def compute(x: int) -> int:
    pass
"""
    module = _visit(source)
    assert module.functions[0].is_async is False


def test_class_with_nested_class_and_method() -> None:
    source = """
class Outer:
    def method(self) -> None:
        pass

    class Inner:
        def inner_method(self) -> int:
            pass
"""
    module = _visit(source)
    assert len(module.classes) == 1
    outer: Class = module.classes[0]
    assert outer.name == "Outer"

    method_names = {m.name for m in outer.methods}
    assert "method" in method_names

    assert len(outer.nested_classes) == 1
    inner: Class = outer.nested_classes[0]
    assert inner.name == "Inner"
    inner_method_names = {m.name for m in inner.methods}
    assert "inner_method" in inner_method_names


def test_class_without_bases_has_empty_bases_and_keywords() -> None:
    source = """
class MyClass:
    pass
"""
    cls = _visit(source).classes[0]
    assert cls.bases == ()
    assert cls.keywords == ()


def test_class_bases_are_captured_as_source_in_order() -> None:
    source = """
class MyClass(errors.IcebergError, Generic[T], *mixins):
    pass
"""
    cls = _visit(source).classes[0]
    assert cls.bases == ("errors.IcebergError", "Generic[T]", "*mixins")


def test_class_keywords_are_captured_as_source_in_order() -> None:
    source = """
class MyClass(Base, metaclass=ABCMeta, total=False, **options):
    pass
"""
    cls = _visit(source).classes[0]
    assert cls.bases == ("Base",)
    assert cls.keywords == ("metaclass=ABCMeta", "total=False", "**options")


def test_nested_class_bases_are_captured() -> None:
    source = """
class Outer:
    class Inner(Enum):
        A = 1
"""
    inner = _visit(source).classes[0].nested_classes[0]
    assert inner.bases == ("Enum",)


def test_class_model_has_no_decorators_attribute() -> None:
    source = """
class MyClass:
    pass
"""
    module = _visit(source)
    cls = module.classes[0]
    assert not hasattr(cls, "decorators")


def test_class_model_has_no_docstring_attribute() -> None:
    source = """
class MyClass:
    pass
"""
    module = _visit(source)
    cls = module.classes[0]
    assert not hasattr(cls, "docstring")


def test_staticmethod_has_staticmethod_kind() -> None:
    source = """
class MyClass:
    @staticmethod
    def helper(x: int) -> str:
        pass
"""
    fn: Function = _visit(source).classes[0].methods[0]

    assert fn.kind == "staticmethod"
    assert fn.decorators == ("staticmethod",)
    assert [p.name for p in fn.positional_parameters] == ["x"]


def test_plain_method_has_method_kind() -> None:
    source = """
class MyClass:
    def helper(self, x: int) -> str:
        pass
"""
    fn: Function = _visit(source).classes[0].methods[0]

    assert fn.kind == "method"
    assert fn.decorators == ()


def test_classmethod_has_classmethod_kind() -> None:
    source = """
class MyClass:
    @classmethod
    def build(cls) -> "MyClass":
        pass
"""
    assert _visit(source).classes[0].methods[0].kind == "classmethod"


def test_property_has_property_kind() -> None:
    source = """
import functools

class MyClass:
    @property
    def p(self) -> int:
        pass

    @functools.cached_property
    def q(self) -> str:
        pass
"""
    methods = _visit(source).classes[0].methods

    assert [(m.name, m.kind) for m in methods] == [("p", "property"), ("q", "property")]
    assert methods[1].decorators == ("functools.cached_property",)


def test_property_setter_and_deleter_are_not_duplicated() -> None:
    source = """
class MyClass:
    @property
    def p(self) -> int:
        pass

    @p.setter
    def p(self, value: int) -> None:
        pass

    @p.deleter
    def p(self) -> None:
        pass
"""
    methods = _visit(source).classes[0].methods

    assert [(m.name, m.kind) for m in methods] == [("p", "property")]


def test_abstractmethod_is_kept_in_decorators() -> None:
    source = """
import abc

class Base(abc.ABC):
    @property
    @abc.abstractmethod
    def p(self) -> int:
        pass

    @abc.abstractmethod
    def run(self) -> None:
        pass
"""
    methods = _visit(source).classes[0].methods

    assert [(m.kind, m.decorators) for m in methods] == [
        ("property", ("property", "abc.abstractmethod")),
        ("method", ("abc.abstractmethod",)),
    ]


def test_called_decorator_does_not_change_method_kind() -> None:
    source = """
import functools

class MyClass:
    @functools.lru_cache(maxsize=None)
    def compute(self, n: int) -> int:
        pass
"""
    fn: Function = _visit(source).classes[0].methods[0]

    assert fn.kind == "method"
    assert fn.decorators == ("functools.lru_cache(maxsize=None)",)


def test_module_level_decorated_function_has_function_kind() -> None:
    source_decorated = """
import functools

@functools.lru_cache
def compute(n: int) -> int:
    pass
"""
    source_plain = """
def compute(n: int) -> int:
    pass
"""
    decorated = _visit(source_decorated).functions[0]
    plain = _visit(source_plain).functions[0]

    assert decorated.kind == "function"
    assert decorated.decorators == ("functools.lru_cache",)
    assert dataclasses.replace(decorated, decorators=()) == plain


def test_annotated_assignment_simple_literal() -> None:
    source = """
TIMEOUT: int = 30
"""
    module = _visit(source)
    assert len(module.assignments) == 1
    a: Assignment = module.assignments[0]
    assert a.name == "TIMEOUT"
    assert a.annotation == "int"


def test_annotated_assignment_string_literal() -> None:
    source = """
VERSION: str = "1.0.0"
"""
    module = _visit(source)
    a = module.assignments[0]
    assert a.name == "VERSION"
    assert a.annotation == "str"


def test_annotated_assignment_no_value() -> None:
    source = """
x: int
"""
    module = _visit(source)
    a = module.assignments[0]
    assert a.name == "x"
    assert a.annotation == "int"


def test_plain_assignment_no_annotation() -> None:
    source = """
LIMIT = 100
"""
    module = _visit(source)
    a = module.assignments[0]
    assert a.name == "LIMIT"
    assert a.annotation is None


def test_chained_assignment_captures_every_name() -> None:
    module = _visit("a = b = 1\n")
    assert [a.name for a in module.assignments] == ["a", "b"]
    assert all(a.annotation is None for a in module.assignments)


def test_tuple_unpacking_captures_every_name() -> None:
    module = _visit("a, b = 1, 2\n")
    assert [a.name for a in module.assignments] == ["a", "b"]


def test_starred_unpacking_captures_every_name() -> None:
    module = _visit("c, *rest = [1, 2, 3]\n")
    assert [a.name for a in module.assignments] == ["c", "rest"]


def test_nested_list_unpacking_captures_every_name() -> None:
    module = _visit("[x, (y, z)] = 1, (2, 3)\n")
    assert [a.name for a in module.assignments] == ["x", "y", "z"]


def test_unpacking_skips_private_names_without_all() -> None:
    module = _visit("a, _b = 1, 2\n")
    assert [a.name for a in module.assignments] == ["a"]


def test_unpacking_skips_attribute_and_subscript_targets() -> None:
    module = _visit("a, obj.attr, d[0] = 1, 2, 3\n")
    assert [a.name for a in module.assignments] == ["a"]


def test_unpacked_name_in_all_is_definition_not_reference() -> None:
    source = """
__all__ = ["a", "b", "c", "rest"]
a = b = 1
c, *rest = 1, 2, 3
"""
    module = _visit(source)
    assert {a.name for a in module.assignments} == {"a", "b", "c", "rest"}
    assert module.references == ()


def test_class_body_chained_and_unpacked_assignments() -> None:
    source = """
class MyClass:
    a = b = 1
    c, *rest = 1, 2, 3
    d, _e = 4, 5
"""
    module = _visit(source)
    names = [a.name for a in module.classes[0].assignments]
    assert names == ["a", "b", "c", "rest", "d"]


def test_attribute_assignment_dropped() -> None:
    source = """
obj.attr = 42
"""
    module = _visit(source)
    assert len(module.assignments) == 0


def test_type_alias_pep695() -> None:
    source = "type X = int\n"
    module = _visit(source)
    assert len(module.assignments) == 1
    a: Assignment = module.assignments[0]
    assert a.name == "X"
    assert a.annotation == "TypeAlias"


def test_type_alias_pep695_complex_rhs() -> None:
    source = "type Vector = list[float]\n"
    module = _visit(source)
    a = module.assignments[0]
    assert a.name == "Vector"
    assert a.annotation == "TypeAlias"


def test_type_alias_pep695_private_excluded_without_all() -> None:
    source = "type _Internal = int\n"
    module = _visit(source)
    assert len(module.assignments) == 0


def test_type_alias_pep695_in_all() -> None:
    source = """
__all__ = ["MyAlias"]
type MyAlias = str
"""
    module = _visit(source)
    assert len(module.assignments) == 1
    assert module.assignments[0].name == "MyAlias"


def test_syntax_error_raises_parse_error() -> None:
    source = "def broken(:"
    with pytest.raises(ParseError):
        _visit(source)


def test_syntax_error_is_iceberg_error() -> None:
    from sheridan.iceberg._exceptions import IcebergError

    source = "class :"
    with pytest.raises(IcebergError):
        _visit(source)


def test_syntax_error_not_swallowed() -> None:
    source = "x = (1 + "
    with pytest.raises(ParseError):
        _visit(source)


def test_module_dotted_name_preserved() -> None:
    source = ""
    module = _visit(source, name="my_pkg.sub.core")
    assert module.name == "my_pkg.sub.core"


def test_class_private_method_excluded() -> None:
    """A method whose name starts with ``_`` (but is not a dunder) is excluded."""
    source = """
class MyClass:
    def public_method(self) -> None:
        pass

    def _helper(self) -> int:
        pass
"""
    module = _visit(source)
    cls: Class = module.classes[0]
    method_names = {m.name for m in cls.methods}
    assert "public_method" in method_names
    assert "_helper" not in method_names


def test_class_private_attribute_excluded() -> None:
    """An annotated class attribute whose name starts with ``_`` is excluded."""
    source = """
class MyClass:
    count: int = 0
    _count: int = 0
"""
    module = _visit(source)
    cls: Class = module.classes[0]
    assignment_names = {a.name for a in cls.assignments}
    assert "count" in assignment_names
    assert "_count" not in assignment_names


def test_class_private_nested_class_excluded() -> None:
    """A nested class whose name starts with ``_`` is excluded."""
    source = """
class Outer:
    class PublicInner:
        pass

    class _Inner:
        pass
"""
    module = _visit(source)
    cls: Class = module.classes[0]
    nested_names = {nc.name for nc in cls.nested_classes}
    assert "PublicInner" in nested_names
    assert "_Inner" not in nested_names


def test_class_dunder_method_included() -> None:
    """Dunder methods like ``__init__`` are treated as public and included."""
    source = """
class MyClass:
    def __init__(self, value: int) -> None:
        pass

    def _private(self) -> None:
        pass
"""
    module = _visit(source)
    cls: Class = module.classes[0]
    method_names = {m.name for m in cls.methods}
    assert "__init__" in method_names
    assert "_private" not in method_names


def test_class_dunder_methods_are_public_but_private_and_mangled_are_not() -> None:
    """``__call__`` and ``__eq__`` are public; ``_x`` and mangled ``__x`` are private."""
    source = """
class MyClass:
    def __call__(self) -> None:
        pass

    def __eq__(self, other: object) -> bool:
        pass

    def __x(self) -> None:
        pass

    def _x(self) -> None:
        pass
"""
    module = _visit(source)
    cls: Class = module.classes[0]
    assert [m.name for m in cls.methods] == ["__call__", "__eq__"]


def test_class_dunder_attributes_are_public_but_private_and_mangled_are_not() -> None:
    """Class attributes of the form ``__x__`` are public; ``_x`` and ``__x`` are private."""
    source = """
class MyClass:
    __slots__ = ("a",)
    __match_args__: tuple[str, ...] = ("a",)
    __x = 1
    _x = 2
"""
    module = _visit(source)
    cls: Class = module.classes[0]
    assert [a.name for a in cls.assignments] == ["__slots__", "__match_args__"]


def test_class_mixed_members_all_filtered_correctly() -> None:
    """All three member kinds are filtered in a single class definition."""
    source = """
class Service:
    timeout: int = 30
    _cache: dict = {}

    def run(self) -> None:
        pass

    def _setup(self) -> None:
        pass

    class Config:
        pass

    class _State:
        pass
"""
    module = _visit(source)
    cls: Class = module.classes[0]

    assignment_names = {a.name for a in cls.assignments}
    assert "timeout" in assignment_names
    assert "_cache" not in assignment_names

    method_names = {m.name for m in cls.methods}
    assert "run" in method_names
    assert "_setup" not in method_names

    nested_names = {nc.name for nc in cls.nested_classes}
    assert "Config" in nested_names
    assert "_State" not in nested_names


def test_all_reexport_of_import_becomes_reference() -> None:
    source = """
from math import sqrt
from ._impl import helper

__all__ = ["sqrt", "helper", "local"]

def local():
    pass
"""
    module = visit_module(source, "pkg.mod")
    assert [f.name for f in module.functions] == ["local"]
    assert module.references == (
        Reference(name="helper", module="pkg._impl", attribute="helper"),
        Reference(name="sqrt", module="math", attribute="sqrt"),
    )


def test_all_unbound_name_becomes_reference_without_source() -> None:
    module = _visit('__all__ = ["ghost"]')
    assert module.references == (Reference(name="ghost", module=None, attribute=None),)


def test_no_all_means_no_references() -> None:
    module = _visit("from math import sqrt\n\ndef f():\n    pass\n")
    assert module.references == ()


def test_type_checking_block_definitions_captured() -> None:
    source = """
from typing import TYPE_CHECKING

__all__ = ["Alias", "Proto", "helper"]

if TYPE_CHECKING:
    Alias = int

    class Proto:
        pass

    def helper() -> None:
        pass
"""
    module = _visit(source)
    assert [a.name for a in module.assignments] == ["Alias"]
    assert [c.name for c in module.classes] == ["Proto"]
    assert [f.name for f in module.functions] == ["helper"]
    assert module.references == ()


def test_version_check_branches_without_all_keep_first_definition() -> None:
    source = """
import sys

if sys.version_info >= (3, 12):
    def compat(x: int) -> int:
        return x
    LIMIT: int = 1
else:
    def compat(x):
        return x
    LIMIT = 2
"""
    module = _visit(source)
    assert module.functions == (
        Function(
            name="compat",
            positional_parameters=(Parameter(name="x", annotation="int", default=None),),
            keyword_parameters=frozenset(),
            var_positional=None,
            var_keyword=None,
            returns="int",
            is_async=False,
        ),
    )
    assert module.assignments == (Assignment(name="LIMIT", annotation="int"),)


def test_try_except_fallback_definition_captured() -> None:
    source = """
__all__ = ["fast", "Thing"]

try:
    from ._speedups import fast
except ImportError:
    def fast():
        pass
finally:
    class Thing:
        pass
"""
    module = visit_module(source, "pkg.mod")
    assert [f.name for f in module.functions] == ["fast"]
    assert [c.name for c in module.classes] == ["Thing"]
    assert module.references == ()


def test_try_except_fallback_without_all_is_captured() -> None:
    source = """
try:
    import tomllib as toml_reader
except ImportError:
    toml_reader = None
else:
    VERSION = 1
"""
    module = _visit(source)
    assert [a.name for a in module.assignments] == ["toml_reader", "VERSION"]


def test_private_definitions_in_if_block_excluded_without_all() -> None:
    module = _visit("if True:\n    def _hidden():\n        pass\n    def shown():\n        pass\n")
    assert [f.name for f in module.functions] == ["shown"]


def test_definitions_inside_functions_not_captured() -> None:
    module = _visit("def outer():\n    if True:\n        def inner():\n            pass\n")
    assert [f.name for f in module.functions] == ["outer"]


def test_class_body_if_else_branches_keep_first_definition() -> None:
    source = """
import sys

class A:
    if sys.version_info >= (3, 12):
        def y(self) -> int: ...
        LIMIT: int = 1
        class Inner:
            pass
    else:
        def y(self) -> str: ...
        LIMIT = 2
        class Inner:
            x = 1
"""
    (cls,) = _visit(source).classes
    assert [(m.name, m.returns) for m in cls.methods] == [("y", "int")]
    assert cls.assignments == (Assignment(name="LIMIT", annotation="int"),)
    assert cls.nested_classes == (
        Class(name="Inner", bases=(), keywords=(), assignments=(), methods=(), nested_classes=()),
    )


def test_class_body_try_except_definitions_captured() -> None:
    source = """
class A:
    try:
        import numpy
        def to_array(self): ...
    except ImportError:
        HAS_NUMPY = False
        class Fallback:
            pass
    else:
        HAS_NUMPY = True
"""
    (cls,) = _visit(source).classes
    assert [m.name for m in cls.methods] == ["to_array"]
    assert cls.assignments == (Assignment(name="HAS_NUMPY", annotation=None),)
    assert [c.name for c in cls.nested_classes] == ["Fallback"]


def test_class_body_private_definitions_in_if_block_excluded() -> None:
    module = _visit("class A:\n    if True:\n        def _hidden(self): ...\n        def shown(self): ...\n")
    assert [m.name for m in module.classes[0].methods] == ["shown"]


def test_class_body_overloads_in_branch_group_with_later_implementation() -> None:
    source = """
from typing import TYPE_CHECKING, overload

class C:
    if TYPE_CHECKING:
        @overload
        def f(self, x: int) -> int: ...
        @overload
        def f(self, x: str) -> str: ...
    def f(self, x): ...
"""
    (method,) = _visit(source).classes[0].methods
    assert method.name == "f"
    assert [o.returns for o in method.overloads] == ["int", "str"]


def test_syntax_error_reports_path_line_and_column() -> None:
    with pytest.raises(ParseError) as info:
        visit_module("x = 1\ndef f(:\n", "pkg.mod", Path("src/pkg/mod.py"))
    assert info.value.path == "src/pkg/mod.py"
    assert info.value.lineno == 2
    assert info.value.offset is not None
    assert str(info.value).startswith(f"src/pkg/mod.py:2:{info.value.offset}: ")


def test_syntax_error_without_path_has_no_path() -> None:
    with pytest.raises(ParseError) as info:
        visit_module("def f(:\n", "pkg.mod")
    assert info.value.path is None
    assert info.value.lineno == 1


def test_star_import_from_module_with_known_all_binds_its_names() -> None:
    source = 'from ._c import *\nfrom os import *\n__all__ = ["X", "ghost"]\n'
    known_all: dict[str, frozenset[str] | None] = {"pkg._c": frozenset({"X"})}
    module = visit_module(source, "pkg.mod", known_all=known_all)
    assert module.references == (
        Reference(name="X", module="pkg._c", attribute="X"),
        Reference(name="ghost", module="os", attribute="ghost"),
    )


def test_star_import_from_unknown_module_is_candidate() -> None:
    module = visit_module('from os.path import *\n__all__ = ["join"]\n', "pkg.mod")
    assert module.references == (Reference(name="join", module="os.path", attribute="join"),)


def test_module_level_overloads_are_grouped_into_the_implementation() -> None:
    source = """
from typing import overload

@overload
def f(x: int) -> int: ...
@overload
def f(x: str) -> str: ...
def f(x):
    return x
"""
    module = _visit(source)

    assert [fn.name for fn in module.functions] == ["f"]
    (f,) = module.functions
    assert f.decorators == ()
    assert f.returns is None
    assert [o.returns for o in f.overloads] == ["int", "str"]
    assert all(o.decorators == ("overload",) and o.overloads == () for o in f.overloads)
    assert all(o.kind == "function" for o in f.overloads)


def test_method_overloads_are_grouped_and_keep_their_kind() -> None:
    source = """
import typing

class C:
    @typing.overload
    def m(self, x: int) -> int: ...
    @typing.overload
    def m(self, x: str) -> str: ...
    def m(self, x):
        return x

    @typing.overload
    @classmethod
    def k(cls, x: int) -> int: ...
    @typing.overload
    @classmethod
    def k(cls, x: str) -> str: ...
    @classmethod
    def k(cls, x):
        return x
"""
    (cls,) = _visit(source).classes

    assert [fn.name for fn in cls.methods] == ["m", "k"]
    m, k = cls.methods
    assert [o.returns for o in m.overloads] == ["int", "str"]
    assert {o.kind for o in m.overloads} == {"method"}
    assert k.kind == "classmethod"
    assert {o.kind for o in k.overloads} == {"classmethod"}


def test_overloads_without_implementation_are_one_function() -> None:
    source = """
from typing import overload

class C:
    @overload
    def m(self, x: int) -> int: ...
    @overload
    def m(self, x: str) -> str: ...
"""
    (cls,) = _visit(source).classes

    (m,) = cls.methods
    assert m.returns == "str"
    assert [o.returns for o in m.overloads] == ["int", "str"]


def test_overloads_in_type_checking_block_group_with_later_implementation() -> None:
    source = """
from typing import TYPE_CHECKING, overload

if TYPE_CHECKING:
    @overload
    def f(x: int) -> int: ...
    @overload
    def f(x: str) -> str: ...

def f(x):
    return x
"""
    (f,) = _visit(source).functions

    assert f.returns is None
    assert len(f.overloads) == 2


def test_function_without_overloads_has_empty_overloads() -> None:
    (f,) = _visit("def f(x: int) -> int: ...").functions

    assert f.overloads == ()
