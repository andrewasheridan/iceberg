"""Provide the fixtures that the iceberg tests share."""

import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture
def tmp_py(tmp_path: Path) -> Callable[[str, str], Path]:
    """Provide a factory fixture that writes a .py file and gives its Path.

    Args:
        tmp_path: The built-in temporary directory of pytest.

    Returns:
        A callable ``write(filename, source)``. It makes the file and gives
        its :class:`~pathlib.Path`.
    """

    def write(filename: str, source: str) -> Path:
        p = tmp_path / filename
        p.write_text(textwrap.dedent(source), encoding="utf-8")
        return p

    return write
