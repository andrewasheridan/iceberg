"""Unit tests for sheridan.iceberg.utilities.get_function."""

import ast
import importlib
import sys
import types
from pathlib import Path

import pytest

from sheridan.iceberg._exceptions import InvalidPathError, ParseError
from sheridan.iceberg._models import Assignment, Class, Function, Module, Package, Parameter
from sheridan.iceberg.utilities import get_assignment, get_class, get_function, get_module, get_package

# ---------------------------------------------------------------------------
# str overload
# ---------------------------------------------------------------------------


def test_str_simple_function_name() -> None:
    result: Function = get_function("def foo(x: int) -> str:\n    ...")
    assert result.name == "foo"


def test_str_simple_function_positional_param() -> None:
    result: Function = get_function("def foo(x: int) -> str:\n    ...")
    assert len(result.positional_parameters) == 1
    param: Parameter = result.positional_parameters[0]
    assert param.name == "x"
    assert param.annotation == "int"


def test_str_simple_function_return_type() -> None:
    result: Function = get_function("def foo(x: int) -> str:\n    ...")
    assert result.returns == "str"


def test_str_simple_function_not_async() -> None:
    result: Function = get_function("def foo(x: int) -> str:\n    ...")
    assert result.is_async is False


def test_str_async_function_name() -> None:
    result: Function = get_function("async def bar() -> None:\n    ...")
    assert result.name == "bar"


def test_str_async_function_is_async() -> None:
    result: Function = get_function("async def bar() -> None:\n    ...")
    assert result.is_async is True


def test_str_syntax_error_raises_parse_error() -> None:
    with pytest.raises(ParseError):
        get_function("def (")


def test_str_no_function_raises_parse_error() -> None:
    with pytest.raises(ParseError):
        get_function("x = 1")


# ---------------------------------------------------------------------------
# AST node overload
# ---------------------------------------------------------------------------


def test_ast_functiondef_name() -> None:
    tree = ast.parse("def baz(a, b): pass")
    node = tree.body[0]
    assert isinstance(node, ast.FunctionDef)
    result: Function = get_function(node)
    assert result.name == "baz"


def test_ast_functiondef_two_positional_params() -> None:
    tree = ast.parse("def baz(a, b): pass")
    node = tree.body[0]
    assert isinstance(node, ast.FunctionDef)
    result: Function = get_function(node)
    assert len(result.positional_parameters) == 2
    assert result.positional_parameters[0].name == "a"
    assert result.positional_parameters[1].name == "b"


def test_ast_asyncfunctiondef_name() -> None:
    tree = ast.parse("async def qux(a, b): pass")
    node = tree.body[0]
    assert isinstance(node, ast.AsyncFunctionDef)
    result: Function = get_function(node)
    assert result.name == "qux"


def test_ast_asyncfunctiondef_is_async() -> None:
    tree = ast.parse("async def qux(a, b): pass")
    node = tree.body[0]
    assert isinstance(node, ast.AsyncFunctionDef)
    result: Function = get_function(node)
    assert result.is_async is True


def test_ast_asyncfunctiondef_two_positional_params() -> None:
    tree = ast.parse("async def qux(a, b): pass")
    node = tree.body[0]
    assert isinstance(node, ast.AsyncFunctionDef)
    result: Function = get_function(node)
    assert len(result.positional_parameters) == 2


# ---------------------------------------------------------------------------
# Path overload
# ---------------------------------------------------------------------------


def test_path_function_found(tmp_path: Path) -> None:
    src = "def the_func(x: int) -> bool:\n    return True\n"
    file: Path = tmp_path / "sample.py"
    file.write_text(src, encoding="utf-8")
    result: Function = get_function(file, name="the_func")
    assert result.name == "the_func"


def test_path_function_found_correct_param(tmp_path: Path) -> None:
    src = "def the_func(x: int) -> bool:\n    return True\n"
    file: Path = tmp_path / "sample.py"
    file.write_text(src, encoding="utf-8")
    result: Function = get_function(file, name="the_func")
    assert len(result.positional_parameters) == 1
    assert result.positional_parameters[0].name == "x"


