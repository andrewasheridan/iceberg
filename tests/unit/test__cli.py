"""Tests for sheridan.iceberg._cli."""

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
    mock_tree.assert_called_once_with(fake_package)
    mock_json.assert_not_called()


def test_main_success_tree_uses_path_argument(capsys: pytest.CaptureFixture[str]) -> None:
    """main passes the path argument as a Path object to get_public_api."""
    from pathlib import Path

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
