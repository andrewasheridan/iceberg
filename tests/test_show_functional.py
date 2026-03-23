"""Functional (golden-file) tests for the ``iceberg show`` command.

Each test class targets one fixture package or module.  The actual CLI output
is compared byte-for-byte against pre-written golden files stored in
``tests/expected/show/``.

For JSON tests the ``path`` field is replaced with ``"__PATH__"`` before
comparison because filesystem paths are not semantically meaningful.
"""

__all__ = [
    "TestGeometryShow",
    "TestStandaloneShow",
    "TestTodoShow",
    "TestWarehouseShow",
]

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from sheridan.iceberg import cli

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_TESTS_DIR: Path = Path(__file__).parent
_FIXTURES_DIR: Path = _TESTS_DIR / "examples"
_GOLDEN_DIR: Path = _TESTS_DIR / "expected" / "show"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(args: list[str], capsys: pytest.CaptureFixture[str]) -> int:
    """Run main() with the given argv, capture output, and return exit code.

    Args:
        args: CLI arguments that follow the ``iceberg`` program name.
        capsys: pytest capsys fixture used by the caller to capture output.

    Returns:
        The integer exit code produced by ``cli.main()``.
    """
    sys.argv = ["iceberg", *args]
    exit_code = 0
    try:
        cli.main()
    except SystemExit as exc:
        exit_code = int(exc.code) if exc.code is not None else 0
    return exit_code


def _load_golden(name: str) -> str:
    """Return the content of tests/expected/show/<name>.

    Args:
        name: The filename inside ``tests/expected/show/``.

    Returns:
        The file contents as a string.
    """
    return (_GOLDEN_DIR / name).read_text(encoding="utf-8")


def _mask_paths(json_text: str) -> str:
    """Replace all 'path' values in a show JSON output with '__PATH__'.

    Parses the JSON array produced by ``iceberg show --format json``, sets
    every top-level entry's ``"path"`` key to ``"__PATH__"``, then
    re-serialises with two-space indentation so the result can be compared
    to the golden file.

    Args:
        json_text: The raw JSON string captured from stdout.

    Returns:
        A normalised JSON string with paths masked.
    """
    entries: list[dict[str, Any]] = json.loads(json_text)
    for entry in entries:
        if "path" in entry:
            entry["path"] = "__PATH__"
    return json.dumps(entries, indent=2)


# ---------------------------------------------------------------------------
# TestStandaloneShow
# ---------------------------------------------------------------------------


