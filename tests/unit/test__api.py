"""Tests for sheridan.iceberg._api."""

from pathlib import Path

import pytest

from sheridan.iceberg._api import get_public_api
from sheridan.iceberg._exceptions import InvalidPathError


def test_get_public_api_nonexistent_path_raises_invalid_path_error() -> None:
    nonexistent = Path("/nonexistent/path/that/does/not/exist")
    with pytest.raises(InvalidPathError):
        get_public_api(nonexistent)


def test_get_public_api_existing_directory_raises_not_implemented_error(
    tmp_path: Path,
) -> None:
    with pytest.raises(NotImplementedError):
        get_public_api(tmp_path)
