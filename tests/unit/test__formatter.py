"""Tests for sheridan.iceberg._formatter (format_tree and format_json)."""

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from sheridan.iceberg._formatter import JSON_SCHEMA_VERSION, format_json, format_tree
from sheridan.iceberg._models import (
    Assignment,
    Class,
    Function,
    FunctionKind,
    Module,
    Package,
    Parameter,
    Reference,
)


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
    kind: FunctionKind = "function",
) -> Function:
    return Function(
        name=name,
        positional_parameters=positional_parameters,
        keyword_parameters=keyword_parameters,
        var_positional=var_positional,
        var_keyword=var_keyword,
        returns=returns,
        is_async=is_async,
        kind=kind,
    )


def _make_assignment(
    name: str = "X",
    annotation: str | None = "int",
) -> Assignment:
    return Assignment(name=name, annotation=annotation)


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


def test_format_tree_empty_package() -> None:
    """An empty package should render just its header line with no children."""
    pkg = _make_package(name="mylib")
    result = format_tree(pkg)
    assert result == "package mylib"


def test_format_tree_single_empty_module() -> None:
    """A package with one empty module renders the module as the sole child."""
    mod = _make_module(name="utils")
    pkg = _make_package(name="mylib", modules=(mod,))
    result = format_tree(pkg)
    expected = "package mylib\n└── module utils"
    assert result == expected


def test_format_tree_two_modules_branch_and_last() -> None:
    """Two modules: first gets ├── and last gets └──."""
    mod_a = _make_module(name="alpha")
    mod_b = _make_module(name="beta")
    pkg = _make_package(name="mylib", modules=(mod_a, mod_b))
    result = format_tree(pkg)
    lines = result.splitlines()
    assert lines[0] == "package mylib"
    assert lines[1] == "├── module alpha"
    assert lines[2] == "└── module beta"


def test_format_tree_module_with_assignment_annotation() -> None:
    """An annotated assignment renders as ``name: annotation``."""
    a = _make_assignment(name="VERSION", annotation="str")
    mod = _make_module(name="core", assignments=(a,))
    pkg = _make_package(name="mylib", modules=(mod,))
    result = format_tree(pkg)
    assert "VERSION: str" in result


def test_format_tree_module_with_bare_assignment() -> None:
    """An assignment with no annotation renders as just the name."""
    a = Assignment(name="SENTINEL", annotation=None)
    mod = _make_module(name="core", assignments=(a,))
    pkg = _make_package(name="mylib", modules=(mod,))
    result = format_tree(pkg)
    assert "SENTINEL" in result


def test_format_tree_function_no_params() -> None:
    """A bare function with no params renders as ``name()``."""
    fn = _make_function(name="do_thing")
    mod = _make_module(name="ops", functions=(fn,))
    pkg = _make_package(name="mylib", modules=(mod,))
    result = format_tree(pkg)
    assert "do_thing()" in result


def test_format_tree_function_with_return() -> None:
    """A function with a return annotation renders ``-> ReturnType``."""
    fn = _make_function(name="compute", returns="int")
    mod = _make_module(name="ops", functions=(fn,))
    pkg = _make_package(name="mylib", modules=(mod,))
    result = format_tree(pkg)
    assert "compute() -> int" in result


def test_format_tree_async_function() -> None:
    """An async function is prefixed with ``async def``."""
    fn = _make_function(name="fetch", is_async=True, returns="str")
    mod = _make_module(name="net", functions=(fn,))
    pkg = _make_package(name="mylib", modules=(mod,))
    result = format_tree(pkg)
    assert "async def fetch() -> str" in result


@pytest.mark.parametrize(
    ("returns", "expected"),
    [("int", "property p: int"), (None, "property p")],
)
def test_format_tree_property(returns: str | None, expected: str) -> None:
    """A property renders as the attribute callers read, not as a call."""
    self_param = _make_parameter(name="self", annotation=None)
    fn = _make_function(name="p", positional_parameters=(self_param,), returns=returns, kind="property")
    mod = _make_module(name="ops", functions=(fn,))
    result = format_tree(mod)
    assert result.splitlines()[-1].endswith(expected)
    assert "def p" not in result


