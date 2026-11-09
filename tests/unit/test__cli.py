"""Tests for sheridan.iceberg._cli."""

import json
import os
import stat
from importlib.metadata import version
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sheridan.iceberg._cli import main
from sheridan.iceberg._config import Config
from sheridan.iceberg._exceptions import IcebergError, InvalidPathError
from sheridan.iceberg._models import Report

_TREE_OUTPUT = "package mypackage\n└── module mymodule"
_JSON_OUTPUT = '{\n  "name": "mypackage"\n}'


def test_main_success_tree_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """main returns 0 and writes tree output to stdout."""
    fake_package = MagicMock()

    with (
        patch("sheridan.iceberg._cli.get_public_api_report", return_value=Report(api=fake_package)) as mock_api,
        patch("sheridan.iceberg._cli.format_tree", return_value=_TREE_OUTPUT) as mock_tree,
        patch("sheridan.iceberg._cli.format_json") as mock_json,
    ):
        exit_code = main(["some/path"])

    assert exit_code == 0

    captured = capsys.readouterr()
    assert _TREE_OUTPUT in captured.out
    assert captured.err == ""

    mock_api.assert_called_once()
    mock_tree.assert_called_once_with(fake_package, show_overload_implementation=False)
    mock_json.assert_not_called()


def test_main_success_tree_uses_path_argument(capsys: pytest.CaptureFixture[str]) -> None:
    """main passes the path argument as a Path object to get_public_api_report."""

    fake_package = MagicMock()

    with (
        patch("sheridan.iceberg._cli.get_public_api_report", return_value=Report(api=fake_package)) as mock_api,
        patch("sheridan.iceberg._cli.format_tree", return_value=_TREE_OUTPUT),
    ):
        main(["src/mypackage"])

    called_path = mock_api.call_args.args[0]
    assert isinstance(called_path, Path)
    assert str(called_path) == "src/mypackage"


def test_main_success_stderr_is_empty(capsys: pytest.CaptureFixture[str]) -> None:
    """On success, nothing is written to stderr."""
    fake_package = MagicMock()

    with (
        patch("sheridan.iceberg._cli.get_public_api_report", return_value=Report(api=fake_package)),
        patch("sheridan.iceberg._cli.format_tree", return_value=_TREE_OUTPUT),
    ):
        main(["some/path"])

    captured = capsys.readouterr()
    assert captured.err == ""


def test_main_json_flag_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """main returns 0 and writes JSON output to stdout when --json is passed."""
    fake_package = MagicMock()

    with (
        patch("sheridan.iceberg._cli.get_public_api_report", return_value=Report(api=fake_package)) as mock_api,
        patch("sheridan.iceberg._cli.format_json", return_value=_JSON_OUTPUT) as mock_json,
        patch("sheridan.iceberg._cli.format_tree") as mock_tree,
    ):
        exit_code = main(["some/path", "--json"])

    assert exit_code == 0

    captured = capsys.readouterr()
    assert _JSON_OUTPUT in captured.out
    assert captured.err == ""

    mock_api.assert_called_once()
    mock_json.assert_called_once_with(fake_package, None)
    mock_tree.assert_not_called()


def test_main_json_flag_stderr_is_empty(capsys: pytest.CaptureFixture[str]) -> None:
    """On success with --json, nothing is written to stderr."""
    fake_package = MagicMock()

    with (
        patch("sheridan.iceberg._cli.get_public_api_report", return_value=Report(api=fake_package)),
        patch("sheridan.iceberg._cli.format_json", return_value=_JSON_OUTPUT),
    ):
        main(["some/path", "--json"])

    captured = capsys.readouterr()
    assert captured.err == ""


def test_main_iceberg_error_returns_1(capsys: pytest.CaptureFixture[str]) -> None:
    """main returns 1 when get_public_api_report raises an IcebergError."""
    with patch(
        "sheridan.iceberg._cli.get_public_api_report",
        side_effect=InvalidPathError("path does not exist: /bad/path"),
    ):
        exit_code = main(["/bad/path"])

    assert exit_code == 1


