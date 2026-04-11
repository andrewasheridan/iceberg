"""Functional tests for ``python -m sheridan.iceberg`` CLI entrypoint.

These tests invoke the module via ``subprocess.run`` with ``sys.executable``
and verify exit codes, stdout content, and stderr content against the real
iceberg source package as a fixture.  No mocking is used.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# The iceberg package itself is a well-known real package on disk that the
# subprocess can locate via the installed editable path.  We derive its
# location relative to this file so the tests are portable.
_TESTS_FUNCTIONAL_DIR = Path(__file__).parent
_PROJECT_ROOT = _TESTS_FUNCTIONAL_DIR.parent.parent
_REAL_PACKAGE_PATH = _PROJECT_ROOT / "src" / "sheridan" / "iceberg"


@pytest.fixture(scope="session")
def real_package_path() -> Path:
    """Return the absolute path to the iceberg source package directory."""
    assert _REAL_PACKAGE_PATH.is_dir(), (
        f"Expected a real package at {_REAL_PACKAGE_PATH}; check that the project layout has not changed."
    )
    return _REAL_PACKAGE_PATH


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "sheridan.iceberg", *args],
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# Test 1: tree output, exit code 0
# ---------------------------------------------------------------------------


def test_tree_output_exit_code_zero(real_package_path: Path) -> None:
    """Invoking ``python -m sheridan.iceberg <path>`` produces tree output on
    stdout and exits with code 0."""
    result = _run([str(real_package_path)])

    assert result.returncode == 0, f"Expected exit code 0, got {result.returncode}.\nstderr: {result.stderr!r}"
    assert result.stdout.strip(), "Expected non-empty tree output on stdout."
    # The tree formatter uses box-drawing characters; the package name should
    # appear near the top of the output.
    assert "iceberg" in result.stdout


def test_tree_output_contains_known_public_symbol(real_package_path: Path) -> None:
    """The tree output includes at least one known public symbol from iceberg."""
    result = _run([str(real_package_path)])

    assert result.returncode == 0
    # get_public_api is the primary entry-point and must appear in the tree.
    assert "get_public_api" in result.stdout


# ---------------------------------------------------------------------------
# Test 2: --json flag, exit code 0, valid JSON
# ---------------------------------------------------------------------------


def test_json_output_exit_code_zero(real_package_path: Path) -> None:
    """Invoking with ``--json`` produces parseable JSON on stdout and exits 0."""
    result = _run([str(real_package_path), "--json"])

    assert result.returncode == 0, f"Expected exit code 0, got {result.returncode}.\nstderr: {result.stderr!r}"
    assert result.stdout.strip(), "Expected non-empty JSON output on stdout."


def test_json_output_is_valid_json(real_package_path: Path) -> None:
    """The ``--json`` output must be parseable by ``json.loads``."""
    result = _run([str(real_package_path), "--json"])

    assert result.returncode == 0
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(f"stdout is not valid JSON: {exc}\nraw output: {result.stdout[:500]!r}")

    assert isinstance(parsed, dict), "Top-level JSON value should be a dict (Package)."


def test_json_output_stable_across_two_runs(real_package_path: Path) -> None:
    """Running ``--json`` twice produces identical output (deterministic serialisation)."""
    result_a = _run([str(real_package_path), "--json"])
    result_b = _run([str(real_package_path), "--json"])

    assert result_a.returncode == 0
    assert result_b.returncode == 0
    assert result_a.stdout == result_b.stdout, (
        "JSON output is not stable across two runs — ordering may be non-deterministic."
    )


# ---------------------------------------------------------------------------
# Test 3: non-existent path exits non-zero with error on stderr
# ---------------------------------------------------------------------------


def test_nonexistent_path_exits_nonzero(tmp_path: Path) -> None:
    """Passing a path that does not exist exits with a non-zero code."""
    nonexistent = tmp_path / "definitely_does_not_exist"
    assert not nonexistent.exists()

    result = _run([str(nonexistent)])

    assert result.returncode != 0, "Expected non-zero exit code for a nonexistent path, got 0."


def test_nonexistent_path_writes_error_to_stderr(tmp_path: Path) -> None:
    """Passing a nonexistent path produces an error message on stderr."""
    nonexistent = tmp_path / "definitely_does_not_exist"

    result = _run([str(nonexistent)])

    assert result.returncode != 0
    assert result.stderr.strip(), "Expected an error message on stderr."
    assert "error" in result.stderr.lower(), f"Expected 'error' in stderr, got: {result.stderr!r}"


def test_nonexistent_path_stdout_is_empty(tmp_path: Path) -> None:
    """On failure, stdout should be empty (error goes to stderr only)."""
    nonexistent = tmp_path / "definitely_does_not_exist"

    result = _run([str(nonexistent)])

    assert result.returncode != 0
    assert not result.stdout.strip(), f"Expected empty stdout on failure, got: {result.stdout!r}"


# ---------------------------------------------------------------------------
# Test 4: exit code 1 specifically (IcebergError path)
# ---------------------------------------------------------------------------


def test_nonexistent_path_exits_with_code_1(tmp_path: Path) -> None:
    """A nonexistent path triggers an IcebergError, so the exit code must be 1."""
    nonexistent = tmp_path / "definitely_does_not_exist"

    result = _run([str(nonexistent)])

    assert result.returncode == 1, (
        f"Expected exit code 1 (IcebergError), got {result.returncode}.\nstderr: {result.stderr!r}"
    )