@pytest.mark.parametrize("kind", ["classmethod", "staticmethod"])
def test_format_tree_classmethod_and_staticmethod_are_prefixed(kind: FunctionKind) -> None:
    """Classmethods and staticmethods are prefixed with their kind."""
    fn = _make_function(name="build", returns="None", kind=kind)
    mod = _make_module(name="ops", functions=(fn,))
    assert f"{kind} def build() -> None" in format_tree(mod)


def test_format_tree_method_has_no_prefix() -> None:
    """A plain method renders like a function."""
    fn = _make_function(name="run", kind="method")
    mod = _make_module(name="ops", functions=(fn,))
    assert format_tree(mod).splitlines()[-1].endswith("── def run()")


def test_format_tree_function_positional_params() -> None:
    """Positional parameters appear in declaration order."""
    p1 = _make_parameter(name="a", annotation="int")
    p2 = _make_parameter(name="b", annotation="str", default="'hi'")
    fn = _make_function(name="greet", positional_parameters=(p1, p2))
    mod = _make_module(name="ops", functions=(fn,))
    pkg = _make_package(name="mylib", modules=(mod,))
    result = format_tree(pkg)
    assert "greet(a: int, b: str = 'hi')" in result


def test_format_tree_function_var_positional() -> None:
    """*args renders as ``*args``."""
    args = Parameter(name="args", annotation=None, default=None)
    fn = _make_function(name="variadic", var_positional=args)
    mod = _make_module(name="ops", functions=(fn,))
    pkg = _make_package(name="mylib", modules=(mod,))
    result = format_tree(pkg)
    assert "variadic(*args)" in result


def test_format_tree_function_var_keyword() -> None:
    """**kwargs renders correctly."""
    kwargs = Parameter(name="kwargs", annotation=None, default=None)
    fn = _make_function(name="wrapper", var_keyword=kwargs)
    mod = _make_module(name="ops", functions=(fn,))
    pkg = _make_package(name="mylib", modules=(mod,))
    result = format_tree(pkg)
    assert "wrapper(**kwargs)" in result


def test_format_tree_function_keyword_only_separator() -> None:
    """Keyword-only params without *args get a bare ``*`` separator."""
    kw = _make_parameter(name="verbose", annotation="bool", default="False")
    fn = _make_function(name="run", keyword_parameters=frozenset({kw}))
    mod = _make_module(name="ops", functions=(fn,))
    pkg = _make_package(name="mylib", modules=(mod,))
    result = format_tree(pkg)
    assert "run(*, verbose: bool = False)" in result


def test_format_tree_class_appears() -> None:
    """A class node appears with ``class`` prefix and its name."""
    cls = _make_class(name="Widget")
    mod = _make_module(name="ui", classes=(cls,))
    pkg = _make_package(name="mylib", modules=(mod,))
    result = format_tree(pkg)
    assert "class Widget" in result


def test_format_tree_class_method_indented() -> None:
    """A method inside a class is indented under the class node."""
    method = _make_function(name="render", returns="str")
    cls = _make_class(name="Widget", methods=(method,))
    mod = _make_module(name="ui", classes=(cls,))
    pkg = _make_package(name="mylib", modules=(mod,))
    result = format_tree(pkg)
    lines = result.splitlines()
    class_idx = next(i for i, line in enumerate(lines) if "class Widget" in line)
    method_idx = next(i for i, line in enumerate(lines) if "render() -> str" in line)
    assert method_idx > class_idx


def test_format_tree_nested_class() -> None:
    """A nested class appears under its parent class."""
    inner = _make_class(name="Inner")
    outer = _make_class(name="Outer", nested_classes=(inner,))
    mod = _make_module(name="stuff", classes=(outer,))
    pkg = _make_package(name="mylib", modules=(mod,))
    result = format_tree(pkg)
    assert "class Inner" in result
    lines = result.splitlines()
    outer_idx = next(i for i, line in enumerate(lines) if "class Outer" in line)
    inner_idx = next(i for i, line in enumerate(lines) if "class Inner" in line)
    assert inner_idx > outer_idx


def test_format_tree_subpackage() -> None:
    """A subpackage appears with ``package`` prefix."""
    subpkg = _make_package(name="sub", path=Path("/fake/sub"))
    pkg = _make_package(name="mylib", subpackages=(subpkg,))
    result = format_tree(pkg)
    assert "package sub" in result