class TestStandaloneShow:
    """Golden-file tests for a single-file module with __all__.

    ``standalone.py`` exercises every member kind: class variables, instance
    attributes, properties, instance methods, classmethods, staticmethods, and
    top-level functions with keyword-only parameters.
    """

    def test_tree_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Tree output for standalone.py matches the golden file exactly.

        Demonstrates all member kinds in a single-file module: class vars,
        instance attrs, properties, methods, classmethods, staticmethods, and
        a top-level function with a keyword-only param with default.
        """
        fixture = str(_FIXTURES_DIR / "standalone.py")
        exit_code = _run(["show", fixture], capsys)
        captured = capsys.readouterr()

        assert exit_code == 0
        assert captured.out == _load_golden("standalone_tree.txt")

    def test_json_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """JSON output for standalone.py matches the golden file after path masking.

        Verifies the full detail structure: class with bases, member list per
        kind, and top-level function with keyword-only param.
        """
        fixture = str(_FIXTURES_DIR / "standalone.py")
        exit_code = _run(["show", "--format", "json", fixture], capsys)
        captured = capsys.readouterr()

        assert exit_code == 0
        masked = _mask_paths(captured.out)
        assert masked == _load_golden("standalone_json.json").rstrip("\n")


# ---------------------------------------------------------------------------
# TestGeometryShow
# ---------------------------------------------------------------------------


class TestGeometryShow:
    """Golden-file tests for the geometry package.

    ``geometry/__init__.py`` declares ``__all__``.  Without ``--use-ast``
    only ``__init__`` is reported; with ``--use-ast`` all four submodules
    are reported with full member detail.
    """

    def test_tree_output_with_all(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Tree output without --use-ast shows only __init__ because __all__ is set.

        Demonstrates that __all__ in __init__.py is authoritative for the
        whole package: submodules (point, shapes, utils) are suppressed.
        """
        fixture = str(_FIXTURES_DIR / "geometry")
        exit_code = _run(["show", fixture], capsys)
        captured = capsys.readouterr()

        assert exit_code == 0
        assert captured.out == _load_golden("geometry_tree.txt")

    def test_json_output_with_all(self, capsys: pytest.CaptureFixture[str]) -> None:
        """JSON output without --use-ast has one entry with empty detail.

        The names are re-exported imports, not definitions, so detail is empty
        even though the names appear in __all__.
        """
        fixture = str(_FIXTURES_DIR / "geometry")
        exit_code = _run(["show", "--format", "json", fixture], capsys)
        captured = capsys.readouterr()

        assert exit_code == 0
        masked = _mask_paths(captured.out)
        assert masked == _load_golden("geometry_json.json").rstrip("\n")

    def test_tree_output_use_ast(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Tree output with --use-ast shows all four submodules with full detail.

        Demonstrates that --use-ast bypasses the __all__ suppression: point,
        shapes, and utils are each reported with their own public API surface.
        """
        fixture = str(_FIXTURES_DIR / "geometry")
        exit_code = _run(["show", "--use-ast", fixture], capsys)
        captured = capsys.readouterr()

        assert exit_code == 0
        assert captured.out == _load_golden("geometry_use_ast_tree.txt")

    def test_json_output_use_ast(self, capsys: pytest.CaptureFixture[str]) -> None:
        """JSON output with --use-ast has four entries, each with rich detail."""
        fixture = str(_FIXTURES_DIR / "geometry")
        exit_code = _run(["show", "--use-ast", "--format", "json", fixture], capsys)
        captured = capsys.readouterr()

        assert exit_code == 0
        masked = _mask_paths(captured.out)
        assert masked == _load_golden("geometry_use_ast_json.json").rstrip("\n")


# ---------------------------------------------------------------------------
# TestWarehouseShow
# ---------------------------------------------------------------------------


class TestWarehouseShow:
    """Golden-file tests for the warehouse package.

    ``warehouse/__init__.py`` has no ``__all__``.  All three submodules
    (__init__, models, utils) are always reported, each using their own
    public API surface.
    """

    def test_tree_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Tree output shows all three submodules because __init__.py has no __all__.

        Demonstrates per-module reporting when the package root omits __all__:
        models and utils are shown with their own member detail.
        """
        fixture = str(_FIXTURES_DIR / "warehouse")
        exit_code = _run(["show", fixture], capsys)
        captured = capsys.readouterr()

        assert exit_code == 0
        assert captured.out == _load_golden("warehouse_tree.txt")

    def test_json_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """JSON output has three entries with rich detail for models and utils.

        Verifies that Product (class with TAX_RATE, properties, classmethod,
        staticmethod) and Warehouse are fully described, and that the two
        utility functions in utils appear with their signatures.
        """
        fixture = str(_FIXTURES_DIR / "warehouse")
        exit_code = _run(["show", "--format", "json", fixture], capsys)
        captured = capsys.readouterr()

        assert exit_code == 0
        masked = _mask_paths(captured.out)
        assert masked == _load_golden("warehouse_json.json").rstrip("\n")


# ---------------------------------------------------------------------------
# TestTodoShow
# ---------------------------------------------------------------------------


class TestTodoShow:
    """Golden-file tests for a single-file module with zero type annotations.

    ``todo.py`` demonstrates how ``show`` renders an entirely untyped module:
    attributes appear as bare names with no ``: type``, callables appear with
    no ``→ return``, and parameters carry no annotation.
    """

    def test_tree_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Tree output for todo.py matches the golden file exactly.

        Demonstrates zero-annotation rendering: every name appears bare,
        no ': type' on attributes, no '→ return' on any callable.
        """
        fixture = str(_FIXTURES_DIR / "todo.py")
        exit_code = _run(["show", fixture], capsys)
        captured = capsys.readouterr()

        assert exit_code == 0
        assert captured.out == _load_golden("todo_tree.txt")

    def test_json_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """JSON output for todo.py matches the golden file after path masking.

        Verifies that annotation fields are null throughout and no
        return_annotation appears on any member.
        """
        fixture = str(_FIXTURES_DIR / "todo.py")
        exit_code = _run(["show", "--format", "json", fixture], capsys)
        captured = capsys.readouterr()

        assert exit_code == 0
        masked = _mask_paths(captured.out)
        assert masked == _load_golden("todo_json.json").rstrip("\n")