def test_path_function_not_found_raises_invalid_path_error(tmp_path: Path) -> None:
    src = "def the_func(x: int) -> bool:\n    return True\n"
    file: Path = tmp_path / "sample.py"
    file.write_text(src, encoding="utf-8")
    with pytest.raises(InvalidPathError):
        get_function(file, name="nonexistent_func")


_SHADOWED_SRC = """\
class Runner:
    def run(self, method_arg): ...

    class Inner:
        def run(self, inner_arg): ...

if True:
    def run(top_arg): ...
"""


def test_path_top_level_function_preferred_over_method(tmp_path: Path) -> None:
    file: Path = tmp_path / "sample.py"
    file.write_text("class Runner:\n    def run(self, method_arg): ...\n\ndef run(top_arg): ...\n", encoding="utf-8")
    result: Function = get_function(file, name="run")
    assert result.positional_parameters[0].name == "top_arg"


def test_path_top_level_function_in_if_block_preferred_over_method(tmp_path: Path) -> None:
    file: Path = tmp_path / "sample.py"
    file.write_text(_SHADOWED_SRC, encoding="utf-8")
    result: Function = get_function(file, name="run")
    assert result.positional_parameters[0].name == "top_arg"


def test_path_dotted_name_selects_method(tmp_path: Path) -> None:
    file: Path = tmp_path / "sample.py"
    file.write_text(_SHADOWED_SRC, encoding="utf-8")
    result: Function = get_function(file, name="Runner.run")
    assert [p.name for p in result.positional_parameters] == ["self", "method_arg"]


def test_path_dotted_name_selects_nested_class_method(tmp_path: Path) -> None:
    file: Path = tmp_path / "sample.py"
    file.write_text(_SHADOWED_SRC, encoding="utf-8")
    result: Function = get_function(file, name="Runner.Inner.run")
    assert [p.name for p in result.positional_parameters] == ["self", "inner_arg"]


def test_path_dotted_name_not_found_raises_invalid_path_error(tmp_path: Path) -> None:
    file: Path = tmp_path / "sample.py"
    file.write_text(_SHADOWED_SRC, encoding="utf-8")
    with pytest.raises(InvalidPathError):
        get_function(file, name="Runner.missing")
    with pytest.raises(InvalidPathError):
        get_function(file, name="Missing.run")


@pytest.mark.parametrize(
    "src",
    [
        "class C:\n    def run(self, method_arg): ...\ntry:\n    pass\nexcept OSError:\n    def run(top_arg): ...\n",
        "class C:\n    def run(self, method_arg): ...\nmatch 1:\n    case _:\n        def run(top_arg): ...\n",
    ],
    ids=["except-handler", "match-case"],
)
def test_path_module_level_function_in_compound_statement_preferred(tmp_path: Path, src: str) -> None:
    file: Path = tmp_path / "sample.py"
    file.write_text(src, encoding="utf-8")
    result: Function = get_function(file, name="run")
    assert result.positional_parameters[0].name == "top_arg"


def test_path_nested_only_function_still_found(tmp_path: Path) -> None:
    file: Path = tmp_path / "sample.py"
    file.write_text("class Runner:\n    def only_method(self): ...\n", encoding="utf-8")
    result: Function = get_function(file, name="only_method")
    assert result.name == "only_method"


def test_path_missing_name_raises_type_error(tmp_path: Path) -> None:
    src = "def the_func(): pass\n"
    file: Path = tmp_path / "sample.py"
    file.write_text(src, encoding="utf-8")
    with pytest.raises(TypeError):
        get_function(file)  # type: ignore[call-overload]


# ---------------------------------------------------------------------------
# Callable overload
# ---------------------------------------------------------------------------


def _sample_callable(a: int, b: str) -> float:
    return float(a)


def test_callable_name_matches() -> None:
    result: Function = get_function(_sample_callable)
    assert result.name == _sample_callable.__name__