def test_format_tree_golden_string() -> None:
    """Full golden-string check for a small but realistic package."""
    # Build: mylib
    #   module core
    #     VERSION: str
    #     class Widget
    #       └── render() -> str
    #     do_thing()
    #   package sub
    version = Assignment(name="VERSION", annotation="str")
    render = _make_function(name="render", returns="str")
    widget = _make_class(name="Widget", methods=(render,))
    do_thing = _make_function(name="do_thing")
    core = _make_module(
        name="core",
        assignments=(version,),
        classes=(widget,),
        functions=(do_thing,),
    )
    sub = _make_package(name="sub", path=Path("/fake/sub"))
    pkg = _make_package(name="mylib", modules=(core,), subpackages=(sub,))

    result = format_tree(pkg)

    expected = (
        "package mylib\n"
        "├── module core\n"
        "│   ├── VERSION: str\n"
        "│   ├── class Widget\n"
        "│   │   └── def render() -> str\n"
        "│   └── def do_thing()\n"
        "└── package sub"
    )
    assert result == expected


def test_format_json_returns_valid_json() -> None:
    """format_json must return a string parseable by json.loads."""
    pkg = _make_package(name="mylib")
    output = format_json(pkg)
    parsed = json.loads(output)
    assert isinstance(parsed, dict)


def test_format_json_top_level_keys_present() -> None:
    """The JSON object must contain the expected top-level keys."""
    pkg = _make_package(name="mylib")
    parsed = json.loads(format_json(pkg))
    assert "name" in parsed
    assert "path" in parsed
    assert "modules" in parsed
    assert "subpackages" in parsed


def test_format_json_name_value() -> None:
    """The ``name`` field in JSON matches the package name."""
    pkg = _make_package(name="awesome_lib")
    parsed = json.loads(format_json(pkg))
    assert parsed["name"] == "awesome_lib"


def test_format_json_path_is_string() -> None:
    """The ``path`` field must be serialised as a plain string, not a mapping."""
    pkg = _make_package(name="mylib", path=Path("/some/path"))
    parsed = json.loads(format_json(pkg))
    assert isinstance(parsed["path"], str)


def test_format_json_root_path_is_dot() -> None:
    """The root package path is rendered as ``"."``, not as an absolute path."""
    pkg = _make_package(name="mylib", path=Path("/some/path"))
    parsed = json.loads(format_json(pkg))
    assert parsed["path"] == "."


def test_format_json_subpackage_path_is_relative_to_root() -> None:
    """Subpackage paths are POSIX paths relative to the root package directory."""
    sub = _make_package(name="mylib.sub.deep", path=Path("/some/path/sub/deep"))
    pkg = _make_package(name="mylib", path=Path("/some/path"), subpackages=(sub,))
    parsed = json.loads(format_json(pkg))
    assert parsed["subpackages"][0]["path"] == "sub/deep"


def test_format_json_stable_across_two_calls() -> None:
    """Two calls with identical input must produce identical output."""
    fn = _make_function(
        name="go",
        keyword_parameters=frozenset(
            {
                _make_parameter(name="alpha", annotation="int"),
                _make_parameter(name="beta", annotation="str"),
            }
        ),
    )
    mod = _make_module(name="core", functions=(fn,))
    pkg = _make_package(name="mylib", modules=(mod,))
    assert format_json(pkg) == format_json(pkg)


def test_format_json_modules_is_list() -> None:
    """``modules`` must serialise as a JSON array."""
    mod = _make_module(name="utils")
    pkg = _make_package(name="mylib", modules=(mod,))
    parsed = json.loads(format_json(pkg))
    assert isinstance(parsed["modules"], list)
    assert parsed["modules"][0]["name"] == "utils"


def test_format_json_indented_two_spaces() -> None:
    """Output must use two-space indentation (json.dumps indent=2)."""
    mod = _make_module(name="utils")
    pkg = _make_package(name="mylib", modules=(mod,))
    output = format_json(pkg)
    # The second line should start with two spaces (top-level key indentation)
    second_line = output.splitlines()[1]
    assert second_line.startswith("  ")
    assert not second_line.startswith("   ")


