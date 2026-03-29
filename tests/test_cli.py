"""Tests for sheridan.iceberg.cli."""

import json
import sys
from pathlib import Path

import pytest

from sheridan.iceberg import cli
from sheridan.iceberg.cli import (
    _build_detail,
    _format_show_json,
    _format_tree,
    _render_member,
    _render_param,
    _render_signature,
)
from sheridan.iceberg.enums import MemberKind, ParamKind
from sheridan.iceberg.models import (
    ClassMember,
    FunctionSignature,
    ModuleInfo,
    ParamInfo,
)


def _run(args: list[str]) -> int:
    """Run main() with the given argv, capture output, and return exit code."""
    sys.argv = ["iceberg", *args]
    exit_code = 0
    try:
        cli.main()
    except SystemExit as exc:
        exit_code = int(exc.code) if exc.code is not None else 0
    return exit_code


def _write(path: Path, source: str) -> Path:
    path.write_text(source, encoding="utf-8")
    return path


class TestCliParser:
    def test_no_subcommand_exits_nonzero(self) -> None:
        sys.argv = ["iceberg"]
        with pytest.raises(SystemExit) as exc_info:
            cli.main()
        assert exc_info.value.code != 0

    def test_invalid_format_exits_nonzero(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "x = 1\n")
        sys.argv = ["iceberg", "--format", "xml", str(p)]
        with pytest.raises(SystemExit) as exc_info:
            cli.main()
        assert exc_info.value.code != 0