def test_callable_returns_function_instance() -> None:
    result: Function = get_function(_sample_callable)
    assert isinstance(result, Function)


def test_callable_positional_params() -> None:
    result: Function = get_function(_sample_callable)
    param_names = [p.name for p in result.positional_parameters]
    assert "a" in param_names
    assert "b" in param_names


def test_callable_builtin_raises_invalid_path_error() -> None:
    with pytest.raises(InvalidPathError, match="Cannot locate source"):
        get_function(len)


def test_callable_without_source_raises_invalid_path_error() -> None:
    namespace: dict[str, object] = {}
    exec("def made_at_runtime(): pass", namespace)
    with pytest.raises(InvalidPathError, match="Cannot locate source"):
        get_function(namespace["made_at_runtime"])  # type: ignore[arg-type]


def test_callable_lambda_raises_invalid_path_error() -> None:
    with pytest.raises(InvalidPathError, match="lambda"):
        get_function(lambda x: x)


# ---------------------------------------------------------------------------
# get_class — str overload
# ---------------------------------------------------------------------------


def test_get_class_str_simple_name() -> None:
    result: Class = get_class("class Foo:\n    x: int = 1")
    assert result.name == "Foo"


def test_get_class_str_no_class_raises_parse_error() -> None:
    with pytest.raises(ParseError):
        get_class("x = 1")


def test_get_class_str_syntax_error_raises_parse_error() -> None:
    with pytest.raises(ParseError):
        get_class("class (")


# ---------------------------------------------------------------------------
# get_class — AST node overload
# ---------------------------------------------------------------------------


def test_get_class_ast_node_name() -> None:
    tree = ast.parse("class Bar:\n    pass")
    node = tree.body[0]
    assert isinstance(node, ast.ClassDef)
    result: Class = get_class(node)
    assert result.name == "Bar"


# ---------------------------------------------------------------------------
# get_class — Path overload
# ---------------------------------------------------------------------------


def test_get_class_path_found(tmp_path: Path) -> None:
    src = "class MyClass:\n    pass\n"
    file: Path = tmp_path / "sample.py"
    file.write_text(src, encoding="utf-8")
    result: Class = get_class(file, name="MyClass")
    assert result.name == "MyClass"


def test_get_class_path_not_found_raises_invalid_path_error(tmp_path: Path) -> None:
    src = "class MyClass:\n    pass\n"
    file: Path = tmp_path / "sample.py"
    file.write_text(src, encoding="utf-8")
    with pytest.raises(InvalidPathError):
        get_class(file, name="NonExistent")


_NESTED_CLASS_SRC = """\
class Outer:
    class Config:
        nested: int

try:
    class Config:
        top: int
except ImportError:
    pass
"""


def test_get_class_path_top_level_preferred_over_nested(tmp_path: Path) -> None:
    file: Path = tmp_path / "sample.py"
    file.write_text(_NESTED_CLASS_SRC, encoding="utf-8")
    result: Class = get_class(file, name="Config")
    assert [a.name for a in result.assignments] == ["top"]


def test_get_class_path_dotted_name_selects_nested_class(tmp_path: Path) -> None:
    file: Path = tmp_path / "sample.py"
    file.write_text(_NESTED_CLASS_SRC, encoding="utf-8")
    result: Class = get_class(file, name="Outer.Config")
    assert [a.name for a in result.assignments] == ["nested"]


def test_get_class_path_dotted_name_not_found_raises_invalid_path_error(tmp_path: Path) -> None:
    file: Path = tmp_path / "sample.py"
    file.write_text(_NESTED_CLASS_SRC, encoding="utf-8")
    with pytest.raises(InvalidPathError):
        get_class(file, name="Outer.Missing")


def test_get_class_path_missing_name_raises_type_error(tmp_path: Path) -> None:
    src = "class MyClass:\n    pass\n"
    file: Path = tmp_path / "sample.py"
    file.write_text(src, encoding="utf-8")
    with pytest.raises(TypeError):
        get_class(file)  # type: ignore[call-overload]


