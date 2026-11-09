"""Tests that keep the docs site in step with the ``cases/`` directory."""

import tomllib
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_CASES = sorted(path.name for path in (_PROJECT_ROOT / "cases").glob("case_*") if path.is_dir())


def _nav_pages(entries: list[dict[str, object]]) -> set[str]:
    pages: set[str] = set()

    for entry in entries:
        for value in entry.values():
            if isinstance(value, str):
                pages.add(value)
            elif isinstance(value, list):
                pages |= _nav_pages(value)

    return pages


_NAV_PAGES = _nav_pages(tomllib.loads((_PROJECT_ROOT / "zensical.toml").read_text(encoding="utf-8"))["project"]["nav"])


def test_index_includes_the_readme() -> None:
    """The home page must include the README, so that the two cannot differ."""
    index = _PROJECT_ROOT / "docs" / "index.md"

    assert index.read_text(encoding="utf-8") == '--8<-- "README.md"\n'


@pytest.mark.parametrize("case", _CASES)
def test_case_has_a_docs_page(case: str) -> None:
    """Each case must have a page that includes its README."""
    page = _PROJECT_ROOT / "docs" / "cases" / f"{case}.md"

    assert page.is_file(), f"Add {page.relative_to(_PROJECT_ROOT)}"
    assert page.read_text(encoding="utf-8") == f'--8<-- "cases/{case}/README.md"\n'


@pytest.mark.parametrize("case", _CASES)
def test_case_is_in_the_nav(case: str) -> None:
    assert f"cases/{case}.md" in _NAV_PAGES, f"Add cases/{case}.md to the nav in zensical.toml"