def test_format_json_frozenset_keyword_params_sorted() -> None:
    """keyword_parameters (frozenset) must appear sorted by name in JSON."""
    kw_z = _make_parameter(name="zebra", annotation="str")
    kw_a = _make_parameter(name="aardvark", annotation="int")
    kw_m = _make_parameter(name="marmot", annotation="float")

    fn = _make_function(
        name="zoo",
        keyword_parameters=frozenset({kw_z, kw_a, kw_m}),
    )
    mod = _make_module(name="animals", functions=(fn,))
    pkg = _make_package(name="mylib", modules=(mod,))

    parsed = json.loads(format_json(pkg))
    kw_list: list[dict[str, Any]] = parsed["modules"][0]["functions"][0]["keyword_parameters"]
    names = [p["name"] for p in kw_list]
    assert names == sorted(names)


def test_format_json_frozenset_order_independent_of_construction_order() -> None:
    """Two Functions built with keyword params in different frozenset iteration
    orders must produce identical JSON."""
    kw_a = _make_parameter(name="alpha", annotation="int")
    kw_b = _make_parameter(name="beta", annotation="str")
    kw_c = _make_parameter(name="gamma", annotation="float")

    fn1 = _make_function(
        name="process",
        keyword_parameters=frozenset({kw_a, kw_b, kw_c}),
    )
    fn2 = _make_function(
        name="process",
        keyword_parameters=frozenset({kw_c, kw_a, kw_b}),
    )

    mod1 = _make_module(name="core", functions=(fn1,))
    mod2 = _make_module(name="core", functions=(fn2,))
    pkg1 = _make_package(name="mylib", modules=(mod1,))
    pkg2 = _make_package(name="mylib", modules=(mod2,))

    assert format_json(pkg1) == format_json(pkg2)


def test_format_json_frozenset_same_name_params_stable() -> None:
    """When two keyword params share the same name the output is still deterministic
    (same params, same JSON on every call).  The sort key is name-only per the spec;
    we simply verify stability rather than a particular annotation order."""
    kw_int = Parameter(name="val", annotation="int", default=None)
    kw_str = Parameter(name="val", annotation="str", default=None)

    fn = _make_function(
        name="ambiguous",
        keyword_parameters=frozenset({kw_int, kw_str}),
    )
    mod = _make_module(name="core", functions=(fn,))
    pkg = _make_package(name="mylib", modules=(mod,))

    # Two calls must produce identical output (stable sort, no hash randomness).
    assert format_json(pkg) == format_json(pkg)

    # Both parameter dicts must appear in the list.
    parsed = json.loads(format_json(pkg))
    kw_list: list[dict[str, Any]] = parsed["modules"][0]["functions"][0]["keyword_parameters"]
    assert len(kw_list) == 2
    found_annotations = {p["annotation"] for p in kw_list}
    assert found_annotations == {"int", "str"}


def test_format_tree_empty_package_no_newline() -> None:
    """An empty package must not trail with a newline."""
    pkg = _make_package(name="empty")
    result = format_tree(pkg)
    assert not result.endswith("\n")


def test_format_tree_package_header() -> None:
    """The first line of format_tree output is always ``package <name>``."""
    pkg = _make_package(name="acme")
    first_line = format_tree(pkg).splitlines()[0]
    assert first_line == "package acme"


def test_format_json_empty_package() -> None:
    """An empty package serialises with empty lists for modules and subpackages."""
    pkg = _make_package(name="empty", path=Path("/e"))
    parsed = json.loads(format_json(pkg))
    assert parsed["modules"] == []
    assert parsed["subpackages"] == []


def test_format_tree_single_module_single_function() -> None:
    """A package with exactly one module containing one function."""
    fn = _make_function(name="hello", returns="None")
    mod = _make_module(name="greetings", functions=(fn,))
    pkg = _make_package(name="mylib", modules=(mod,))
    result = format_tree(pkg)
    expected = "package mylib\n└── module greetings\n    └── def hello() -> None"
    assert result == expected