# ---------------------------------------------------------------------------
# get_class — type overload
# ---------------------------------------------------------------------------


class _TestClass:
    pass


def test_get_class_type_overload_name() -> None:
    result: Class = get_class(_TestClass)
    assert result.name == "_TestClass"


def test_get_class_c_extension_type_raises_invalid_path_error() -> None:
    with pytest.raises(InvalidPathError, match="Cannot locate source"):
        get_class(int)


def test_get_class_without_source_raises_invalid_path_error() -> None:
    namespace: dict[str, object] = {}
    exec("class MadeAtRuntime: pass", namespace)
    with pytest.raises(InvalidPathError, match="Cannot locate source"):
        get_class(namespace["MadeAtRuntime"])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# get_assignment — str overload
# ---------------------------------------------------------------------------


def test_get_assignment_str_annotated_name() -> None:
    result: Assignment = get_assignment("x: int = 1")
    assert result.name == "x"


def test_get_assignment_str_annotated_annotation() -> None:
    result: Assignment = get_assignment("x: int = 1")
    assert result.annotation == "int"


def test_get_assignment_str_plain_assign_name() -> None:
    result: Assignment = get_assignment("y = 42")
    assert result.name == "y"


def test_get_assignment_str_plain_assign_no_annotation() -> None:
    result: Assignment = get_assignment("y = 42")
    assert result.annotation is None


def test_get_assignment_str_name_kwarg_selects_correct() -> None:
    source = "a = 1\nb: str = 'hi'"
    result: Assignment = get_assignment(source, name="b")
    assert result.name == "b"
    assert result.annotation == "str"


def test_get_assignment_str_name_not_found_raises_parse_error() -> None:
    source = "a = 1\nb: str = 'hi'"
    with pytest.raises(ParseError):
        get_assignment(source, name="missing")


def test_get_assignment_str_no_assignment_raises_parse_error() -> None:
    with pytest.raises(ParseError):
        get_assignment("def foo(): pass")


# ---------------------------------------------------------------------------
# get_assignment — AST node overload
# ---------------------------------------------------------------------------


def test_get_assignment_ast_ann_assign_name() -> None:
    tree = ast.parse("z: float")
    node = tree.body[0]
    assert isinstance(node, ast.AnnAssign)
    result: Assignment = get_assignment(node)
    assert result.name == "z"


def test_get_assignment_ast_ann_assign_annotation() -> None:
    tree = ast.parse("z: float")
    node = tree.body[0]
    assert isinstance(node, ast.AnnAssign)
    result: Assignment = get_assignment(node)
    assert result.annotation == "float"


def test_get_assignment_ast_type_alias_name() -> None:
    tree = ast.parse("type Alias = int")
    node = tree.body[0]
    assert isinstance(node, ast.TypeAlias)
    result: Assignment = get_assignment(node)
    assert result.name == "Alias"


def test_get_assignment_ast_type_alias_annotation() -> None:
    tree = ast.parse("type Alias = int")
    node = tree.body[0]
    assert isinstance(node, ast.TypeAlias)
    result: Assignment = get_assignment(node)
    assert result.annotation == "TypeAlias"


# ---------------------------------------------------------------------------
# get_assignment — Path overload
# ---------------------------------------------------------------------------


def test_get_assignment_path_found(tmp_path: Path) -> None:
    src = "MY_CONST: int = 99\n"
    file: Path = tmp_path / "consts.py"
    file.write_text(src, encoding="utf-8")
    result: Assignment = get_assignment(file, name="MY_CONST")
    assert result.name == "MY_CONST"
    assert result.annotation == "int"


def test_get_assignment_path_missing_name_raises_type_error(tmp_path: Path) -> None:
    src = "MY_CONST: int = 99\n"
    file: Path = tmp_path / "consts.py"
    file.write_text(src, encoding="utf-8")
    with pytest.raises(TypeError):
        get_assignment(file)  # type: ignore[call-overload]


