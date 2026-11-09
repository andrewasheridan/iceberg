"""Test the CLI entry point ``python -m sheridan.iceberg`` from end to end.

These tests run the module through ``subprocess.run`` with ``sys.executable``.
They use the real iceberg source package as the fixture. They examine the exit
codes, the stdout and the stderr. They do not use mocks.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# The iceberg package is a known real package on disk. The subprocess can find
# it through the installed editable path. Its location is relative to this file,
# so that the tests work on all computers.
_TESTS_FUNCTIONAL_DIR = Path(__file__).parent
_PROJECT_ROOT = _TESTS_FUNCTIONAL_DIR.parent.parent
_REAL_PACKAGE_PATH = _PROJECT_ROOT / "src" / "sheridan"


@pytest.fixture(scope="session")
def real_package_path() -> Path:
    """Resolve the absolute path of the iceberg source package directory."""
    assert _REAL_PACKAGE_PATH.is_dir(), (
        f"Expected a real package at {_REAL_PACKAGE_PATH}; check that the project layout has not changed."
    )
    return _REAL_PACKAGE_PATH


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "sheridan.iceberg", *args],
        capture_output=True,
        text=True,
    )


def test_tree_output_exit_code_zero(real_package_path: Path) -> None:
    """``python -m sheridan.iceberg <path>`` writes the tree output to stdout and
    stops with exit code 0."""
    result = _run([str(real_package_path)])

    assert result.returncode == 0, f"Expected exit code 0, got {result.returncode}.\nstderr: {result.stderr!r}"
    assert result.stdout.strip(), "Expected non-empty tree output on stdout."
    # The tree formatter uses box-drawing characters. The package name must be
    # near the top of the output.
    assert "iceberg" in result.stdout


def test_tree_output_contains_known_public_symbol(real_package_path: Path) -> None:
    """The tree output includes at least one known public symbol from iceberg."""
    result = _run([str(real_package_path)])

    assert result.returncode == 0
    # get_public_api is the primary entry point. The tree must show it.
    assert "get_public_api" in result.stdout


def test_json_output_exit_code_zero(real_package_path: Path) -> None:
    """With ``--json``, the CLI writes valid JSON to stdout and stops with exit code 0."""
    result = _run([str(real_package_path), "--json"])

    assert result.returncode == 0, f"Expected exit code 0, got {result.returncode}.\nstderr: {result.stderr!r}"
    assert result.stdout.strip(), "Expected non-empty JSON output on stdout."


def test_json_output_is_valid_json(real_package_path: Path) -> None:
    """``json.loads`` must accept the ``--json`` output."""
    result = _run([str(real_package_path), "--json"])

    assert result.returncode == 0
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(f"stdout is not valid JSON: {exc}\nraw output: {result.stdout[:500]!r}")

    assert isinstance(parsed, dict), "Top-level JSON value should be a dict (Package)."


def test_json_output_stable_across_two_runs(real_package_path: Path) -> None:
    """Two runs with ``--json`` give the same output (deterministic serialization)."""
    result_a = _run([str(real_package_path), "--json"])
    result_b = _run([str(real_package_path), "--json"])

    assert result_a.returncode == 0
    assert result_b.returncode == 0
    assert result_a.stdout == result_b.stdout, (
        "JSON output is not stable across two runs — ordering may be non-deterministic."
    )


def test_nonexistent_path_exits_nonzero(tmp_path: Path) -> None:
    """A path that does not exist gives an exit code that is not zero."""
    nonexistent = tmp_path / "definitely_does_not_exist"
    assert not nonexistent.exists()

    result = _run([str(nonexistent)])

    assert result.returncode != 0, "Expected non-zero exit code for a nonexistent path, got 0."


def test_nonexistent_path_writes_error_to_stderr(tmp_path: Path) -> None:
    """A path that does not exist gives an error message on stderr."""
    nonexistent = tmp_path / "definitely_does_not_exist"

    result = _run([str(nonexistent)])

    assert result.returncode != 0
    assert result.stderr.strip(), "Expected an error message on stderr."
    assert "error" in result.stderr.lower(), f"Expected 'error' in stderr, got: {result.stderr!r}"


def test_nonexistent_path_stdout_is_empty(tmp_path: Path) -> None:
    """If the command fails, stdout is empty. The error goes only to stderr."""
    nonexistent = tmp_path / "definitely_does_not_exist"

    result = _run([str(nonexistent)])

    assert result.returncode != 0
    assert not result.stdout.strip(), f"Expected empty stdout on failure, got: {result.stdout!r}"


def test_nonexistent_path_exits_with_code_1(tmp_path: Path) -> None:
    """A path that does not exist causes an IcebergError. Thus, the exit code must be 1."""
    nonexistent = tmp_path / "definitely_does_not_exist"

    result = _run([str(nonexistent)])

    assert result.returncode == 1, (
        f"Expected exit code 1 (IcebergError), got {result.returncode}.\nstderr: {result.stderr!r}"
    )


def test_json_output_is_identical_for_copies_in_different_directories(tmp_path: Path) -> None:
    """The same package in two different directories gives JSON with the same bytes."""
    fixture = _PROJECT_ROOT / "tests" / "fixtures" / "nested_pkg"
    first = tmp_path / "first" / "nested_pkg"
    second = tmp_path / "second" / "deeper" / "nested_pkg"
    shutil.copytree(fixture, first)
    shutil.copytree(fixture, second)

    first_result = _run([str(first), "--json"])
    second_result = _run([str(second), "--json"])

    assert first_result.returncode == 0, first_result.stderr
    assert second_result.returncode == 0, second_result.stderr
    assert first_result.stdout == second_result.stdout
    assert str(tmp_path) not in first_result.stdout
    parsed = json.loads(first_result.stdout)

    assert parsed["path"] == "."
