"""Tests for sheridan.iceberg public API surface (__init__.py)."""

import sheridan.iceberg as iceberg
from sheridan.iceberg import check_api, fix_api, get_public_api


class TestPublicApi:
    def test_all_exports_are_importable(self) -> None:
        for name in iceberg.__all__:
            assert hasattr(iceberg, name), f"{name} not found on sheridan.iceberg"

    def test_all_list_contents(self) -> None:
        assert set(iceberg.__all__) == {
            "check_api",
            "fix_api",
            "get_public_api",
        }

    def test_get_public_api_is_exported(self) -> None:
        assert get_public_api is iceberg.get_public_api

    def test_check_api_is_exported(self) -> None:
        assert check_api is iceberg.check_api

    def test_fix_api_is_exported(self) -> None:
        assert fix_api is iceberg.fix_api
