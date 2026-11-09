"""The JSON Schema in ``docs/schema/`` accepts the ``--json`` output of every case and fixture."""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError

from sheridan.iceberg import get_public_api
from sheridan.iceberg._config import Config
from sheridan.iceberg._formatter import JSON_SCHEMA_VERSION, format_json

_CFG = Config(max_workers=1)
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_CASES = _PROJECT_ROOT / "cases"
_FIXTURES = _PROJECT_ROOT / "tests" / "fixtures"
_SCHEMA_PATH = _PROJECT_ROOT / "docs" / "schema" / "iceberg.schema.json"

_TARGETS: list[Path] = [
    *sorted(path for path in _CASES.iterdir() if path.is_dir()),
    *sorted(_CASES.glob("*/*.py")),
    *sorted(path for path in _FIXTURES.iterdir() if path.is_dir() and path.name != "__pycache__"),
    _PROJECT_ROOT / "src" / "sheridan",
]


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return loaded


@pytest.fixture(scope="module")
def validator(schema: dict[str, Any]) -> Draft202012Validator:
    return Draft202012Validator(schema)


def test_schema_is_valid_draft_2020_12(schema: dict[str, Any]) -> None:
    Draft202012Validator.check_schema(schema)


def test_schema_version_matches_formatter(schema: dict[str, Any]) -> None:
    """Bumping ``JSON_SCHEMA_VERSION`` without updating the schema fails here."""
    assert schema["properties"]["schema_version"]["const"] == JSON_SCHEMA_VERSION


@pytest.mark.parametrize("target", _TARGETS, ids=lambda path: path.relative_to(_PROJECT_ROOT).as_posix())
def test_output_matches_schema(target: Path, validator: Draft202012Validator) -> None:
    document = json.loads(format_json(get_public_api(target, config=_CFG)))

    validator.validate(document)


class TestSchemaRejects:
    """The schema is strict enough to catch drift between it and the formatter."""

    @pytest.fixture
    def document(self) -> dict[str, Any]:
        loaded: dict[str, Any] = json.loads(format_json(get_public_api(_CASES / "case_00", config=_CFG)))
        return loaded

    def test_unknown_top_level_key(self, document: dict[str, Any], validator: Draft202012Validator) -> None:
        document["extra"] = 1

        with pytest.raises(ValidationError):
            validator.validate(document)

    def test_missing_schema_version(self, document: dict[str, Any], validator: Draft202012Validator) -> None:
        del document["schema_version"]

        with pytest.raises(ValidationError):
            validator.validate(document)

    def test_unknown_key_in_nested_module(self, document: dict[str, Any], validator: Draft202012Validator) -> None:
        document["modules"][0]["extra"] = 1

        with pytest.raises(ValidationError):
            validator.validate(document)

    def test_schema_version_on_nested_module(self, document: dict[str, Any], validator: Draft202012Validator) -> None:
        document["modules"][0]["schema_version"] = JSON_SCHEMA_VERSION

        with pytest.raises(ValidationError):
            validator.validate(document)

    def test_unknown_function_kind(self, validator: Draft202012Validator) -> None:
        document = json.loads(format_json(get_public_api(_PROJECT_ROOT / "src" / "sheridan", config=_CFG)))
        function = next(f for module in _all_modules(document) for f in module["functions"])
        function["kind"] = "coroutine"

        with pytest.raises(ValidationError):
            validator.validate(document)


def _all_modules(package: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect every module object in a package object and its subpackages."""
    return [*package["modules"], *(m for sub in package["subpackages"] for m in _all_modules(sub))]