def test_main_iceberg_error_message_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    """main writes 'error: <msg>' to stderr on IcebergError."""
    error_msg = "path does not exist: /bad/path"

    with patch(
        "sheridan.iceberg._cli.get_public_api_report",
        side_effect=InvalidPathError(error_msg),
    ):
        main(["/bad/path"])

    captured = capsys.readouterr()
    assert f"error: {error_msg}" in captured.err
    assert captured.out == ""


def test_main_iceberg_error_nothing_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """On IcebergError, nothing is written to stdout."""
    with patch(
        "sheridan.iceberg._cli.get_public_api_report",
        side_effect=IcebergError("some iceberg error"),
    ):
        main(["any/path"])

    captured = capsys.readouterr()
    assert captured.out == ""


@pytest.mark.parametrize(
    "exc",
    [
        InvalidPathError("path does not exist: /x"),
        IcebergError("generic iceberg failure"),
    ],
    ids=["InvalidPathError", "IcebergError"],
)
def test_main_iceberg_error_subclasses_return_1(
    exc: IcebergError,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Any IcebergError subclass causes exit code 1."""
    with patch("sheridan.iceberg._cli.get_public_api_report", side_effect=exc):
        exit_code = main(["any/path"])

    assert exit_code == 1


def test_main_unexpected_error_returns_2(capsys: pytest.CaptureFixture[str]) -> None:
    """main returns 2 when get_public_api_report raises an unexpected exception."""
    with patch(
        "sheridan.iceberg._cli.get_public_api_report",
        side_effect=RuntimeError("something went very wrong"),
    ):
        exit_code = main(["any/path"])

    assert exit_code == 2


def test_main_unexpected_error_message_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    """main writes 'unexpected error: <type>: <msg>' to stderr on unexpected exceptions."""
    with patch(
        "sheridan.iceberg._cli.get_public_api_report",
        side_effect=RuntimeError("something went very wrong"),
    ):
        main(["any/path"])

    captured = capsys.readouterr()
    assert "unexpected error: RuntimeError: something went very wrong" in captured.err
    assert captured.out == ""


def test_main_unexpected_error_hints_at_traceback_and_tracker(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without --traceback, the message names the option and the issue tracker."""
    monkeypatch.delenv("ICEBERG_DEBUG", raising=False)

    with patch("sheridan.iceberg._cli.get_public_api_report", side_effect=RuntimeError("boom")):
        main(["any/path"])

    err = capsys.readouterr().err

    assert "--traceback" in err
    assert "ICEBERG_DEBUG=1" in err
    assert "https://github.com/andrewasheridan/iceberg/issues" in err
    assert "Traceback (most recent call last)" not in err


def test_main_traceback_option_prints_full_traceback(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--traceback prints the full traceback of an unexpected error."""
    monkeypatch.delenv("ICEBERG_DEBUG", raising=False)

    with patch("sheridan.iceberg._cli.get_public_api_report", side_effect=RuntimeError("boom")):
        exit_code = main(["any/path", "--traceback"])

    err = capsys.readouterr().err

    assert exit_code == 2
    assert "Traceback (most recent call last)" in err
    assert "RuntimeError: boom" in err
    assert "https://github.com/andrewasheridan/iceberg/issues" in err


@pytest.mark.parametrize(("value", "shows_traceback"), [("1", True), ("0", False), ("", False)])
def test_main_iceberg_debug_env_prints_full_traceback(
    value: str,
    shows_traceback: bool,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ICEBERG_DEBUG=1 works like --traceback; other values do not."""
    monkeypatch.setenv("ICEBERG_DEBUG", value)

    with patch("sheridan.iceberg._cli.get_public_api_report", side_effect=RuntimeError("boom")):
        exit_code = main(["any/path"])

    err = capsys.readouterr().err

    assert exit_code == 2
    assert ("Traceback (most recent call last)" in err) is shows_traceback


def test_main_traceback_option_does_not_affect_iceberg_errors(capsys: pytest.CaptureFixture[str]) -> None:
    """Known iceberg errors keep their one-line message under --traceback."""
    with patch("sheridan.iceberg._cli.get_public_api_report", side_effect=IcebergError("bad")):
        exit_code = main(["any/path", "--traceback"])

    err = capsys.readouterr().err

    assert exit_code == 1
    assert err == "error: bad\n"


def test_main_unexpected_error_nothing_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """On an unexpected exception, nothing is written to stdout."""
    with patch(
        "sheridan.iceberg._cli.get_public_api_report",
        side_effect=ValueError("oops"),
    ):
        main(["any/path"])

    captured = capsys.readouterr()
    assert captured.out == ""


@pytest.mark.parametrize(
    ("exc", "expected_type_name"),
    [
        (RuntimeError("boom"), "RuntimeError"),
        (ValueError("bad value"), "ValueError"),
        (TypeError("wrong type"), "TypeError"),
        (OSError("disk error"), "OSError"),
    ],
    ids=["RuntimeError", "ValueError", "TypeError", "OSError"],
)
def test_main_unexpected_error_includes_type_name(
    exc: Exception,
    expected_type_name: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The unexpected error message contains the exception class name."""
    with patch("sheridan.iceberg._cli.get_public_api_report", side_effect=exc):
        exit_code = main(["any/path"])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert expected_type_name in captured.err


@pytest.mark.parametrize(
    ("target", "extra_args"),
    [
        ("format_tree", []),
        ("format_json", ["--json"]),
        ("_write_output", ["-o", "api.txt"]),
    ],
    ids=["format_tree", "format_json", "_write_output"],
)
class TestUnexpectedErrorAfterAnalysis:
    """Unexpected errors while formatting or writing the report go through the bug-report handler."""

    def test_returns_2_with_bug_report_message(
        self,
        target: str,
        extra_args: list[str],
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("ICEBERG_DEBUG", raising=False)

        with (
            patch("sheridan.iceberg._cli.get_public_api_report", return_value=Report(api=MagicMock())),
            patch(f"sheridan.iceberg._cli.{target}", side_effect=RecursionError("too deep")),
        ):
            exit_code = main(["some/path", *extra_args])

        captured = capsys.readouterr()

        assert exit_code == 2
        assert "unexpected error: RecursionError: too deep" in captured.err
        assert "https://github.com/andrewasheridan/iceberg/issues" in captured.err
        assert "Traceback (most recent call last)" not in captured.err
        assert captured.out == ""

    def test_traceback_option_prints_full_traceback(
        self,
        target: str,
        extra_args: list[str],
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("ICEBERG_DEBUG", raising=False)

        with (
            patch("sheridan.iceberg._cli.get_public_api_report", return_value=Report(api=MagicMock())),
            patch(f"sheridan.iceberg._cli.{target}", side_effect=RecursionError("too deep")),
        ):
            exit_code = main(["some/path", "--traceback", *extra_args])

        err = capsys.readouterr().err

        assert exit_code == 2
        assert "Traceback (most recent call last)" in err
        assert "RecursionError: too deep" in err


def test_main_argv_none_reads_sys_argv(capsys: pytest.CaptureFixture[str]) -> None:
    """When argv is None, main reads from sys.argv[1:]."""
    fake_package = MagicMock()

    with (
        patch("sys.argv", ["iceberg", "some/path"]),
        patch("sheridan.iceberg._cli.get_public_api_report", return_value=Report(api=fake_package)) as mock_api,
        patch("sheridan.iceberg._cli.format_tree", return_value=_TREE_OUTPUT),
    ):
        exit_code = main(None)

    assert exit_code == 0
    mock_api.assert_called_once()


def test_main_non_py_file_returns_1_with_message(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A file target that is not a .py file exits 1 with a clear message."""
    target = tmp_path / "README.md"
    target.write_text("# Title\n")

    exit_code = main([str(target)])

    captured = capsys.readouterr()

    assert exit_code == 1
    assert "error: not a .py file" in captured.err
    assert captured.out == ""


def test_main_syntax_error_reports_file_line_and_column(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "good.py").write_text("x = 1\n")
    bad = pkg / "mod.py"
    bad.write_text("x = 1\n\ndef f(:\n    pass\n")

    exit_code = main([str(pkg)])

    assert exit_code == 1
    err = capsys.readouterr().err

    assert err.startswith(f"error: {bad}:3:7: ")
    assert "(<unknown>" not in err


def _package(tmp_path: Path, module_bytes: bytes) -> Path:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_bytes(module_bytes)
    return pkg


def test_main_latin1_declaration_is_used(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A module with a PEP 263 latin-1 declaration is decoded with latin-1."""
    source = "# -*- coding: latin-1 -*-\ndef café() -> None: ...\n"
    pkg = _package(tmp_path, source.encode("latin-1"))

    assert main([str(pkg)]) == 0
    assert "café" in capsys.readouterr().out


def test_main_undecodable_file_returns_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A module that is not valid UTF-8 is an IcebergError naming the file."""
    pkg = _package(tmp_path, 'NAME = "café"\n'.encode("latin-1"))

    assert main([str(pkg)]) == 1
    captured = capsys.readouterr()

    assert str(pkg / "mod.py") in captured.err
    assert "unexpected error" not in captured.err


def test_main_broken_symlink_returns_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A module that is a broken symlink is an IcebergError naming the file."""
    pkg = _package(tmp_path, b"")
    (pkg / "mod.py").unlink()
    (pkg / "mod.py").symlink_to(tmp_path / "missing.py")

    assert main([str(pkg)]) == 1
    captured = capsys.readouterr()

    assert str(pkg / "mod.py") in captured.err
    assert "unexpected error" not in captured.err


def test_main_exclude_extends_configured_list(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Repeated --exclude options are appended to the configured exclude list."""
    (tmp_path / "pyproject.toml").write_text('[tool.iceberg]\nexclude = ["a"]\n', encoding="utf-8")

    with (
        patch("sheridan.iceberg._cli.get_public_api_report", return_value=Report(api=MagicMock())) as mock_api,
        patch("sheridan.iceberg._cli.format_tree", return_value=_TREE_OUTPUT),
    ):
        exit_code = main([str(tmp_path), "--exclude", "b", "--exclude", "**/c"])

    assert exit_code == 0
    assert mock_api.call_args.kwargs["config"].exclude == ("a", "b", "**/c")


def test_main_exclude_skips_modules_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """--exclude removes matching modules from the real output."""
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    root = tmp_path / "pkg"
    root.mkdir()
    (root / "__init__.py").write_text("", encoding="utf-8")
    (root / "keep.py").write_text("def kept() -> None: ...\n", encoding="utf-8")
    (root / "drop.py").write_text("def dropped() -> None: ...\n", encoding="utf-8")

    exit_code = main([str(root), "--exclude", "drop.py"])

    out = capsys.readouterr().out

    assert exit_code == 0
    assert "kept" in out
    assert "dropped" not in out


def test_main_config_error_returns_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """An invalid configuration file is reported as an error with exit code 1."""
    (tmp_path / ".iceberg.toml").write_text('exclude = "nope"\n', encoding="utf-8")

    exit_code = main([str(tmp_path)])

    assert exit_code == 1
    assert "'exclude' must be a list of strings" in capsys.readouterr().err


def test_main_show_overload_implementations_flag_reaches_format_tree() -> None:
    """--show-overload-implementations asks format_tree for implementation signatures."""
    fake_package = MagicMock()

    with (
        patch("sheridan.iceberg._cli.get_public_api_report", return_value=Report(api=fake_package)),
        patch("sheridan.iceberg._cli.format_tree", return_value=_TREE_OUTPUT) as mock_tree,
    ):
        exit_code = main(["some/path", "--show-overload-implementations"])

    assert exit_code == 0
    mock_tree.assert_called_once_with(fake_package, show_overload_implementation=True)


def test_main_version_prints_installed_version(capsys: pytest.CaptureFixture[str]) -> None:
    """--version prints 'iceberg <version>' from package metadata and exits 0."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out == f"iceberg {version('sheridan-iceberg')}\n"


def _config_passed_to_api(argv: list[str]) -> Config:
    """Run main with get_public_api_report mocked and return the Config it received."""
    with (
        patch("sheridan.iceberg._cli.get_public_api_report", return_value=Report(api=MagicMock())) as mock_api,
        patch("sheridan.iceberg._cli.format_tree", return_value=_TREE_OUTPUT),
    ):
        assert main(argv) == 0

    config = mock_api.call_args.kwargs["config"]

    assert isinstance(config, Config)
    return config


def test_main_config_option_replaces_discovered_file(tmp_path: Path) -> None:
    """--config reads the named file and ignores the one found by walking up."""
    (tmp_path / ".iceberg.toml").write_text('exclude = ["found"]\nmax_workers = 2\n', encoding="utf-8")
    explicit = tmp_path / "other.toml"
    explicit.write_text('exclude = ["explicit"]\n', encoding="utf-8")

    config = _config_passed_to_api([str(tmp_path), "--config", str(explicit)])

    assert config.exclude == ("explicit",)
    assert config.max_workers == 1


def test_main_config_option_reads_pyproject_table(tmp_path: Path) -> None:
    """--config with a pyproject.toml reads its [tool.iceberg] table."""
    project = tmp_path / "elsewhere"
    project.mkdir()
    (project / "pyproject.toml").write_text('[tool.iceberg]\nexclude = ["a"]\n', encoding="utf-8")

    config = _config_passed_to_api([str(tmp_path), "--config", str(project / "pyproject.toml")])

    assert config.exclude == ("a",)


def test_main_config_option_missing_file_returns_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """--config with a path that does not exist is an error with exit code 1."""
    missing = tmp_path / "missing.toml"

    assert main([str(tmp_path), "--config", str(missing)]) == 1
    assert f"Configuration file not found: {missing}" in capsys.readouterr().err


def test_main_no_config_ignores_discovered_file(tmp_path: Path) -> None:
    """--no-config uses the defaults even when a configuration file exists."""
    (tmp_path / ".iceberg.toml").write_text('exclude = ["found"]\nmax_workers = 2\n', encoding="utf-8")

    assert _config_passed_to_api([str(tmp_path), "--no-config"]) == Config()


def test_main_no_config_skips_invalid_file(tmp_path: Path) -> None:
    """--no-config does not read the discovered file, so an invalid one is not an error."""
    (tmp_path / ".iceberg.toml").write_text("not = [valid toml", encoding="utf-8")

    assert _config_passed_to_api([str(tmp_path), "--no-config"]) == Config()


def test_main_config_and_no_config_are_mutually_exclusive(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Passing both --config and --no-config is a usage error."""
    with pytest.raises(SystemExit) as exc_info:
        main([str(tmp_path), "--config", "x.toml", "--no-config"])

    assert exc_info.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err


def test_main_max_workers_overrides_file_value(tmp_path: Path) -> None:
    """--max-workers takes precedence over max_workers in the discovered file."""
    (tmp_path / ".iceberg.toml").write_text("max_workers = 2\n", encoding="utf-8")

    assert _config_passed_to_api([str(tmp_path), "--max-workers", "3"]).max_workers == 3


def test_main_max_workers_overrides_config_option_file(tmp_path: Path) -> None:
    """--max-workers takes precedence over max_workers in the --config file."""
    explicit = tmp_path / "other.toml"
    explicit.write_text("max_workers = 2\n", encoding="utf-8")

    config = _config_passed_to_api([str(tmp_path), "--config", str(explicit), "--max-workers", "4"])

    assert config.max_workers == 4


def test_main_max_workers_with_no_config(tmp_path: Path) -> None:
    """--max-workers applies on top of the defaults when --no-config is given."""
    (tmp_path / ".iceberg.toml").write_text("max_workers = 2\n", encoding="utf-8")

    config = _config_passed_to_api([str(tmp_path), "--no-config", "--max-workers", "5"])

    assert config == Config(max_workers=5)


def test_main_without_max_workers_keeps_file_value(tmp_path: Path) -> None:
    """Without --max-workers, max_workers comes from the configuration file."""
    (tmp_path / ".iceberg.toml").write_text("max_workers = 2\n", encoding="utf-8")

    assert _config_passed_to_api([str(tmp_path)]).max_workers == 2


def test_main_exclude_extends_config_option_file(tmp_path: Path) -> None:
    """--exclude adds to the exclude list from the --config file."""
    explicit = tmp_path / "other.toml"
    explicit.write_text('exclude = ["a"]\n', encoding="utf-8")

    config = _config_passed_to_api([str(tmp_path), "--config", str(explicit), "--exclude", "b"])

    assert config.exclude == ("a", "b")


@pytest.mark.parametrize("value", ["0", "-1", "two", "1.5"])
def test_main_max_workers_rejects_invalid_values(
    value: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--max-workers accepts only integers of at least 1."""
    with pytest.raises(SystemExit) as exc_info:
        main([str(tmp_path), "--max-workers", value])

    assert exc_info.value.code == 2
    assert "expected a positive integer" in capsys.readouterr().err


class TestKeepGoing:
    """``--keep-going`` skips broken modules and prints diagnostics to stderr."""

    @pytest.fixture
    def package(self, tmp_path: Path) -> Path:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text('__all__ = ["good", "lazy"]\n', encoding="utf-8")
        (pkg / "good.py").write_text("def ok() -> None: ...\n", encoding="utf-8")
        (pkg / "vendored.py").write_text("x = 1\nprint 'py2'\n", encoding="utf-8")
        return pkg

    def test_without_keep_going_stops_on_bad_file(self, package: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert main([str(package), "--no-config"]) == 1
        assert capsys.readouterr().out == ""

    def test_keep_going_prints_output_and_diagnostics(self, package: Path, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main([str(package), "--no-config", "--keep-going"])

        captured = capsys.readouterr()

        assert exit_code == 1
        assert "def ok() -> None" in captured.out
        error, warning = captured.err.splitlines()

        assert error.startswith(f"{package / 'vendored.py'}:2: error: ")
        assert warning == f"{package / '__init__.py'}: warning: 'lazy' is exported but never bound"

    def test_keep_going_json_includes_diagnostics(self, package: Path, capsys: pytest.CaptureFixture[str]) -> None:
        main([str(package), "--no-config", "--keep-going", "--json"])

        document = json.loads(capsys.readouterr().out)
        assert [(d["severity"], d["path"]) for d in document["diagnostics"]] == [
            ("error", "vendored.py"),
            ("warning", "__init__.py"),
        ]

    def test_keep_going_with_only_warnings_exits_0(self, package: Path, capsys: pytest.CaptureFixture[str]) -> None:
        (package / "vendored.py").unlink()

        assert main([str(package), "--no-config", "--keep-going"]) == 0
        assert "warning:" in capsys.readouterr().err

    def test_json_without_keep_going_has_no_diagnostics(
        self, package: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (package / "vendored.py").unlink()

        assert main([str(package), "--no-config", "--json"]) == 0
        captured = capsys.readouterr()

        assert "diagnostics" not in json.loads(captured.out)
        assert captured.err == ""


class TestOutput:
    """``-o/--output`` writes the report to a file instead of stdout."""

    @pytest.fixture
    def package(self, tmp_path: Path) -> Path:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text('__all__ = ["greet"]\n\ndef greet() -> str: ...\n', encoding="utf-8")
        return pkg

    @pytest.mark.parametrize("flag", ["-o", "--output"])
    def test_writes_utf8_with_final_newline(
        self, flag: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "api.txt"
        with (
            patch("sheridan.iceberg._cli.get_public_api_report", return_value=Report(api=MagicMock())),
            patch("sheridan.iceberg._cli.format_tree", return_value="package café\n└── módulo"),
        ):
            assert main(["some/path", flag, str(target)]) == 0

        assert target.read_bytes() == "package café\n└── módulo\n".encode()
        assert capsys.readouterr().out == ""

    def test_json_output_matches_stdout(
        self, package: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "api.json"
        main([str(package), "--no-config", "--json"])
        stdout = capsys.readouterr().out

        assert main([str(package), "--no-config", "--json", "-o", str(target)]) == 0
        assert target.read_text(encoding="utf-8") == stdout

    def test_replaces_existing_file(self, package: Path, tmp_path: Path) -> None:
        target = tmp_path / "api.txt"
        target.write_text("old snapshot that is much longer than the new one\n" * 100, encoding="utf-8")

        assert main([str(package), "--no-config", "-o", str(target)]) == 0
        assert "def greet() -> str" in target.read_text(encoding="utf-8")
        assert "old snapshot" not in target.read_text(encoding="utf-8")

    def test_analysis_error_leaves_existing_file_untouched(self, tmp_path: Path) -> None:
        target = tmp_path / "api.txt"
        target.write_text("previous\n", encoding="utf-8")

        assert main([str(tmp_path / "missing"), "--no-config", "-o", str(target)]) == 1
        assert target.read_text(encoding="utf-8") == "previous\n"
        assert list(tmp_path.iterdir()) == [target]

    def test_analysis_error_creates_no_file(self, tmp_path: Path) -> None:
        target = tmp_path / "api.txt"

        assert main([str(tmp_path / "missing"), "--no-config", "-o", str(target)]) == 1
        assert list(tmp_path.iterdir()) == []

    def test_write_error_leaves_no_partial_file(
        self, package: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        target = out_dir / "api.txt"
        target.write_text("previous\n", encoding="utf-8")

        with patch("sheridan.iceberg._cli.os.replace", side_effect=OSError(28, "No space left on device")):
            exit_code = main([str(package), "--no-config", "-o", str(target)])

        assert exit_code == 1
        assert capsys.readouterr().err == f"error: cannot write {target}: No space left on device\n"
        assert list(out_dir.iterdir()) == [target]
        assert target.read_text(encoding="utf-8") == "previous\n"

    def test_missing_directory_returns_1(
        self, package: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "nowhere" / "api.txt"

        assert main([str(package), "--no-config", "-o", str(target)]) == 1
        assert capsys.readouterr().err.startswith(f"error: cannot write {target}: ")
        assert not target.parent.exists()

    def test_new_file_uses_umask_permissions(self, package: Path, tmp_path: Path) -> None:
        target = tmp_path / "api.txt"
        old_umask = os.umask(0o022)
        try:
            assert main([str(package), "--no-config", "-o", str(target)]) == 0
        finally:
            os.umask(old_umask)

        assert stat.S_IMODE(target.stat().st_mode) == 0o644

    def test_existing_file_keeps_its_permissions(self, package: Path, tmp_path: Path) -> None:
        target = tmp_path / "api.txt"
        target.write_text("previous\n", encoding="utf-8")
        target.chmod(0o640)

        assert main([str(package), "--no-config", "-o", str(target)]) == 0
        assert stat.S_IMODE(target.stat().st_mode) == 0o640
        assert "def greet() -> str" in target.read_text(encoding="utf-8")

    def test_symlink_writes_through_to_target(self, package: Path, tmp_path: Path) -> None:
        shared = tmp_path / "shared"
        shared.mkdir()
        real = shared / "api.txt"
        real.write_text("previous\n", encoding="utf-8")
        link = tmp_path / "api.txt"
        link.symlink_to(real)

        assert main([str(package), "--no-config", "-o", str(link)]) == 0
        assert link.is_symlink()
        assert "def greet() -> str" in real.read_text(encoding="utf-8")
        assert sorted(p.name for p in tmp_path.iterdir()) == ["api.txt", "pkg", "shared"]
        assert list(shared.iterdir()) == [real]

    def test_dangling_symlink_creates_its_target(self, package: Path, tmp_path: Path) -> None:
        real = tmp_path / "real.txt"
        link = tmp_path / "api.txt"
        link.symlink_to(real)

        assert main([str(package), "--no-config", "-o", str(link)]) == 0
        assert link.is_symlink()
        assert "def greet() -> str" in real.read_text(encoding="utf-8")

    @pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs named pipes")
    def test_non_regular_file_is_written_directly(self, package: Path, tmp_path: Path) -> None:
        fifo = tmp_path / "api.fifo"
        os.mkfifo(fifo)
        read_fd = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)

        try:
            assert main([str(package), "--no-config", "-o", str(fifo)]) == 0
            received = os.read(read_fd, 65536).decode()
        finally:
            os.close(read_fd)

        assert "def greet() -> str" in received
        assert stat.S_ISFIFO(fifo.stat().st_mode)
        assert sorted(p.name for p in tmp_path.iterdir()) == ["api.fifo", "pkg"]

    def test_keep_going_still_writes_file(
        self, package: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (package / "broken.py").write_text("print 'py2'\n", encoding="utf-8")
        target = tmp_path / "api.txt"

        assert main([str(package), "--no-config", "--keep-going", "-o", str(target)]) == 1
        assert "def greet() -> str" in target.read_text(encoding="utf-8")
        assert "error:" in capsys.readouterr().err
