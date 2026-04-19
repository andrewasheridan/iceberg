"""Tests for the AST visitor module sheridan.iceberg._visitor."""

import pytest

from sheridan.iceberg._exceptions import ParseError
from sheridan.iceberg._models import Assignment, Class, Function, Module
from sheridan.iceberg._visitor import visit_module

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _visit(source: str, name: str = "mymodule") -> Module:
    return visit_module(source, name)


# ---------------------------------------------------------------------------
# Scenario 1: __all__ filters public names
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Scenario 2: Private name in __all__ is still exposed
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Scenario 3: No __all__ — underscore names excluded, public ones included
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Scenario 4: Function with every parameter kind
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Scenario 5: async def produces Function.is_async is True
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Scenario 6: Class with nested class plus method; no bases/decorators/docstring
# ---------------------------------------------------------------------------


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


def test_class_model_has_no_bases_attribute() -> None:
    source = """
class MyClass:
    pass
"""
    module = _visit(source)
    cls = module.classes[0]
    assert not hasattr(cls, "bases")


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


# ---------------------------------------------------------------------------
# Scenario 7: Decorator on a function is ignored
# ---------------------------------------------------------------------------


def test_decorated_function_same_as_undecorated() -> None:
    source_decorated = """
class MyClass:
    @staticmethod
    def helper(x: int) -> str:
        pass
"""
    source_plain = """
class MyClass:
    def helper(x: int) -> str:
        pass
"""
    mod_decorated = _visit(source_decorated)
    mod_plain = _visit(source_plain)

    fn_decorated: Function = mod_decorated.classes[0].methods[0]
    fn_plain: Function = mod_plain.classes[0].methods[0]

    assert fn_decorated == fn_plain


def test_module_level_decorated_function_same_as_undecorated() -> None:
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
    mod_decorated = _visit(source_decorated)
    mod_plain = _visit(source_plain)

    assert mod_decorated.functions[0] == mod_plain.functions[0]


# ---------------------------------------------------------------------------
# Scenario 8: Module-level annotated assignment captures annotation
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Scenario 9: Non-simple assignment target is dropped
# ---------------------------------------------------------------------------


def test_tuple_unpacking_dropped() -> None:
    source = """
a, b = 1, 2
"""
    module = _visit(source)
    assert len(module.assignments) == 0


def test_attribute_assignment_dropped() -> None:
    source = """
obj.attr = 42
"""
    module = _visit(source)
    assert len(module.assignments) == 0


def test_mixed_assignments_drops_non_simple() -> None:
    source = """
GOOD: int = 1
a, b = 2, 3
"""
    module = _visit(source)
    names = {a.name for a in module.assignments}
    assert names == {"GOOD"}


# ---------------------------------------------------------------------------
# Scenario 10: PEP 695 type alias captured as Assignment with TypeAlias annotation
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Scenario 11: Syntax error source raises ParseError
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Module name is preserved
# ---------------------------------------------------------------------------


def test_module_dotted_name_preserved() -> None:
    source = ""
    module = _visit(source, name="my_pkg.sub.core")
    assert module.name == "my_pkg.sub.core"


# ---------------------------------------------------------------------------
# Scenario 12: Class body privacy filtering
# ---------------------------------------------------------------------------


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