def test_get_assignment_path_name_not_found_raises_invalid_path_error(tmp_path: Path) -> None:
    src = "MY_CONST: int = 99\n"
    file: Path = tmp_path / "consts.py"
    file.write_text(src, encoding="utf-8")
    with pytest.raises(InvalidPathError):
        get_assignment(file, name="MISSING")


# ---------------------------------------------------------------------------
# get_assignment — chained, unpacked, and if/try-block targets (#145)
# ---------------------------------------------------------------------------

_BOUND_NAMES_SRC = """\
a = b = 1
c, d = 1, 2
[f, g] = 3, 4
h, *rest = 5, 6, 7
if True:
    e = 3
try:
    t: int = 1
except ImportError:
    u = 2
"""


@pytest.mark.parametrize("name", ["a", "b", "c", "d", "f", "g", "h", "rest", "e", "t", "u"])
def test_get_assignment_str_finds_every_bound_name(name: str) -> None:
    result: Assignment = get_assignment(_BOUND_NAMES_SRC, name=name)
    assert result.name == name


@pytest.mark.parametrize("name", ["a", "b", "c", "d", "f", "g", "h", "rest", "e", "t", "u"])
def test_get_assignment_path_finds_every_bound_name(tmp_path: Path, name: str) -> None:
    file: Path = tmp_path / "u.py"
    file.write_text(_BOUND_NAMES_SRC, encoding="utf-8")
    result: Assignment = get_assignment(file, name=name)
    assert result.name == name


def test_get_assignment_path_matches_get_module(tmp_path: Path) -> None:
    file: Path = tmp_path / "u.py"
    file.write_text(_BOUND_NAMES_SRC, encoding="utf-8")
    for expected in get_module(file).assignments:
        assert get_assignment(file, name=expected.name) == expected


def test_get_assignment_str_annotated_in_try_block_keeps_annotation() -> None:
    result: Assignment = get_assignment(_BOUND_NAMES_SRC, name="t")
    assert result.annotation == "int"


_FIRST_DEFINITION_SRC = """\
try:
    x: int = 1
except ImportError:
    x: str = "1"
"""


def test_get_assignment_str_keeps_first_definition() -> None:
    assert get_assignment(_FIRST_DEFINITION_SRC, name="x").annotation == "int"


def test_get_assignment_path_keeps_first_definition(tmp_path: Path) -> None:
    file: Path = tmp_path / "u.py"
    file.write_text(_FIRST_DEFINITION_SRC, encoding="utf-8")
    assert get_assignment(file, name="x").annotation == "int"


def test_get_assignment_str_without_name_returns_first_unpacked_name() -> None:
    assert get_assignment("c, d = 1, 2").name == "c"


def test_get_assignment_str_attribute_target_not_found() -> None:
    with pytest.raises(ParseError):
        get_assignment("obj.attr = 1", name="attr")


# ---------------------------------------------------------------------------
# get_module — str overload
# ---------------------------------------------------------------------------


def test_get_module_str_default_name() -> None:
    result: Module = get_module("x = 1\ndef foo(): pass")
    assert result.name == "<module>"


def test_get_module_str_custom_name() -> None:
    result: Module = get_module("x = 1\ndef foo(): pass", name="mymod")
    assert result.name == "mymod"


def test_get_module_str_syntax_error_raises_parse_error() -> None:
    with pytest.raises(ParseError):
        get_module("def (")


# ---------------------------------------------------------------------------
# get_module — Path overload
# ---------------------------------------------------------------------------


def test_get_module_path_name_is_stem(tmp_path: Path) -> None:
    src = "x = 1\n"
    file: Path = tmp_path / "myfile.py"
    file.write_text(src, encoding="utf-8")
    result: Module = get_module(file)
    assert result.name == "myfile"


def test_get_module_path_custom_name(tmp_path: Path) -> None:
    src = "x = 1\n"
    file: Path = tmp_path / "myfile.py"
    file.write_text(src, encoding="utf-8")
    result: Module = get_module(file, name="custom")
    assert result.name == "custom"