class TestShowSubcommand:
    def test_exits_0_on_valid_file(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Foo"]\ndef Foo(): ...\n')
        code = _run([str(p)])
        assert code == 0

    def test_exits_2_when_path_does_not_exist(self, tmp_path: Path) -> None:
        code = _run([str(tmp_path / "ghost.py")])
        assert code == 2

    def test_tree_output_contains_module_name(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mymod.py", '__all__ = ["Alpha"]\ndef Alpha(): ...\n')
        _run([str(p)])
        captured = capsys.readouterr()
        assert "mymod" in captured.out

    def test_tree_output_contains_public_name(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mymod.py", '__all__ = ["Alpha"]\ndef Alpha(): ...\n')
        _run([str(p)])
        captured = capsys.readouterr()
        assert "Alpha" in captured.out

    def test_tree_output_respects_all_by_default(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        # __all__ = ["Declared"] but AST also has "Hidden"
        # Default: __all__ is authoritative — only "Declared" should appear
        p = _write(tmp_path / "mod.py", '__all__ = ["Declared"]\ndef Declared(): ...\ndef Hidden(): ...\n')
        _run([str(p)])
        captured = capsys.readouterr()
        assert "Declared" in captured.out
        assert "Hidden" not in captured.out

    def test_use_ast_ignores_all(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Declared"]\ndef Declared(): ...\ndef Hidden(): ...\n')
        _run(["--use-ast", str(p)])
        captured = capsys.readouterr()
        assert "Declared" in captured.out
        assert "Hidden" in captured.out

    def test_json_format_valid(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Foo"]\ndef Foo(): ...\n')
        _run(["--format", "json", str(p)])
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert isinstance(parsed, list)
        assert parsed[0]["names"] == ["Foo"]

    def test_json_source_is_all_when_declared(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Foo"]\ndef Foo(): ...\n')
        _run(["--format", "json", str(p)])
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed[0]["source"] == "__all__"

    def test_json_source_is_ast_when_use_ast(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Foo"]\ndef Foo(): ...\n')
        _run(["--format", "json", "--use-ast", str(p)])
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed[0]["source"] == "ast"

    def test_json_source_is_ast_when_no_all(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        _run(["--format", "json", str(p)])
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed[0]["source"] == "ast"

    def test_tree_directory_shows_root_header(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _write(tmp_path / "mod.py", '__all__ = ["Foo"]\ndef Foo(): ...\n')
        _run([str(tmp_path)])
        captured = capsys.readouterr()
        lines = captured.out.splitlines()
        # First line should be the directory (package) name; module is indented beneath it
        assert lines[0] == tmp_path.name
        assert lines[1] == "  mod"

    def test_stderr_on_missing_path(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _run([str(tmp_path / "ghost.py")])
        captured = capsys.readouterr()
        assert "does not exist" in captured.err


class TestRenderParam:
    def test_simple_no_annotation(self) -> None:
        assert _render_param(ParamInfo(name="x")) == "x"

    def test_param_with_annotation(self) -> None:
        assert _render_param(ParamInfo(name="x", annotation="int")) == "x: int"

    def test_param_with_default_and_annotation(self) -> None:
        assert _render_param(ParamInfo(name="x", annotation="int", has_default=True)) == "x: int = ..."

    def test_param_with_default_no_annotation(self) -> None:
        assert _render_param(ParamInfo(name="x", has_default=True)) == "x = ..."

    def test_var_positional_no_annotation(self) -> None:
        assert _render_param(ParamInfo(name="args", kind=ParamKind.var_positional)) == "*args"

    def test_var_positional_with_annotation(self) -> None:
        assert _render_param(ParamInfo(name="args", annotation="int", kind=ParamKind.var_positional)) == "*args: int"

    def test_var_keyword_no_annotation(self) -> None:
        assert _render_param(ParamInfo(name="kwargs", kind=ParamKind.var_keyword)) == "**kwargs"

    def test_var_keyword_with_annotation(self) -> None:
        assert _render_param(ParamInfo(name="kwargs", annotation="str", kind=ParamKind.var_keyword)) == "**kwargs: str"

    def test_var_positional_has_default_does_not_add_ellipsis(self) -> None:
        # *args cannot have a default; has_default is ignored for var_positional
        result = _render_param(ParamInfo(name="args", kind=ParamKind.var_positional, has_default=True))
        assert "= ..." not in result

    def test_var_keyword_has_default_does_not_add_ellipsis(self) -> None:
        result = _render_param(ParamInfo(name="kwargs", kind=ParamKind.var_keyword, has_default=True))
        assert "= ..." not in result


class TestRenderSignature:
    def test_empty_signature(self) -> None:
        assert _render_signature(FunctionSignature()) == "()"

    def test_single_param(self) -> None:
        sig = FunctionSignature(params=[ParamInfo(name="x", annotation="int")])
        assert _render_signature(sig) == "(x: int)"

    def test_return_annotation(self) -> None:
        sig = FunctionSignature(return_annotation="bool")
        assert _render_signature(sig) == "() \u2192 bool"

    def test_multiple_params(self) -> None:
        sig = FunctionSignature(
            params=[
                ParamInfo(name="x", annotation="int"),
                ParamInfo(name="y", annotation="str", has_default=True),
            ]
        )
        assert _render_signature(sig) == "(x: int, y: str = ...)"

    def test_keyword_only_inserts_bare_star(self) -> None:
        sig = FunctionSignature(
            params=[
                ParamInfo(name="kw", annotation="int", kind=ParamKind.keyword_only),
            ]
        )
        rendered = _render_signature(sig)
        assert "*, kw: int" in rendered

    def test_var_positional_prevents_bare_star(self) -> None:
        sig = FunctionSignature(
            params=[
                ParamInfo(name="args", kind=ParamKind.var_positional),
                ParamInfo(name="kw", annotation="int", kind=ParamKind.keyword_only),
            ]
        )
        rendered = _render_signature(sig)
        # bare "*" should NOT appear — *args already provides the separator
        assert "*, " not in rendered
        assert "*args" in rendered
        assert "kw: int" in rendered

    def test_positional_only_inserts_slash(self) -> None:
        sig = FunctionSignature(
            params=[
                ParamInfo(name="x", annotation="int", kind=ParamKind.positional_only),
                ParamInfo(name="y", annotation="str"),
            ]
        )
        rendered = _render_signature(sig)
        assert "x: int, /, y: str" in rendered

    def test_positional_only_trailing_slash(self) -> None:
        # all params are positional-only, slash goes at end
        sig = FunctionSignature(
            params=[
                ParamInfo(name="x", annotation="int", kind=ParamKind.positional_only),
            ]
        )
        rendered = _render_signature(sig)
        assert rendered == "(x: int, /)"


class TestRenderMember:
    def test_class_var_with_annotation(self) -> None:
        member = ClassMember(name="x", kind=MemberKind.class_var, annotation="int")
        assert _render_member(member) == "x: int"

    def test_class_var_without_annotation(self) -> None:
        member = ClassMember(name="x", kind=MemberKind.class_var)
        assert _render_member(member) == "x"

    def test_instance_attr_with_annotation(self) -> None:
        member = ClassMember(name="name", kind=MemberKind.instance_attr, annotation="str")
        assert _render_member(member) == "name: str"

    def test_instance_attr_without_annotation(self) -> None:
        member = ClassMember(name="name", kind=MemberKind.instance_attr)
        assert _render_member(member) == "name"

    def test_property_with_return_annotation(self) -> None:
        sig = FunctionSignature(return_annotation="int")
        member = ClassMember(name="value", kind=MemberKind.property, signature=sig)
        assert _render_member(member) == "value (property) \u2192 int"

    def test_property_without_return_annotation(self) -> None:
        sig = FunctionSignature()
        member = ClassMember(name="value", kind=MemberKind.property, signature=sig)
        assert _render_member(member) == "value (property)"

    def test_classmethod_with_signature(self) -> None:
        sig = FunctionSignature(
            params=[ParamInfo(name="cls")],
            return_annotation="Foo",
        )
        member = ClassMember(name="create", kind=MemberKind.classmethod, signature=sig)
        result = _render_member(member)
        assert result.startswith("classmethod create")
        assert "Foo" in result

    def test_staticmethod_with_signature(self) -> None:
        sig = FunctionSignature(
            params=[ParamInfo(name="s", annotation="str")],
            return_annotation="Foo",
        )
        member = ClassMember(name="parse", kind=MemberKind.staticmethod, signature=sig)
        result = _render_member(member)
        assert result.startswith("staticmethod parse")
        assert "Foo" in result

    def test_method_sync_with_signature(self) -> None:
        sig = FunctionSignature(
            params=[ParamInfo(name="self")],
            return_annotation="None",
            is_async=False,
        )
        member = ClassMember(name="update", kind=MemberKind.method, signature=sig)
        result = _render_member(member)
        assert result.startswith("update(")
        assert "None" in result
        assert "async" not in result

    def test_method_async_with_signature(self) -> None:
        sig = FunctionSignature(
            params=[ParamInfo(name="self")],
            return_annotation="None",
            is_async=True,
        )
        member = ClassMember(name="update", kind=MemberKind.method, signature=sig)
        result = _render_member(member)
        assert result.startswith("async update(")


class TestFormatTreeWithSignatures:
    @staticmethod
    def _make_modules(tmp_path: Path, source: str) -> dict[str, ModuleInfo]:
        from sheridan.iceberg.ast_walker import walk_module

        p = tmp_path / "mod.py"
        p.write_text(source, encoding="utf-8")
        return {"mod": walk_module(p)}

    def test_function_renders_with_signature(self, tmp_path: Path) -> None:
        modules = self._make_modules(tmp_path, "def greet(name: str) -> str: ...\n")
        result = _format_tree(modules, use_ast=True)
        assert "greet(name: str)" in result
        assert "\u2192 str" in result

    def test_async_function_renders_with_async_prefix(self, tmp_path: Path) -> None:
        modules = self._make_modules(tmp_path, "async def fetch(url: str) -> bytes: ...\n")
        result = _format_tree(modules, use_ast=True)
        assert "async fetch(" in result

    def test_class_renders_name_and_members(self, tmp_path: Path) -> None:
        source = "class Foo:\n    x: int = 5\n"
        modules = self._make_modules(tmp_path, source)
        result = _format_tree(modules, use_ast=True)
        assert "Foo" in result
        assert "x: int" in result

    def test_unannotated_variable_renders_with_untyped_marker(self, tmp_path: Path) -> None:
        modules = self._make_modules(tmp_path, "MY_CONST = 42\n")
        result = _format_tree(modules, use_ast=True)
        assert "MY_CONST (untyped)" in result

    def test_annotated_variable_renders_with_type(self, tmp_path: Path) -> None:
        modules = self._make_modules(tmp_path, 'VERSION: str = "1"\n')
        result = _format_tree(modules, use_ast=True)
        assert "VERSION: str" in result

    def test_unannotated_variable_in_mix_renders_with_untyped_marker(self, tmp_path: Path) -> None:
        source = "COUNT = 0\ndef reset() -> None: ...\n"
        modules = self._make_modules(tmp_path, source)
        result = _format_tree(modules, use_ast=True)
        assert "COUNT (untyped)" in result
        assert "reset(" in result

    def test_mix_of_function_class_variable(self, tmp_path: Path) -> None:
        source = "VERSION = '1'\ndef add(a: int, b: int) -> int: ...\nclass Point:\n    x: int = 0\n"
        modules = self._make_modules(tmp_path, source)
        result = _format_tree(modules, use_ast=True)
        assert "VERSION" in result
        assert "add(" in result
        assert "Point" in result
        assert "x: int" in result


class TestFormatShowJsonWithDetail:
    @staticmethod
    def _make_modules(tmp_path: Path, source: str) -> dict[str, ModuleInfo]:
        from sheridan.iceberg.ast_walker import walk_module

        p = tmp_path / "mod.py"
        p.write_text(source, encoding="utf-8")
        return {"mod": walk_module(p)}

    def test_json_output_has_detail_key(self, tmp_path: Path) -> None:
        modules = self._make_modules(tmp_path, "def f() -> None: ...\n")
        result = json.loads(_format_show_json(modules, use_ast=True))
        assert "detail" in result[0]

    def test_function_entry_has_kind_function(self, tmp_path: Path) -> None:
        modules = self._make_modules(tmp_path, "def f(x: int) -> bool: ...\n")
        result = json.loads(_format_show_json(modules, use_ast=True))
        detail = result[0]["detail"]
        assert "f" in detail
        assert detail["f"]["kind"] == "function"
        assert "signature" in detail["f"]

    def test_async_function_entry_has_kind_async_function(self, tmp_path: Path) -> None:
        modules = self._make_modules(tmp_path, "async def fetch() -> bytes: ...\n")
        result = json.loads(_format_show_json(modules, use_ast=True))
        detail = result[0]["detail"]
        assert detail["fetch"]["kind"] == "async function"

    def test_class_entry_has_kind_class_and_bases_and_members(self, tmp_path: Path) -> None:
        source = "class Foo:\n    x: int = 5\n"
        modules = self._make_modules(tmp_path, source)
        result = json.loads(_format_show_json(modules, use_ast=True))
        detail = result[0]["detail"]
        assert "Foo" in detail
        assert detail["Foo"]["kind"] == "class"
        assert "bases" in detail["Foo"]
        assert "members" in detail["Foo"]

    def test_variable_in_detail_with_kind_variable(self, tmp_path: Path) -> None:
        modules = self._make_modules(tmp_path, "MY_VAR = 42\n")
        result = json.loads(_format_show_json(modules, use_ast=True))
        detail = result[0]["detail"]
        assert "MY_VAR" in detail
        assert detail["MY_VAR"]["kind"] == "variable"

    def test_build_detail_includes_variables_for_module_with_no_functions_or_classes(self, tmp_path: Path) -> None:
        modules = self._make_modules(tmp_path, "MY_VAR = 1\nOTHER = 2\n")
        info = modules["mod"]
        names = info.effective_all if info.declared_all is not None else info.inferred_all
        detail = _build_detail(names, info)
        assert "MY_VAR" in detail
        my_var_entry = detail["MY_VAR"]
        assert isinstance(my_var_entry, dict)
        assert my_var_entry["kind"] == "variable"
        assert "OTHER" in detail

    def test_variable_detail_has_annotation_for_annotated_variable(self, tmp_path: Path) -> None:
        modules = self._make_modules(tmp_path, "VERSION: str = '1'\n")
        result = json.loads(_format_show_json(modules, use_ast=True))
        detail = result[0]["detail"]
        assert "VERSION" in detail
        assert detail["VERSION"]["kind"] == "variable"
        assert detail["VERSION"]["annotation"] == "str"

    def test_variable_detail_has_null_annotation_for_unannotated_variable(self, tmp_path: Path) -> None:
        modules = self._make_modules(tmp_path, "FOO = 42\n")
        result = json.loads(_format_show_json(modules, use_ast=True))
        detail = result[0]["detail"]
        assert "FOO" in detail
        assert detail["FOO"]["kind"] == "variable"
        assert detail["FOO"]["annotation"] is None
