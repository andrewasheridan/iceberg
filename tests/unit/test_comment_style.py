"""Fail if a source or configuration file has a banner comment.

A banner is a comment line made only of ``#`` and ten or more ``-`` or ``=``. It is
usually around a section title. Banners add noise and become out of date. Thus, they
are not permitted. The same pattern runs as a ``pygrep`` hook in
``.pre-commit-config.yaml``. Keep the two patterns the same.

This test scans the tree. It does not call ``git ls-files``, because the CI container
has no ``git``.
"""

import re
from collections.abc import Iterator
from pathlib import Path

import pytest

BANNER = re.compile(r"^\s*#\s*[-=]{10,}\s*$")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUFFIXES = frozenset({".py", ".pyi", ".toml", ".yaml", ".yml", ".sh"})
_SKIP_DIRS = frozenset({"__pycache__", "node_modules", "site", "build", "dist", "mutants"})
_ALLOWED_DOT_DIRS = frozenset({".github"})


def _is_skipped_dir(name: str) -> bool:
    """Check if a directory name is a cache, build output or hidden directory."""
    if name in _SKIP_DIRS:
        return True

    return name.startswith(".") and name not in _ALLOWED_DOT_DIRS


def _source_files(root: Path) -> Iterator[Path]:
    """Yield the files below *root* to scan. Skip virtualenvs, caches and build output."""
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in _SUFFIXES:
            continue

        dirs = path.relative_to(root).parts[:-1]
        if any(_is_skipped_dir(d) for d in dirs):
            continue

        yield path


def _banner_lines(paths: Iterator[Path], root: Path) -> list[str]:
    """Collect ``path:line: text`` for each banner line in *paths*."""
    hits: list[str] = []

    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")

        for lineno, line in enumerate(text.splitlines(), start=1):
            if BANNER.match(line):
                hits.append(f"{path.relative_to(root)}:{lineno}: {line.strip()}")

    return hits


@pytest.mark.parametrize(
    "line",
    [
        "# " + "-" * 75,
        "    # " + "-" * 24,
        "#" + "=" * 40,
        "# ----------  ",
    ],
)
def test_banner_pattern_matches_divider_lines(line: str) -> None:
    assert BANNER.match(line)


@pytest.mark.parametrize(
    "line",
    [
        "# A plain comment.",
        "# --- short ---",
        "# ---------",
        'x = "# ' + "-" * 20 + '"',
        "# " + "-" * 20 + " Title " + "-" * 20,
    ],
)
def test_banner_pattern_ignores_other_lines(line: str) -> None:
    assert not BANNER.match(line)


def test_scan_reports_banner_and_skips_hidden_dirs(tmp_path: Path) -> None:
    rule = "# " + "-" * 30
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text(f"x = 1\n{rule}\n# Section\n{rule}\n")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "dep.py").write_text(f"{rule}\n")
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "ci.yaml").write_text(f"{rule}\n")

    hits = _banner_lines(_source_files(tmp_path), tmp_path)

    assert hits == [
        f"{Path('.github/ci.yaml')}:1: {rule}",
        f"{Path('pkg/mod.py')}:2: {rule}",
        f"{Path('pkg/mod.py')}:4: {rule}",
    ]


def test_repository_has_no_banner_comments() -> None:
    hits = _banner_lines(_source_files(_REPO_ROOT), _REPO_ROOT)

    assert not hits, "Banner comments are not allowed (see CLAUDE.md):\n" + "\n".join(hits)
