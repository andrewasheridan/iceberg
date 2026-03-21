"""Tests for sheridan.iceberg public API surface (__init__.py)."""

import sheridan.iceberg as iceberg
from sheridan.iceberg import Issue, IssueKind, ModuleInfo, fix_module, report, walk_module, walk_path


class TestPublicApi:
    def test_all_exports_are_importable(self) -> None:
        for name in iceberg.__all__:
            assert hasattr(iceberg, name), f"{name} not found on sheridan.iceberg"

    def test_module_info_is_exported(self) -> None:
        assert ModuleInfo is iceberg.ModuleInfo

    def test_walk_module_is_exported(self) -> None:
        assert walk_module is iceberg.walk_module

    def test_walk_path_is_exported(self) -> None:
        assert walk_path is iceberg.walk_path

    def test_fix_module_is_exported(self) -> None:
        assert fix_module is iceberg.fix_module

    def test_report_is_exported(self) -> None:
        assert report is iceberg.report

    def test_issue_is_exported(self) -> None:
        assert Issue is iceberg.Issue

    def test_issue_kind_is_exported(self) -> None:
        assert IssueKind is iceberg.IssueKind

    def test_all_list_contents(self) -> None:
        assert set(iceberg.__all__) == {
            "Issue",
            "IssueKind",
            "ModuleInfo",
            "fix_module",
            "report",
            "walk_module",
            "walk_path",
        }
