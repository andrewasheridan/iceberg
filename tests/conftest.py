"""Shared fixtures for sheridan-iceberg tests."""

import textwrap
from pathlib import Path

import pytest


@pytest.fixture()
def tmp_py(tmp_path: Path):
    """Factory fixture that writes a .py file and returns its Path.

    Args:
        tmp_path: pytest built-in temporary directory.

    Returns:
        A callable ``write(filename, source)`` that creates the file and
        returns its :class:`~pathlib.Path`.
    """

    def write(filename: str, source: str) -> Path:
        p = tmp_path / filename
        p.write_text(textwrap.dedent(source), encoding="utf-8")
        return p

    return write
