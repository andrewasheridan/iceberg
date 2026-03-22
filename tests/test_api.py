"""Tests for sheridan.iceberg.api."""

from pathlib import Path
from unittest.mock import patch

import pytest

from sheridan.iceberg.api import check_api, fix_api, get_public_api
from sheridan.iceberg.ast_walker import ModuleInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, source: str) -> Path:
    path.write_text(source, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# get_public_api — single file
# ---------------------------------------------------------------------------


class TestGetPublicApiFile:
    def test_returns_dict(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Foo"]\ndef Foo(): ...\n')
        result = get_public_api(p)
        assert isinstance(result, dict)

    def test_key_is_module_stem(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mymod.py", '__all__ = ["Foo"]\ndef Foo(): ...\n')
        result = get_public_api(p)
        assert "mymod" in result

    def test_value_is_list_of_strings(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Foo", "Bar"]\ndef Foo(): ...\ndef Bar(): ...\n')
        result = get_public_api(p)
        assert result["mod"] == ["Foo", "Bar"]

    def test_uses_declared_all_by_default(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Declared"]\ndef Inferred(): ...\n')
        result = get_public_api(p)
        assert result["mod"] == ["Declared"]

    def test_uses_inferred_when_no_all(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "def PublicFn(): ...\ndef _private(): ...\n")
        result = get_public_api(p)
        assert result["mod"] == ["PublicFn"]

    def test_use_ast_returns_inferred_names(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Declared"]\ndef Inferred(): ...\n')
        result = get_public_api(p, use_ast=True)
        assert result["mod"] == ["Inferred"]

    def test_use_ast_false_returns_declared_names(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Alpha"]\ndef Beta(): ...\n')
        result = get_public_api(p, use_ast=False)
        assert result["mod"] == ["Alpha"]

    def test_accepts_str_path(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        result = get_public_api(str(p))
        assert "mod" in result

    def test_empty_module_returns_empty_list(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "empty.py", "")
        result = get_public_api(p)
        assert result["empty"] == []

    def test_module_with_empty_all_returns_empty_list(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "__all__: list[str] = []\n")
        result = get_public_api(p)
        assert result["mod"] == []

    def test_use_ast_empty_module_returns_empty_list(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "")
        result = get_public_api(p, use_ast=True)
        assert result["mod"] == []


# ---------------------------------------------------------------------------
# get_public_api — directory
# ---------------------------------------------------------------------------


class TestGetPublicApiDirectory:
    def test_returns_entry_for_each_module(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.py", "def Alpha(): ...\n")
        _write(tmp_path / "b.py", "def Beta(): ...\n")
        result = get_public_api(tmp_path)
        assert "a" in result
        assert "b" in result

    def test_accepts_str_directory(self, tmp_path: Path) -> None:
        _write(tmp_path / "mod.py", "def Foo(): ...\n")
        result = get_public_api(str(tmp_path))
        assert "mod" in result

    def test_empty_directory_returns_empty_dict(self, tmp_path: Path) -> None:
        result = get_public_api(tmp_path)
        assert result == {}

    def test_module_keys_are_relative_dotted(self, tmp_path: Path) -> None:
        sub = tmp_path / "pkg"
        sub.mkdir()
        _write(sub / "util.py", "def helper(): ...\n")
        result = get_public_api(tmp_path)
        assert "pkg.util" in result

    def test_init_module_key_strips_dunder_init(self, tmp_path: Path) -> None:
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        _write(pkg / "__init__.py", '__all__ = ["Pub"]\ndef Pub(): ...\n')
        result = get_public_api(tmp_path)
        assert "mypkg" in result
        assert "mypkg.__init__" not in result

    def test_init_with_all_suppresses_submodules(self, tmp_path: Path) -> None:
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        _write(pkg / "__init__.py", '__all__ = ["Pub"]\ndef Pub(): ...\n')
        _write(pkg / "sub.py", "def SubFn(): ...\n")
        result = get_public_api(tmp_path)
        assert "mypkg" in result
        assert "mypkg.sub" not in result

    def test_init_without_all_does_not_suppress_submodules(self, tmp_path: Path) -> None:
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        _write(pkg / "__init__.py", "")
        _write(pkg / "sub.py", "def SubFn(): ...\n")
        result = get_public_api(tmp_path)
        assert "mypkg.sub" in result

    def test_use_ast_true_shows_all_modules(self, tmp_path: Path) -> None:
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        _write(pkg / "__init__.py", '__all__ = ["Pub"]\ndef Pub(): ...\n')
        _write(pkg / "sub.py", "def SubFn(): ...\n")
        result = get_public_api(tmp_path, use_ast=True)
        assert "mypkg" in result
        assert "mypkg.sub" in result

    def test_use_ast_true_values_are_inferred(self, tmp_path: Path) -> None:
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        _write(pkg / "__init__.py", '__all__ = ["Declared"]\ndef Inferred(): ...\n')
        result = get_public_api(tmp_path, use_ast=True)
        assert result["mypkg"] == ["Inferred"]

    def test_skips_test_files(self, tmp_path: Path) -> None:
        _write(tmp_path / "mod.py", "def Foo(): ...\n")
        _write(tmp_path / "test_mod.py", "def test_foo(): ...\n")
        result = get_public_api(tmp_path)
        assert "mod" in result
        assert "test_mod" not in result

    def test_skips_unparseable_files(self, tmp_path: Path) -> None:
        _write(tmp_path / "good.py", "def Foo(): ...\n")
        _write(tmp_path / "bad.py", "def (\n")
        result = get_public_api(tmp_path)
        assert "good" in result
        assert "bad" not in result

    def test_path_outside_base_uses_str_fallback(self, tmp_path: Path) -> None:
        # Single file: when base=parent, relative_to always succeeds for files.
        # Test with a directory path to confirm no ValueError is raised.
        _write(tmp_path / "mod.py", "def Foo(): ...\n")
        result = get_public_api(tmp_path)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# check_api — single file
# ---------------------------------------------------------------------------


class TestCheckApiFile:
    def test_returns_list(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Foo"]\ndef Foo(): ...\n')
        result = check_api(p)
        assert isinstance(result, list)

    def test_no_issues_when_all_correct(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = [\n    "Foo",\n]\ndef Foo(): ...\n')
        result = check_api(p)
        assert result == []

    def test_reports_missing_all(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        result = check_api(p)
        assert len(result) == 1
        assert result[0]["kind"] == "missing"

    def test_reports_incorrect_all(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Wrong"]\ndef Correct(): ...\n')
        result = check_api(p)
        assert any(d["kind"] == "incorrect" for d in result)

    def test_reports_unsorted_all(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Beta", "Alpha"]\ndef Alpha(): ...\ndef Beta(): ...\n')
        result = check_api(p)
        assert any(d["kind"] == "unsorted" for d in result)

    def test_issue_dict_has_required_keys(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        result = check_api(p)
        assert len(result) == 1
        issue = result[0]
        assert "code" in issue
        assert "path" in issue
        assert "kind" in issue
        assert "declared" in issue
        assert "expected" in issue

    def test_accepts_str_path(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        result = check_api(str(p))
        assert isinstance(result, list)

    def test_ignore_missing_suppresses_ib001(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        result = check_api(p, ignore_missing=True)
        assert result == []

    def test_ignore_missing_false_reports_ib001(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        result = check_api(p, ignore_missing=False)
        assert len(result) == 1
        assert result[0]["kind"] == "missing"

    def test_ignore_missing_does_not_suppress_other_issues(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Beta", "Alpha"]\ndef Alpha(): ...\ndef Beta(): ...\n')
        result = check_api(p, ignore_missing=True)
        kinds = [d["kind"] for d in result]
        assert "unsorted" in kinds

    def test_phantom_export_not_flagged(self, tmp_path: Path) -> None:
        # "Ghost" is in __all__ but not in AST — IB002 is one-directional so no issue
        p = _write(tmp_path / "mod.py", '__all__ = ["Ghost", "Real"]\ndef Real(): ...\n')
        result = check_api(p)
        assert result == []


# ---------------------------------------------------------------------------
# check_api — directory
# ---------------------------------------------------------------------------


class TestCheckApiDirectory:
    def test_returns_list(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.py", "def Foo(): ...\n")
        result = check_api(tmp_path)
        assert isinstance(result, list)

    def test_aggregates_issues_across_files(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.py", "def Alpha(): ...\n")
        _write(tmp_path / "b.py", "def Beta(): ...\n")
        result = check_api(tmp_path)
        paths = [d["path"] for d in result]
        assert str(tmp_path / "a.py") in paths
        assert str(tmp_path / "b.py") in paths

    def test_empty_directory_returns_empty_list(self, tmp_path: Path) -> None:
        result = check_api(tmp_path)
        assert result == []

    def test_accepts_str_directory(self, tmp_path: Path) -> None:
        _write(tmp_path / "mod.py", "def Foo(): ...\n")
        result = check_api(str(tmp_path))
        assert isinstance(result, list)

    def test_ignore_missing_on_directory(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.py", "def Foo(): ...\n")
        _write(tmp_path / "b.py", "def Bar(): ...\n")
        result = check_api(tmp_path, ignore_missing=True)
        assert result == []


# ---------------------------------------------------------------------------
# fix_api — dry_run=True
# ---------------------------------------------------------------------------


class TestFixApiDryRun:
    def test_returns_list_of_paths(self, tmp_path: Path) -> None:
        _write(tmp_path / "mod.py", "def Foo(): ...\n")
        result = fix_api(tmp_path, dry_run=True)
        assert isinstance(result, list)
        assert all(isinstance(p, Path) for p in result)

    def test_does_not_modify_files(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        original = p.read_text(encoding="utf-8")
        fix_api(tmp_path, dry_run=True)
        assert p.read_text(encoding="utf-8") == original

    def test_returns_paths_that_would_be_modified(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        result = fix_api(tmp_path, dry_run=True)
        assert p in result

    def test_dry_run_on_already_correct_file(self, tmp_path: Path) -> None:
        _write(tmp_path / "mod.py", '__all__ = [\n    "Foo",\n]\ndef Foo(): ...\n')
        result = fix_api(tmp_path, dry_run=True)
        assert result == []

    def test_dry_run_single_file(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        result = fix_api(p, dry_run=True)
        assert p in result
        assert p.read_text(encoding="utf-8") == "def Foo(): ...\n"

    def test_accepts_str_path_dry_run(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        result = fix_api(str(tmp_path), dry_run=True)
        assert p in result


# ---------------------------------------------------------------------------
# fix_api — dry_run=False (live writes)
# ---------------------------------------------------------------------------


class TestFixApiLive:
    def test_modifies_file_in_place(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        fix_api(tmp_path)
        assert "__all__" in p.read_text(encoding="utf-8")

    def test_returns_modified_paths(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        result = fix_api(tmp_path)
        assert p in result

    def test_no_changes_returns_empty_list(self, tmp_path: Path) -> None:
        _write(tmp_path / "mod.py", '__all__ = [\n    "Foo",\n]\ndef Foo(): ...\n')
        result = fix_api(tmp_path)
        assert result == []

    def test_fixes_incorrect_all(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Wrong"]\ndef Correct(): ...\n')
        fix_api(tmp_path)
        source = p.read_text(encoding="utf-8")
        assert '"Correct"' in source
        assert '"Wrong"' not in source

    def test_fixes_phantom_export(self, tmp_path: Path) -> None:
        # "Ghost" in __all__ but not in AST — fix should remove it
        p = _write(tmp_path / "mod.py", '__all__ = ["Ghost", "Real"]\ndef Real(): ...\n')
        fix_api(tmp_path)
        source = p.read_text(encoding="utf-8")
        assert "Ghost" not in source
        assert "Real" in source

    def test_fixes_multiple_files(self, tmp_path: Path) -> None:
        p1 = _write(tmp_path / "a.py", "def Alpha(): ...\n")
        p2 = _write(tmp_path / "b.py", "def Beta(): ...\n")
        result = fix_api(tmp_path)
        assert set(result) == {p1, p2}
        assert "__all__" in p1.read_text(encoding="utf-8")
        assert "__all__" in p2.read_text(encoding="utf-8")

    def test_accepts_str_path(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        result = fix_api(str(tmp_path))
        assert p in result

    def test_single_file_input(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        result = fix_api(p)
        assert p in result
        assert "__all__" in p.read_text(encoding="utf-8")

    def test_empty_directory_returns_empty_list(self, tmp_path: Path) -> None:
        result = fix_api(tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# fix_api — dry_run semantics consistency
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dry_run", [True, False])
def test_fix_api_returns_empty_for_clean_module(tmp_path: Path, dry_run: bool) -> None:
    _write(tmp_path / "mod.py", '__all__ = [\n    "Foo",\n]\ndef Foo(): ...\n')
    result = fix_api(tmp_path, dry_run=dry_run)
    assert result == []


@pytest.mark.parametrize("dry_run", [True, False])
def test_fix_api_identifies_module_needing_fix(tmp_path: Path, dry_run: bool) -> None:
    p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
    result = fix_api(tmp_path, dry_run=dry_run)
    assert p in result


# ---------------------------------------------------------------------------
# get_public_api — ValueError fallback branch (path outside base)
# ---------------------------------------------------------------------------


def test_get_public_api_path_outside_base_uses_str_key(tmp_path: Path) -> None:
    # Construct a ModuleInfo whose path is NOT under the base so that
    # relative_to raises ValueError and the except branch is exercised.
    other = tmp_path / "other" / "mod.py"
    other.parent.mkdir()
    _write(other, "def Foo(): ...\n")

    outside_info = ModuleInfo(
        path=other,
        declared_all=["Foo"],
        inferred_all=["Foo"],
    )

    base_dir = tmp_path / "base"
    base_dir.mkdir()
    _write(base_dir / "placeholder.py", "")

    with (
        patch("sheridan.iceberg.api.load_modules", return_value=[outside_info]),
        patch("sheridan.iceberg.api.resolve_show_modules", return_value=[outside_info]),
    ):
        result = get_public_api(base_dir)

    # The key should be the str() of the path, not a dotted module name.
    assert str(other) in result
