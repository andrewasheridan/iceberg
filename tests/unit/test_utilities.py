"""Unit tests for sheridan.iceberg.utilities.get_function."""

import ast
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


# ---------------------------------------------------------------------------
# get_package — invalid path
# ---------------------------------------------------------------------------


def test_get_package_nonexistent_path_raises_invalid_path_error() -> None:
    with pytest.raises((InvalidPathError, FileNotFoundError, OSError)):
        get_package(Path("/nonexistent/path/to/pkg"))
