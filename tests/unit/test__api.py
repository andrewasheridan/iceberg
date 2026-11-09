"""Tests for sheridan.iceberg._api."""

from pathlib import Path

import pytest

from sheridan.iceberg._api import get_public_api, get_public_api_report
from sheridan.iceberg._config import Config
from sheridan.iceberg._exceptions import InvalidPathError, ParseError
from sheridan.iceberg._models import Package


def test_get_public_api_nonexistent_path_raises_invalid_path_error() -> None:
    nonexistent = Path("/nonexistent/path/that/does/not/exist")
    with pytest.raises(InvalidPathError):
        get_public_api(nonexistent)


@pytest.mark.parametrize("name", ["README.md", "module.txt", "module.pyi", "Makefile"])
def test_get_public_api_non_py_file_raises_invalid_path_error(tmp_path: Path, name: str) -> None:
    target = tmp_path / name
    target.write_text("# not a Python module\n")
    with pytest.raises(InvalidPathError, match=r"not a \.py file"):
        get_public_api(target)


class TestGetPublicApiReport:
    """``get_public_api_report`` returns the API with its diagnostics."""

    def test_keep_going_reports_errors_before_warnings(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text('__all__ = ["lazy"]\n', encoding="utf-8")
        (pkg / "vendored.py").write_text("print 'py2'\n", encoding="utf-8")

        report = get_public_api_report(pkg, config=Config(), keep_going=True)

        assert isinstance(report.api, Package)
        assert [(d.severity, d.module) for d in report.diagnostics] == [("error", "pkg.vendored"), ("warning", "pkg")]
        assert report.has_errors

    def test_without_keep_going_errors_raise(self, tmp_path: Path) -> None:
        (tmp_path / "bad.py").write_text("print 'py2'\n", encoding="utf-8")

        with pytest.raises(ParseError):
            get_public_api_report(tmp_path, config=Config())

    def test_warnings_without_keep_going(self, tmp_path: Path) -> None:
        target = tmp_path / "mod.py"
        target.write_text('__all__ = ["lazy"]\n', encoding="utf-8")

        report = get_public_api_report(target, config=Config())

        assert [(d.severity, d.path) for d in report.diagnostics] == [("warning", target.resolve())]
        assert not report.has_errors

    def test_keep_going_single_file_still_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "bad.py"
        target.write_text("print 'py2'\n", encoding="utf-8")

        with pytest.raises(ParseError):
            get_public_api_report(target, config=Config(), keep_going=True)

    def test_get_public_api_returns_report_api(self, tmp_path: Path) -> None:
        target = tmp_path / "mod.py"
        target.write_text("def f() -> None: ...\n", encoding="utf-8")

        assert get_public_api(target) == get_public_api_report(target).api
