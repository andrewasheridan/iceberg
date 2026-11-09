"""Tests for sheridan.iceberg._cli."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sheridan.iceberg._cli import main
from sheridan.iceberg._exceptions import IcebergError, InvalidPathError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TREE_OUTPUT = "package mypackage\n└── module mymodule"
_JSON_OUTPUT = '{\n  "name": "mypackage"\n}'


# ---------------------------------------------------------------------------
# Success path — tree format (default)
# ---------------------------------------------------------------------------


def test_main_success_tree_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """main returns 0 and writes tree output to stdout."""
    fake_package = MagicMock()

    with (
        patch("sheridan.iceberg._cli.get_public_api", return_value=fake_package) as mock_api,
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
    """main passes the path argument as a Path object to get_public_api."""

    fake_package = MagicMock()

    with (
        patch("sheridan.iceberg._cli.get_public_api", return_value=fake_package) as mock_api,
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
        patch("sheridan.iceberg._cli.get_public_api", return_value=fake_package),
        patch("sheridan.iceberg._cli.format_tree", return_value=_TREE_OUTPUT),
    ):
        main(["some/path"])

    captured = capsys.readouterr()
    assert captured.err == ""


# ---------------------------------------------------------------------------
# Success path — JSON format (--json flag)
# ---------------------------------------------------------------------------


def test_main_json_flag_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """main returns 0 and writes JSON output to stdout when --json is passed."""
    fake_package = MagicMock()

    with (
        patch("sheridan.iceberg._cli.get_public_api", return_value=fake_package) as mock_api,
        patch("sheridan.iceberg._cli.format_json", return_value=_JSON_OUTPUT) as mock_json,
        patch("sheridan.iceberg._cli.format_tree") as mock_tree,
    ):
        exit_code = main(["some/path", "--json"])

    assert exit_code == 0

    captured = capsys.readouterr()
    assert _JSON_OUTPUT in captured.out
    assert captured.err == ""

    mock_api.assert_called_once()
    mock_json.assert_called_once_with(fake_package)
    mock_tree.assert_not_called()


def test_main_json_flag_stderr_is_empty(capsys: pytest.CaptureFixture[str]) -> None:
    """On success with --json, nothing is written to stderr."""
    fake_package = MagicMock()

    with (
        patch("sheridan.iceberg._cli.get_public_api", return_value=fake_package),
        patch("sheridan.iceberg._cli.format_json", return_value=_JSON_OUTPUT),
    ):
        main(["some/path", "--json"])

    captured = capsys.readouterr()
    assert captured.err == ""


# ---------------------------------------------------------------------------
# Error path — IcebergError (exit code 1)
# ---------------------------------------------------------------------------


def test_main_iceberg_error_returns_1(capsys: pytest.CaptureFixture[str]) -> None:
    """main returns 1 when get_public_api raises an IcebergError."""
    with patch(
        "sheridan.iceberg._cli.get_public_api",
        side_effect=InvalidPathError("path does not exist: /bad/path"),
    ):
        exit_code = main(["/bad/path"])

    assert exit_code == 1


def test_main_iceberg_error_message_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    """main writes 'error: <msg>' to stderr on IcebergError."""
    error_msg = "path does not exist: /bad/path"

    with patch(
        "sheridan.iceberg._cli.get_public_api",
        side_effect=InvalidPathError(error_msg),
    ):
        main(["/bad/path"])

    captured = capsys.readouterr()
    assert f"error: {error_msg}" in captured.err
    assert captured.out == ""


def test_main_iceberg_error_nothing_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """On IcebergError, nothing is written to stdout."""
    with patch(
        "sheridan.iceberg._cli.get_public_api",
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
    with patch("sheridan.iceberg._cli.get_public_api", side_effect=exc):
        exit_code = main(["any/path"])

    assert exit_code == 1


# ---------------------------------------------------------------------------
# Error path — unexpected exception (exit code 2)
# ---------------------------------------------------------------------------


def test_main_unexpected_error_returns_2(capsys: pytest.CaptureFixture[str]) -> None:
    """main returns 2 when get_public_api raises an unexpected exception."""
    with patch(
        "sheridan.iceberg._cli.get_public_api",
        side_effect=RuntimeError("something went very wrong"),
    ):
        exit_code = main(["any/path"])

    assert exit_code == 2


def test_main_unexpected_error_message_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    """main writes 'unexpected error: <type>: <msg>' to stderr on unexpected exceptions."""
    with patch(
        "sheridan.iceberg._cli.get_public_api",
        side_effect=RuntimeError("something went very wrong"),
    ):
        main(["any/path"])

    captured = capsys.readouterr()
    assert "unexpected error: RuntimeError: something went very wrong" in captured.err
    assert captured.out == ""


def test_main_unexpected_error_nothing_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """On an unexpected exception, nothing is written to stdout."""
    with patch(
        "sheridan.iceberg._cli.get_public_api",
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
    with patch("sheridan.iceberg._cli.get_public_api", side_effect=exc):
        exit_code = main(["any/path"])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert expected_type_name in captured.err


# ---------------------------------------------------------------------------
# argv defaults to sys.argv[1:] when None
# ---------------------------------------------------------------------------


def test_main_argv_none_reads_sys_argv(capsys: pytest.CaptureFixture[str]) -> None:
    """When argv is None, main reads from sys.argv[1:]."""
    fake_package = MagicMock()

    with (
        patch("sys.argv", ["iceberg", "some/path"]),
        patch("sheridan.iceberg._cli.get_public_api", return_value=fake_package) as mock_api,
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


# ---------------------------------------------------------------------------
# Source files that cannot be read or decoded (real files, no mocks)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# --exclude
# ---------------------------------------------------------------------------


def test_main_exclude_extends_configured_list(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Repeated --exclude options are appended to the configured exclude list."""
    (tmp_path / "pyproject.toml").write_text('[tool.iceberg]\nexclude = ["a"]\n', encoding="utf-8")

    with (
        patch("sheridan.iceberg._cli.get_public_api", return_value=MagicMock()) as mock_api,
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
        patch("sheridan.iceberg._cli.get_public_api", return_value=fake_package),
        patch("sheridan.iceberg._cli.format_tree", return_value=_TREE_OUTPUT) as mock_tree,
    ):
        exit_code = main(["some/path", "--show-overload-implementations"])

    assert exit_code == 0
    mock_tree.assert_called_once_with(fake_package, show_overload_implementation=True)
