"""Tests for sheridan.iceberg public API surface (__init__.py)."""

import re

import sheridan.iceberg as iceberg
from sheridan.iceberg import get_public_api


class TestPublicApi:
    def test_all_exports_are_importable(self) -> None:
        for name in iceberg.__all__:
            assert hasattr(iceberg, name), f"{name} not found on sheridan.iceberg"

    def test_all_list_contents(self) -> None:
        assert set(iceberg.__all__) == {
            "__version__",
            "get_public_api",
        }

    def test_get_public_api_is_exported(self) -> None:
        assert get_public_api is iceberg.get_public_api

    def test_version_is_str(self) -> None:
        assert isinstance(iceberg.__version__, str)

    def test_version_value(self) -> None:
        version = iceberg.__version__
        is_semver = bool(re.match(r"^\d+\.\d+\.\d+", version))
        is_fallback = version == "0.0.0+unknown"
        assert is_semver or is_fallback, f"unexpected __version__: {version!r}"
