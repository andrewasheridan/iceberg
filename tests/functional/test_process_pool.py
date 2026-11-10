"""Test that the process pool gives the same public API as the in-process path for each case."""

from pathlib import Path

import pytest

from sheridan.iceberg import get_public_api
from sheridan.iceberg._config import Config

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_CASES = _PROJECT_ROOT / "cases"
_CASE_DIRS: list[Path] = sorted(path for path in _CASES.iterdir() if path.is_dir())


@pytest.mark.parametrize("case_dir", _CASE_DIRS, ids=lambda path: path.name)
def test_process_pool_matches_in_process(case_dir: Path) -> None:
    """Snapshot the case with ``max_workers=1`` and ``max_workers=2``, and compare the two results."""
    in_process = get_public_api(case_dir, config=Config(max_workers=1))
    pooled = get_public_api(case_dir, config=Config(max_workers=2))

    assert pooled == in_process
