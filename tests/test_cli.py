"""Tests for sheridan.iceberg.cli."""

import json
import sys
from pathlib import Path

import pytest

from sheridan.iceberg import cli


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