def test_format_json_single_module_single_function() -> None:
    """A package with one module and one function round-trips correctly."""
    fn = _make_function(name="hello", returns="None")
    mod = _make_module(name="greetings", functions=(fn,))
    pkg = _make_package(name="mylib", modules=(mod,))
    parsed = json.loads(format_json(pkg))
    assert parsed["modules"][0]["name"] == "greetings"
    assert parsed["modules"][0]["functions"][0]["name"] == "hello"
    assert parsed["modules"][0]["functions"][0]["returns"] == "None"


def test_format_json_class_methods_serialised() -> None:
    """Methods inside a class appear in the JSON output."""
    method = _make_function(name="act", returns="bool")
    cls = _make_class(name="Agent", methods=(method,))
    mod = _make_module(name="agents", classes=(cls,))
    pkg = _make_package(name="mylib", modules=(mod,))
    parsed = json.loads(format_json(pkg))
    cls_data = parsed["modules"][0]["classes"][0]
    assert cls_data["name"] == "Agent"
    assert cls_data["methods"][0]["name"] == "act"


def test_format_json_nested_class_serialised() -> None:
    """Nested classes appear under the parent class in JSON."""
    inner = _make_class(name="Inner")
    outer = _make_class(name="Outer", nested_classes=(inner,))
    mod = _make_module(name="nesting", classes=(outer,))
    pkg = _make_package(name="mylib", modules=(mod,))
    parsed = json.loads(format_json(pkg))
    outer_data = parsed["modules"][0]["classes"][0]
    assert outer_data["nested_classes"][0]["name"] == "Inner"


@pytest.mark.parametrize(
    "annotation, expected_label",
    [
        ("str", "CONST: str"),
        (None, "CONST"),
    ],
)
def test_format_tree_assignment_label_variants(
    annotation: str | None,
    expected_label: str,
) -> None:
    """Parametrised: both rendering paths for Assignment labels."""
    a = Assignment(name="CONST", annotation=annotation)
    mod = _make_module(name="m", assignments=(a,))
    pkg = _make_package(name="p", modules=(mod,))
    result = format_tree(pkg)
    assert expected_label in result


@pytest.mark.parametrize(
    "name,annotation,default,expected_param_str",
    [
        ("x", "int", None, "x: int"),
        ("y", None, "'hello'", "y = 'hello'"),
        ("z", "float", "0.0", "z: float = 0.0"),
        ("plain", None, None, "plain"),
    ],
)
def test_format_tree_parameter_rendering(
    name: str,
    annotation: str | None,
    default: str | None,
    expected_param_str: str,
) -> None:
    """Parametrised: parameter strings render correctly in function signatures."""
    p = Parameter(name=name, annotation=annotation, default=default)
    fn = _make_function(name="f", positional_parameters=(p,))
    mod = _make_module(name="m", functions=(fn,))
    pkg = _make_package(name="p", modules=(mod,))
    result = format_tree(pkg)
    assert expected_param_str in result


def test_format_tree_init_module_hoisted_no_intermediate_node() -> None:
    """A Package whose only module is the init module (module.name == package.name)
    must NOT produce an intermediate ``module <name>`` node — its contents are
    hoisted directly to the package level.
    """
    fn = _make_function(name="do_work", returns="None")
    init_mod = _make_module(name="mylib", functions=(fn,))  # name matches package
    pkg = _make_package(name="mylib", modules=(init_mod,))

    result = format_tree(pkg)
    lines = result.splitlines()

    # The spurious intermediate node must be absent.
    assert not any("module mylib" in line for line in lines), (
        "init module was not hoisted; found unexpected 'module mylib' node"
    )
    # The function must appear directly as a child of the package header.
    assert any("do_work()" in line for line in lines), "hoisted function not found in output"


def test_format_tree_init_module_hoisted_class_and_assignment() -> None:
    """Classes and assignments from the init module are also hoisted, each
    appearing at the package level without an intermediate module node.
    """
    a = _make_assignment(name="VERSION", annotation="str")
    cls = _make_class(name="Client")
    init_mod = _make_module(name="mylib", assignments=(a,), classes=(cls,))
    pkg = _make_package(name="mylib", modules=(init_mod,))

    result = format_tree(pkg)
    lines = result.splitlines()

    assert not any("module mylib" in line for line in lines)
    assert any("VERSION: str" in line for line in lines)
    assert any("class Client" in line for line in lines)


