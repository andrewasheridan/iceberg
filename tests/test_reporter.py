"""Tests for sheridan.iceberg.reporter."""

import json
from pathlib import Path

import pytest

from sheridan.iceberg.ast_walker import ModuleInfo
from sheridan.iceberg.reporter import Issue, IssueKind, check_modules, report

# ---------------------------------------------------------------------------
# IssueKind
# ---------------------------------------------------------------------------


class TestIssueKind:
    def test_values(self) -> None:
        assert IssueKind.MISSING.value == "missing"
        assert IssueKind.INCORRECT.value == "incorrect"
        assert IssueKind.UNSORTED.value == "unsorted"


# ---------------------------------------------------------------------------
# Issue.to_dict
# ---------------------------------------------------------------------------


class TestIssueToDictAndToText:
    def test_to_dict_missing(self, tmp_path: Path) -> None:
        issue = Issue(
            path=tmp_path / "mod.py",
            kind=IssueKind.MISSING,
            declared=None,
            expected=["Foo"],
        )
        d = issue.to_dict()
        assert d["kind"] == "missing"
        assert d["declared"] is None
        assert d["expected"] == ["Foo"]
        assert d["path"] == str(tmp_path / "mod.py")

    def test_to_dict_incorrect(self, tmp_path: Path) -> None:
        issue = Issue(
            path=tmp_path / "mod.py",
            kind=IssueKind.INCORRECT,
            declared=["Bar"],
            expected=["Foo"],
        )
        d = issue.to_dict()
        assert d["kind"] == "incorrect"
        assert d["declared"] == ["Bar"]
        assert d["expected"] == ["Foo"]

    def test_to_dict_unsorted(self, tmp_path: Path) -> None:
        issue = Issue(
            path=tmp_path / "mod.py",
            kind=IssueKind.UNSORTED,
            declared=["Beta", "Alpha"],
            expected=["Alpha", "Beta"],
        )
        d = issue.to_dict()
        assert d["kind"] == "unsorted"

    def test_to_text_missing(self, tmp_path: Path) -> None:
        p = tmp_path / "mod.py"
        issue = Issue(path=p, kind=IssueKind.MISSING, declared=None, expected=["Foo"])
        text = issue.to_text()
        assert "missing __all__" in text
        assert str(p) in text
        assert "Foo" in text

    def test_to_text_incorrect(self, tmp_path: Path) -> None:
        p = tmp_path / "mod.py"
        issue = Issue(path=p, kind=IssueKind.INCORRECT, declared=["Bar"], expected=["Foo"])
        text = issue.to_text()
        assert "missing from __all__" in text
        assert "Foo" in text

    def test_to_text_unsorted(self, tmp_path: Path) -> None:
        p = tmp_path / "mod.py"
        issue = Issue(
            path=p,
            kind=IssueKind.UNSORTED,
            declared=["Beta", "Alpha"],
            expected=["Alpha", "Beta"],
        )
        text = issue.to_text()
        assert "not sorted" in text
        assert "Alpha" in text


# ---------------------------------------------------------------------------
# check_modules() — pure issue detection
# ---------------------------------------------------------------------------


class TestCheckModules:
    def _make_info(self, tmp_path: Path, declared: list[str] | None, inferred: list[str]) -> ModuleInfo:
        return ModuleInfo(path=tmp_path / "mod.py", declared_all=declared, inferred_all=inferred)

    def test_no_issues_when_all_correct(self, tmp_path: Path) -> None:
        info = self._make_info(tmp_path, ["Foo", "bar"], ["bar", "Foo"])
        assert check_modules([info]) == []

    def test_missing_all_reported(self, tmp_path: Path) -> None:
        info = self._make_info(tmp_path, None, ["Foo"])
        issues = check_modules([info])
        assert len(issues) == 1
        assert issues[0].kind == IssueKind.MISSING

    def test_incorrect_all_reported(self, tmp_path: Path) -> None:
        info = self._make_info(tmp_path, ["Wrong"], ["Correct"])
        issues = check_modules([info])
        assert len(issues) == 1
        assert issues[0].kind == IssueKind.INCORRECT

    def test_empty_module_list_returns_empty(self) -> None:
        assert check_modules([]) == []

    def test_multiple_modules_aggregated(self, tmp_path: Path) -> None:
        info1 = self._make_info(tmp_path, None, ["Foo"])
        info2 = ModuleInfo(path=tmp_path / "b.py", declared_all=["Bad"], inferred_all=["Good"])
        issues = check_modules([info1, info2])
        assert len(issues) == 2

    def test_ib002_and_ib003_both_fire(self, tmp_path: Path) -> None:
        # declared is unsorted AND missing a public name
        info = self._make_info(tmp_path, ["Z", "A"], ["A", "B", "Z"])
        issues = check_modules([info])
        kinds = [i.kind for i in issues]
        assert IssueKind.INCORRECT in kinds  # B is in AST but not in __all__
        assert IssueKind.UNSORTED in kinds  # ["Z", "A"] is not sorted

    def test_phantom_only_no_ib002(self, tmp_path: Path) -> None:
        # "Ghost" is in __all__ but not in AST — no IB002
        info = self._make_info(tmp_path, ["Ghost", "Real"], ["Real"])
        issues = check_modules([info])
        kinds = [i.kind for i in issues]
        assert IssueKind.INCORRECT not in kinds
        # sorted ["Ghost", "Real"] == ["Ghost", "Real"] → no IB003 either
        assert issues == []


