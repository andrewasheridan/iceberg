"""Check the docstring conventions that D401 of ruff cannot check."""

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNED_DIRS = ("src", "tests")
RETURN_VERB = re.compile(r"Returns?\s")

_DocstringOwner = ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef


def _python_files() -> list[Path]:
    files: list[Path] = []

    for directory in SCANNED_DIRS:
        for path in (REPO_ROOT / directory).rglob("*.py"):
            if "__pycache__" not in path.parts:
                files.append(path)

    return sorted(files)


def _return_docstrings(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders = []

    for node in ast.walk(tree):
        if not isinstance(node, _DocstringOwner):
            continue

        docstring = ast.get_docstring(node)
        if docstring and RETURN_VERB.match(docstring):
            line = getattr(node, "lineno", 1)
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}")

    return offenders


@pytest.mark.parametrize("text", ["Return the value.", "Returns the value.", "Return\nmore"])
def test_return_verb_pattern_matches(text: str) -> None:
    assert RETURN_VERB.match(text)


@pytest.mark.parametrize("text", ["Return-type annotations survive.", "Build the value.", "Returned values."])
def test_return_verb_pattern_ignores(text: str) -> None:
    assert not RETURN_VERB.match(text)


def test_no_docstring_starts_with_return() -> None:
    """Use a specific verb (build, find, list, ...), not "Return"."""
    offenders: list[str] = []
    for path in _python_files():
        offenders.extend(_return_docstrings(path))

    assert offenders == [], (
        "Docstrings must not start with 'Return' or 'Returns'. Use a specific "
        "imperative verb (see CONTRIBUTING.md):\n" + "\n".join(offenders)
    )