def test_format_tree_non_init_module_still_has_module_node() -> None:
    """A module whose name does NOT match the package name must still render
    as a ``module <name>`` child — the hoisting logic must not swallow it.
    """
    fn = _make_function(name="helper")
    non_init = _make_module(name="utils", functions=(fn,))
    pkg = _make_package(name="mylib", modules=(non_init,))

    result = format_tree(pkg)
    lines = result.splitlines()

    assert any("module utils" in line for line in lines), "non-init module should appear as 'module utils'"


def test_format_tree_mixed_init_and_non_init_modules() -> None:
    """A Package with both an init module (hoisted) and a regular submodule
    renders the init contents at package level while the submodule still
    appears as ``module <name>``.
    """
    init_fn = _make_function(name="top_level_func")
    init_mod = _make_module(name="mylib", functions=(init_fn,))

    sub_fn = _make_function(name="internal")
    sub_mod = _make_module(name="helpers", functions=(sub_fn,))

    pkg = _make_package(name="mylib", modules=(init_mod, sub_mod))

    result = format_tree(pkg)

    assert "module helpers" in result, "non-init submodule must appear as 'module helpers'"
    assert "module mylib" not in result, "init module must not produce its own node"
    assert "top_level_func()" in result, "init-level function must be present"


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        (Reference(name="sqrt", module="math", attribute="sqrt"), "from math import sqrt"),
        (
            Reference(name="Ordered", module="collections", attribute="OrderedDict"),
            "from collections import OrderedDict as Ordered",
        ),
        (Reference(name="json", module="json", attribute=None), "import json"),
        (Reference(name="os", module="os", attribute=None), "import os"),
        (Reference(name="la", module="numpy.linalg", attribute=None), "import numpy.linalg as la"),
        (Reference(name="ghost", module=None, attribute=None), "ghost (unresolved)"),
    ],
)
def test_format_tree_renders_module_references(reference: Reference, expected: str) -> None:
    module = Module(name="m", assignments=(), classes=(), functions=(), references=(reference,))
    assert format_tree(module) == f"module m\n└── {expected}"


def test_format_tree_hoists_init_references_to_package_level() -> None:
    init_mod = Module(
        name="pkg",
        assignments=(),
        classes=(),
        functions=(),
        references=(Reference(name="sqrt", module="math", attribute="sqrt"),),
    )
    pkg = Package(name="pkg", path=Path("/fake"), modules=(init_mod,), subpackages=())
    assert format_tree(pkg) == "package pkg\n└── from math import sqrt"


def test_format_json_includes_references() -> None:
    module = Module(
        name="m",
        assignments=(),
        classes=(),
        functions=(),
        references=(Reference(name="json", module="json", attribute=None),),
    )
    data = json.loads(format_json(module))
    assert data["references"] == [{"node_type": "reference", "name": "json", "module": "json", "attribute": None}]


def test_format_json_path_outside_root_is_not_absolute() -> None:
    """A path outside the root package directory is reduced to its final component."""
    sub = _make_package(name="mylib.sub", path=Path("/elsewhere/sub"))
    pkg = _make_package(name="mylib", path=Path("/some/path"), subpackages=(sub,))
    parsed = json.loads(format_json(pkg))
    assert parsed["subpackages"][0]["path"] == "sub"


def _overloaded() -> Function:
    overloads = tuple(
        Function(
            name="f",
            positional_parameters=(_make_parameter(name="x", annotation=t),),
            keyword_parameters=frozenset(),
            var_positional=None,
            var_keyword=None,
            returns=t,
            is_async=False,
            decorators=("typing.overload",),
        )
        for t in ("int", "str")
    )
    return Function(
        name="f",
        positional_parameters=(_make_parameter(name="x", annotation=None),),
        keyword_parameters=frozenset(),
        var_positional=None,
        var_keyword=None,
        returns=None,
        is_async=False,
        overloads=overloads,
    )


def test_format_tree_shows_overloads_and_hides_implementation() -> None:
    result = format_tree(_make_module(name="m", functions=(_overloaded(),)))

    assert result.splitlines() == [
        "module m",
        "├── def f(x: int) -> int",
        "└── def f(x: str) -> str",
    ]


