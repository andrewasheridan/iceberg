"""Test the round trip: ``load_json(format_json(api))`` makes ``api`` again for each case and fixture."""

from pathlib import Path

import pytest

from sheridan.iceberg import Package, get_public_api, load_json
from sheridan.iceberg._config import Config
from sheridan.iceberg._formatter import format_json

_CFG = Config(max_workers=1)
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_CASES = _PROJECT_ROOT / "cases"
_FIXTURES = _PROJECT_ROOT / "tests" / "fixtures"

_TARGETS: list[Path] = [
    *sorted(path for path in _CASES.iterdir() if path.is_dir()),
    *sorted(_CASES.glob("*/*.py")),
    *sorted(path for path in _FIXTURES.iterdir() if path.is_dir() and path.name != "__pycache__"),
    _PROJECT_ROOT / "src" / "sheridan",
]


@pytest.mark.parametrize("target", _TARGETS, ids=lambda path: path.relative_to(_PROJECT_ROOT).as_posix())
def test_load_json_round_trips(target: Path) -> None:
    api = get_public_api(target, config=_CFG)
    root = api.path if isinstance(api, Package) else None

    assert load_json(format_json(api), root=root) == api


@pytest.mark.parametrize("target", _TARGETS, ids=lambda path: path.relative_to(_PROJECT_ROOT).as_posix())
def test_reformatting_loaded_json_is_identical(target: Path) -> None:
    """Without a root, the paths stay relative, but the JSON has the same bytes."""
    text = format_json(get_public_api(target, config=_CFG))

    assert format_json(load_json(text)) == text
