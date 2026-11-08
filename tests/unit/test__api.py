"""Tests for sheridan.iceberg._api."""

from pathlib import Path

import pytest

from sheridan.iceberg._api import get_public_api
from sheridan.iceberg._exceptions import InvalidPathError


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