def test_format_tree_can_show_overload_implementation() -> None:
    result = format_tree(_make_module(name="m", functions=(_overloaded(),)), show_overload_implementation=True)

    assert result.splitlines() == [
        "module m",
        "├── def f(x: int) -> int",
        "├── def f(x: str) -> str",
        "└── def f(x)",
    ]


def test_format_tree_does_not_repeat_overload_standing_in_for_implementation() -> None:
    *_, last = _overloaded().overloads
    fn = dataclasses.replace(last, overloads=_overloaded().overloads)

    result = format_tree(_make_module(name="m", functions=(fn,)), show_overload_implementation=True)

    assert result.splitlines() == [
        "module m",
        "├── def f(x: int) -> int",
        "└── def f(x: str) -> str",
    ]


def test_format_tree_shows_method_overloads() -> None:
    cls = _make_class(name="C", methods=(dataclasses.replace(_overloaded(), kind="method"),))

    result = format_tree(_make_module(name="m", classes=(cls,)))

    assert result.splitlines() == [
        "module m",
        "└── class C",
        "    ├── def f(x: int) -> int",
        "    └── def f(x: str) -> str",
    ]


def test_format_json_includes_overloads() -> None:
    data = json.loads(format_json(_make_module(name="m", functions=(_overloaded(),))))

    (fn,) = data["functions"]
    assert [o["returns"] for o in fn["overloads"]] == ["int", "str"]


def test_format_json_top_level_has_schema_version() -> None:
    parsed = json.loads(format_json(_make_package(name="mylib")))
    assert parsed["schema_version"] == JSON_SCHEMA_VERSION
    assert next(iter(parsed)) == "schema_version"


def test_format_json_module_root_has_schema_version() -> None:
    parsed = json.loads(format_json(_make_module(name="m")))
    assert parsed["schema_version"] == JSON_SCHEMA_VERSION


def test_format_json_schema_version_only_at_top_level() -> None:
    sub = _make_package(name="mylib.sub", path=Path("/p/sub"))
    pkg = _make_package(name="mylib", path=Path("/p"), modules=(_make_module(name="m"),), subpackages=(sub,))
    parsed = json.loads(format_json(pkg))
    assert "schema_version" not in parsed["subpackages"][0]
    assert "schema_version" not in parsed["modules"][0]


def test_format_json_every_node_has_node_type() -> None:
    method = _make_function(name="act")
    cls = _make_class(name="Agent", methods=(method,), nested_classes=(_make_class(name="Inner"),))
    mod = Module(
        name="m",
        assignments=(_make_assignment(),),
        classes=(cls,),
        functions=(_overloaded(),),
        references=(Reference(name="json", module="json", attribute=None),),
    )
    sub = _make_package(name="mylib.sub", path=Path("/p/sub"))
    pkg = _make_package(name="mylib", path=Path("/p"), modules=(mod,), subpackages=(sub,))

    parsed = json.loads(format_json(pkg))
    module = parsed["modules"][0]
    cls_data = module["classes"][0]
    function = module["functions"][0]

    assert parsed["node_type"] == "package"
    assert parsed["subpackages"][0]["node_type"] == "package"
    assert module["node_type"] == "module"
    assert module["assignments"][0]["node_type"] == "assignment"
    assert module["references"][0]["node_type"] == "reference"
    assert cls_data["node_type"] == "class"
    assert cls_data["nested_classes"][0]["node_type"] == "class"
    assert cls_data["methods"][0]["node_type"] == "function"
    assert function["node_type"] == "function"
    assert {o["node_type"] for o in function["overloads"]} == {"function"}


def test_format_json_node_type_does_not_replace_function_kind() -> None:
    method = _make_function(name="make", kind="classmethod")
    mod = _make_module(name="m", classes=(_make_class(name="C", methods=(method,)),))
    parsed = json.loads(format_json(mod))
    method_data = parsed["classes"][0]["methods"][0]
    assert method_data["node_type"] == "function"
    assert method_data["kind"] == "classmethod"


def test_format_json_parameters_have_no_node_type() -> None:
    fn = _make_function(name="f", positional_parameters=(_make_parameter(),))
    parsed = json.loads(format_json(_make_module(name="m", functions=(fn,))))
    assert "node_type" not in parsed["functions"][0]["positional_parameters"][0]
