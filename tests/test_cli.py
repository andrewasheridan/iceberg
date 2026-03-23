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
from sheridan.iceberg.models import (
    ClassMember,
    FunctionSignature,
    MemberKind,
    ModuleInfo,
    ParamInfo,
    ParamKind,
)


def _run(args: list[str], capsys: pytest.CaptureFixture[str]) -> int:
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


# ---------------------------------------------------------------------------
# check subcommand — basic
# ---------------------------------------------------------------------------


class TestCheckSubcommand:
    def test_exits_0_when_no_issues(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Foo"]\ndef Foo(): ...\n')
        code = _run(["check", str(p)], capsys)
        assert code == 0

    def test_exits_1_when_issues_found(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        code = _run(["check", str(p)], capsys)
        assert code == 1

    def test_exits_2_when_path_does_not_exist(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        code = _run(["check", str(tmp_path / "nonexistent.py")], capsys)
        assert code == 2

    def test_check_missing_all_prints_message(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        _run(["check", str(p)], capsys)
        captured = capsys.readouterr()
        assert "missing __all__" in captured.out

    def test_check_incorrect_all_prints_message(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Wrong"]\ndef Correct(): ...\n')
        _run(["check", str(p)], capsys)
        captured = capsys.readouterr()
        assert "missing from __all__" in captured.out

    def test_check_directory(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _write(tmp_path / "mod.py", "def Foo(): ...\n")
        code = _run(["check", str(tmp_path)], capsys)
        assert code == 1

    def test_stderr_on_missing_path(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _run(["check", str(tmp_path / "ghost.py")], capsys)
        captured = capsys.readouterr()
        assert "does not exist" in captured.err


# ---------------------------------------------------------------------------
# check —- --format json
# ---------------------------------------------------------------------------


class TestCheckFormatJson:
    def test_json_output_is_valid_json(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        _run(["check", "--format", "json", str(p)], capsys)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert isinstance(parsed, list)
        assert parsed[0]["kind"] == "missing"

    def test_json_output_empty_list_when_no_issues(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        # When there are no issues, _render produces "[]" which is falsy-ish but
        # the CLI still prints it because json.dumps([]) == "[]" which is truthy.
        # The check is `if output: print(output)` — "[]" IS truthy, so it prints.
        p = _write(tmp_path / "mod.py", '__all__ = [\n    "Foo",\n]\ndef Foo(): ...\n')
        code = _run(["check", "--format", "json", str(p)], capsys)
        captured = capsys.readouterr()
        # No issues → exit code 0; output is "[]" (valid JSON empty array)
        assert code == 0
        assert json.loads(captured.out) == []


# ---------------------------------------------------------------------------
# check — --ignore-missing
# ---------------------------------------------------------------------------


class TestCheckIgnoreMissing:
    def test_ignore_missing_suppresses_missing_issues(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        code = _run(["check", "--ignore-missing", str(p)], capsys)
        assert code == 0
        captured = capsys.readouterr()
        assert "missing" not in captured.out

    def test_ignore_missing_still_reports_incorrect(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Wrong"]\ndef Correct(): ...\n')
        code = _run(["check", "--ignore-missing", str(p)], capsys)
        assert code == 1

    def test_ignore_missing_still_reports_unsorted(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Beta", "Alpha"]\ndef Alpha(): ...\ndef Beta(): ...\n')
        code = _run(["check", "--ignore-missing", str(p)], capsys)
        assert code == 1


# ---------------------------------------------------------------------------
# fix subcommand — basic
# ---------------------------------------------------------------------------


class TestFixSubcommand:
    def test_exits_0_when_no_issues(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = [\n    "Foo",\n]\ndef Foo(): ...\n')
        code = _run(["fix", str(p)], capsys)
        assert code == 0

    def test_exits_2_when_path_does_not_exist(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        code = _run(["fix", str(tmp_path / "nonexistent.py")], capsys)
        assert code == 2

    def test_fix_writes_all_to_file(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        _run(["fix", str(p)], capsys)
        new_source = p.read_text(encoding="utf-8")
        assert "__all__" in new_source

    def test_fix_prints_fixed_path(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        _run(["fix", str(p)], capsys)
        captured = capsys.readouterr()
        assert "Fixed" in captured.out

    def test_fix_prints_count(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        _run(["fix", str(p)], capsys)
        captured = capsys.readouterr()
        assert "fixed" in captured.out.lower()

    def test_no_issues_prints_no_issues_message(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = [\n    "Foo",\n]\ndef Foo(): ...\n')
        _run(["fix", str(p)], capsys)
        captured = capsys.readouterr()
        assert "No issues" in captured.out

    def test_fix_directory(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _write(tmp_path / "mod.py", "def Foo(): ...\n")
        code = _run(["fix", str(tmp_path)], capsys)
        assert code == 0

    def test_stderr_on_missing_path(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _run(["fix", str(tmp_path / "ghost.py")], capsys)
        captured = capsys.readouterr()
        assert "does not exist" in captured.err

    def test_fix_removes_phantom_names(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        # __all__ has "Ghost" which doesn't exist in AST — fix should remove it
        p = _write(tmp_path / "mod.py", '__all__ = ["Foo", "Ghost"]\ndef Foo(): ...\n')
        _run(["fix", str(p)], capsys)
        new_source = p.read_text(encoding="utf-8")
        assert "Ghost" not in new_source
        assert "Foo" in new_source


# ---------------------------------------------------------------------------
# fix — --dry-run
# ---------------------------------------------------------------------------


class TestFixDryRun:
    def test_dry_run_does_not_write_file(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        original = "def Foo(): ...\n"
        p = _write(tmp_path / "mod.py", original)
        _run(["fix", "--dry-run", str(p)], capsys)
        assert p.read_text(encoding="utf-8") == original

    def test_dry_run_prints_would_fix(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        _run(["fix", "--dry-run", str(p)], capsys)
        captured = capsys.readouterr()
        assert "Would fix" in captured.out

    def test_dry_run_exits_0(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        code = _run(["fix", "--dry-run", str(p)], capsys)
        assert code == 0

    def test_dry_run_does_not_print_count(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        _run(["fix", "--dry-run", str(p)], capsys)
        captured = capsys.readouterr()
        # The "N file(s) fixed." line should not appear in dry-run mode
        assert "file(s) fixed" not in captured.out


# ---------------------------------------------------------------------------
# CLI parser — argument validation
# ---------------------------------------------------------------------------


class TestCliParser:
    def test_no_subcommand_exits_nonzero(self, capsys: pytest.CaptureFixture[str]) -> None:
        sys.argv = ["iceberg"]
        with pytest.raises(SystemExit) as exc_info:
            cli.main()
        assert exc_info.value.code != 0

    def test_invalid_format_exits_nonzero(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", "x = 1\n")
        sys.argv = ["iceberg", "check", "--format", "xml", str(p)]
        with pytest.raises(SystemExit) as exc_info:
            cli.main()
        assert exc_info.value.code != 0


# ---------------------------------------------------------------------------
# show subcommand
# ---------------------------------------------------------------------------


class TestShowSubcommand:
    def test_exits_0_on_valid_file(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Foo"]\ndef Foo(): ...\n')
        code = _run(["show", str(p)], capsys)
        assert code == 0

    def test_exits_2_when_path_does_not_exist(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        code = _run(["show", str(tmp_path / "ghost.py")], capsys)
        assert code == 2

    def test_tree_output_contains_module_name(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mymod.py", '__all__ = ["Alpha"]\ndef Alpha(): ...\n')
        _run(["show", str(p)], capsys)
        captured = capsys.readouterr()
        assert "mymod" in captured.out

    def test_tree_output_contains_public_name(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mymod.py", '__all__ = ["Alpha"]\ndef Alpha(): ...\n')
        _run(["show", str(p)], capsys)
        captured = capsys.readouterr()
        assert "Alpha" in captured.out

    def test_tree_output_respects_all_by_default(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        # __all__ = ["Declared"] but AST also has "Hidden"
        # Default: __all__ is authoritative — only "Declared" should appear
        p = _write(tmp_path / "mod.py", '__all__ = ["Declared"]\ndef Declared(): ...\ndef Hidden(): ...\n')
        _run(["show", str(p)], capsys)
        captured = capsys.readouterr()
        assert "Declared" in captured.out
        assert "Hidden" not in captured.out

    def test_use_ast_ignores_all(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Declared"]\ndef Declared(): ...\ndef Hidden(): ...\n')
        _run(["show", "--use-ast", str(p)], capsys)
        captured = capsys.readouterr()
        assert "Declared" in captured.out
        assert "Hidden" in captured.out

    def test_json_format_valid(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Foo"]\ndef Foo(): ...\n')
        _run(["show", "--format", "json", str(p)], capsys)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert isinstance(parsed, list)
        assert parsed[0]["names"] == ["Foo"]

    def test_json_source_is_all_when_declared(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Foo"]\ndef Foo(): ...\n')
        _run(["show", "--format", "json", str(p)], capsys)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed[0]["source"] == "__all__"

    def test_json_source_is_ast_when_use_ast(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Foo"]\ndef Foo(): ...\n')
        _run(["show", "--format", "json", "--use-ast", str(p)], capsys)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed[0]["source"] == "ast"

    def test_json_source_is_ast_when_no_all(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        _run(["show", "--format", "json", str(p)], capsys)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed[0]["source"] == "ast"

    def test_tree_directory_shows_root_header(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _write(tmp_path / "mod.py", '__all__ = ["Foo"]\ndef Foo(): ...\n')
        _run(["show", str(tmp_path)], capsys)
        captured = capsys.readouterr()
        # First line should be the directory name with trailing slash
        first_line = captured.out.splitlines()[0]
        assert first_line == f"{tmp_path.name}/"

    def test_stderr_on_missing_path(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _run(["show", str(tmp_path / "ghost.py")], capsys)
        captured = capsys.readouterr()
        assert "does not exist" in captured.err


# ---------------------------------------------------------------------------
# _render_param
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# _render_signature
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# _render_member
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# _format_tree with signatures
# ---------------------------------------------------------------------------


class TestFormatTreeWithSignatures:
    def _make_module(self, tmp_path: Path, source: str) -> ModuleInfo:
        from sheridan.iceberg.ast_walker import walk_module

        p = tmp_path / "mod.py"
        p.write_text(source, encoding="utf-8")
        return walk_module(p)

    def test_function_renders_with_signature(self, tmp_path: Path) -> None:
        info = self._make_module(tmp_path, "def greet(name: str) -> str: ...\n")
        result = _format_tree([info], tmp_path / "mod.py", use_ast=True)
        assert "greet(name: str)" in result
        assert "\u2192 str" in result

    def test_async_function_renders_with_async_prefix(self, tmp_path: Path) -> None:
        info = self._make_module(tmp_path, "async def fetch(url: str) -> bytes: ...\n")
        result = _format_tree([info], tmp_path / "mod.py", use_ast=True)
        assert "async fetch(" in result

    def test_class_renders_name_and_members(self, tmp_path: Path) -> None:
        source = "class Foo:\n    x: int = 5\n"
        info = self._make_module(tmp_path, source)
        result = _format_tree([info], tmp_path / "mod.py", use_ast=True)
        assert "Foo" in result
        assert "x: int" in result

    def test_plain_variable_renders_as_name_only(self, tmp_path: Path) -> None:
        info = self._make_module(tmp_path, "MY_CONST = 42\n")
        result = _format_tree([info], tmp_path / "mod.py", use_ast=True)
        assert "MY_CONST" in result
        # No parentheses since it is not a function
        lines = [ln.strip() for ln in result.splitlines() if "MY_CONST" in ln]
        assert all("(" not in ln for ln in lines)

    def test_mix_of_function_class_variable(self, tmp_path: Path) -> None:
        source = "VERSION = '1'\ndef add(a: int, b: int) -> int: ...\nclass Point:\n    x: int = 0\n"
        info = self._make_module(tmp_path, source)
        result = _format_tree([info], tmp_path / "mod.py", use_ast=True)
        assert "VERSION" in result
        assert "add(" in result
        assert "Point" in result
        assert "x: int" in result


# ---------------------------------------------------------------------------
# _format_show_json / _build_detail
# ---------------------------------------------------------------------------


class TestFormatShowJsonWithDetail:
    def _make_module(self, tmp_path: Path, source: str) -> ModuleInfo:
        from sheridan.iceberg.ast_walker import walk_module

        p = tmp_path / "mod.py"
        p.write_text(source, encoding="utf-8")
        return walk_module(p)

    def test_json_output_has_detail_key(self, tmp_path: Path) -> None:
        info = self._make_module(tmp_path, "def f() -> None: ...\n")
        result = json.loads(_format_show_json([info], tmp_path / "mod.py", use_ast=True))
        assert "detail" in result[0]

    def test_function_entry_has_kind_function(self, tmp_path: Path) -> None:
        info = self._make_module(tmp_path, "def f(x: int) -> bool: ...\n")
        result = json.loads(_format_show_json([info], tmp_path / "mod.py", use_ast=True))
        detail = result[0]["detail"]
        assert "f" in detail
        assert detail["f"]["kind"] == "function"
        assert "signature" in detail["f"]

    def test_async_function_entry_has_kind_async_function(self, tmp_path: Path) -> None:
        info = self._make_module(tmp_path, "async def fetch() -> bytes: ...\n")
        result = json.loads(_format_show_json([info], tmp_path / "mod.py", use_ast=True))
        detail = result[0]["detail"]
        assert detail["fetch"]["kind"] == "async function"

    def test_class_entry_has_kind_class_and_bases_and_members(self, tmp_path: Path) -> None:
        source = "class Foo:\n    x: int = 5\n"
        info = self._make_module(tmp_path, source)
        result = json.loads(_format_show_json([info], tmp_path / "mod.py", use_ast=True))
        detail = result[0]["detail"]
        assert "Foo" in detail
        assert detail["Foo"]["kind"] == "class"
        assert "bases" in detail["Foo"]
        assert "members" in detail["Foo"]

    def test_variable_not_in_detail(self, tmp_path: Path) -> None:
        info = self._make_module(tmp_path, "MY_VAR = 42\n")
        result = json.loads(_format_show_json([info], tmp_path / "mod.py", use_ast=True))
        detail = result[0]["detail"]
        assert "MY_VAR" not in detail

    def test_build_detail_empty_for_module_with_no_functions_or_classes(self, tmp_path: Path) -> None:
        info = self._make_module(tmp_path, "MY_VAR = 1\nOTHER = 2\n")
        names = info.effective_all if info.declared_all is not None else info.inferred_all
        detail = _build_detail(names, info)
        assert detail == {}