# ---------------------------------------------------------------------------
# report() — issue detection
# ---------------------------------------------------------------------------


class TestReport:
    def _make_info(self, tmp_path: Path, declared: list[str] | None, inferred: list[str]) -> ModuleInfo:
        return ModuleInfo(
            path=tmp_path / "mod.py",
            declared_all=declared,
            inferred_all=inferred,
        )

    def test_no_issues_when_all_correct_and_sorted(self, tmp_path: Path) -> None:
        info = self._make_info(tmp_path, ["Foo", "bar"], ["bar", "Foo"])
        issues, _output = report([info])
        assert issues == []

    def test_missing_all_reported(self, tmp_path: Path) -> None:
        info = self._make_info(tmp_path, None, ["Foo"])
        issues, _ = report([info])
        assert len(issues) == 1
        assert issues[0].kind == IssueKind.MISSING

    def test_incorrect_all_reported(self, tmp_path: Path) -> None:
        info = self._make_info(tmp_path, ["Wrong"], ["Correct"])
        issues, _ = report([info])
        assert len(issues) == 1
        assert issues[0].kind == IssueKind.INCORRECT

    def test_unsorted_all_reported(self, tmp_path: Path) -> None:
        info = self._make_info(tmp_path, ["Beta", "Alpha"], ["Alpha", "Beta"])
        issues, _ = report([info])
        assert len(issues) == 1
        assert issues[0].kind == IssueKind.UNSORTED

    def test_unsorted_not_reported_when_already_sorted(self, tmp_path: Path) -> None:
        info = self._make_info(tmp_path, ["Alpha", "Beta"], ["Alpha", "Beta"])
        issues, _ = report([info])
        assert issues == []

    def test_phantom_names_in_all_do_not_trigger_ib002(self, tmp_path: Path) -> None:
        # "Extra" is in __all__ but not in AST — not an IB002 (one-directional check)
        info = self._make_info(tmp_path, ["A", "Extra", "Z"], ["A", "Z"])
        issues, _ = report([info])
        kinds = {i.kind for i in issues}
        assert IssueKind.INCORRECT not in kinds

    def test_multiple_modules_multiple_issues(self, tmp_path: Path) -> None:
        info1 = self._make_info(tmp_path, None, ["Foo"])
        info2 = ModuleInfo(path=tmp_path / "b.py", declared_all=["Bad"], inferred_all=["Good"])
        issues, _ = report([info1, info2])
        assert len(issues) == 2

    def test_empty_module_list_returns_no_issues(self) -> None:
        issues, output = report([])
        assert issues == []
        assert output == ""

    def test_missing_expected_is_sorted_inferred(self, tmp_path: Path) -> None:
        info = self._make_info(tmp_path, None, ["zebra", "apple"])
        issues, _ = report([info])
        assert issues[0].expected == ["apple", "zebra"]

    def test_module_with_empty_all_and_no_public_names(self, tmp_path: Path) -> None:
        info = self._make_info(tmp_path, [], [])
        issues, _ = report([info])
        assert issues == []


# ---------------------------------------------------------------------------
# report() — output format
# ---------------------------------------------------------------------------


class TestReportOutputFormat:
    def test_text_format_default(self, tmp_path: Path) -> None:
        info = ModuleInfo(path=tmp_path / "mod.py", declared_all=None, inferred_all=["Foo"])
        _, output = report([info], fmt="text")
        assert "missing __all__" in output

    def test_json_format_valid_json(self, tmp_path: Path) -> None:
        info = ModuleInfo(path=tmp_path / "mod.py", declared_all=None, inferred_all=["Foo"])
        _, output = report([info], fmt="json")
        parsed = json.loads(output)
        assert isinstance(parsed, list)
        assert parsed[0]["kind"] == "missing"

    def test_json_format_no_issues_is_empty_list(self, tmp_path: Path) -> None:
        info = ModuleInfo(path=tmp_path / "mod.py", declared_all=["Foo"], inferred_all=["Foo"])
        _, output = report([info], fmt="json")
        assert json.loads(output) == []

    def test_text_multiple_issues_joined_by_newline(self, tmp_path: Path) -> None:
        info1 = ModuleInfo(path=tmp_path / "a.py", declared_all=None, inferred_all=["Foo"])
        info2 = ModuleInfo(path=tmp_path / "b.py", declared_all=None, inferred_all=["Bar"])
        _, output = report([info1, info2], fmt="text")
        lines = output.splitlines()
        assert len(lines) == 2

    def test_invalid_format_raises_value_error(self, tmp_path: Path) -> None:
        info = ModuleInfo(path=tmp_path / "mod.py", declared_all=None, inferred_all=[])
        with pytest.raises(ValueError, match="Unknown format"):
            report([info], fmt="xml")

    def test_no_issues_text_output_is_empty_string(self, tmp_path: Path) -> None:
        info = ModuleInfo(path=tmp_path / "mod.py", declared_all=["Foo"], inferred_all=["Foo"])
        _, output = report([info], fmt="text")
        assert output == ""