def test_get_module_path_syntax_error_reports_file_path(tmp_path: Path) -> None:
    file: Path = tmp_path / "bad.py"
    file.write_text("def f(:\n", encoding="utf-8")
    with pytest.raises(ParseError) as info:
        get_module(file)
    assert info.value.path == str(file)
    assert str(file) in str(info.value)


def test_get_module_path_all_warning_names_file(tmp_path: Path) -> None:
    file: Path = tmp_path / "dyn.py"
    file.write_text("x = 1\n__all__ = compute()\n", encoding="utf-8")
    with pytest.warns(UserWarning, match="cannot evaluate __all__") as record:
        get_module(file)
    assert any(str(file) in str(w.message) for w in record)


# ---------------------------------------------------------------------------
# get_module — ModuleType overload
# ---------------------------------------------------------------------------


def test_get_module_module_type_returns_module() -> None:
    import textwrap

    result: Module = get_module(textwrap)
    assert isinstance(result, Module)


def test_get_module_module_type_name_contains_textwrap() -> None:
    import textwrap

    result: Module = get_module(textwrap)
    assert "textwrap" in result.name


def test_get_module_builtin_module_raises_invalid_path_error() -> None:
    with pytest.raises(InvalidPathError, match="Cannot locate source"):
        get_module(sys)


# ---------------------------------------------------------------------------
# get_package — Path overload
# ---------------------------------------------------------------------------

_ICEBERG_PKG_PATH = Path(__file__).parent.parent.parent / "src" / "sheridan" / "iceberg"


def test_get_package_path_returns_package() -> None:
    result: Package = get_package(_ICEBERG_PKG_PATH)
    assert isinstance(result, Package)


# ---------------------------------------------------------------------------
# get_package — str overload
# ---------------------------------------------------------------------------


def test_get_package_str_returns_package() -> None:
    result: Package = get_package(str(_ICEBERG_PKG_PATH))
    assert isinstance(result, Package)


# ---------------------------------------------------------------------------
# get_package — ModuleType overload
# ---------------------------------------------------------------------------


def test_get_package_module_type_returns_package() -> None:
    import sheridan.iceberg

    result: Package = get_package(sheridan.iceberg)
    assert isinstance(result, Package)


def test_get_package_plain_stdlib_module_raises_invalid_path_error() -> None:
    import textwrap

    with pytest.raises(InvalidPathError, match=r"get_module\(\)"):
        get_package(textwrap)


def _import_namespace_package(name: str, *roots: Path) -> types.ModuleType:
    for root in roots:
        (root / name).mkdir()
        (root / name / f"part_{root.name}.py").write_text("def f() -> None: ...\n")
    sys.path[:0] = [str(r) for r in roots]
    try:
        return importlib.import_module(name)
    finally:
        del sys.path[: len(roots)]
        sys.modules.pop(name, None)


def test_get_package_namespace_package_uses_dunder_path(tmp_path: Path) -> None:
    mod = _import_namespace_package("iceberg_ns_single", tmp_path)
    assert getattr(mod, "__file__", None) is None

    result: Package = get_package(mod)
    assert isinstance(result, Package)
    assert result.name == "iceberg_ns_single"


def test_get_package_namespace_package_with_many_portions_raises(tmp_path: Path) -> None:
    roots = [tmp_path / "a", tmp_path / "b"]
    for root in roots:
        root.mkdir()
    mod = _import_namespace_package("iceberg_ns_multi", *roots)

    with pytest.raises(InvalidPathError, match="2 portions"):
        get_package(mod)


# ---------------------------------------------------------------------------
# get_package — invalid path
# ---------------------------------------------------------------------------


def test_get_package_nonexistent_path_raises_invalid_path_error() -> None:
    with pytest.raises((InvalidPathError, FileNotFoundError, OSError)):
        get_package(Path("/nonexistent/path/to/pkg"))


def test_path_syntax_error_reports_file_path(tmp_path: Path) -> None:
    target = tmp_path / "mod.py"
    target.write_text("def (\n")
    with pytest.raises(ParseError) as info:
        get_function(target, name="f")
    assert info.value.path == str(target)
    assert info.value.lineno == 1
