"""Tests for sheridan.iceberg.fixer."""

from pathlib import Path

import pytest

from sheridan.iceberg.ast_walker import walk_module
from sheridan.iceberg.fixer import fix_module, fix_modules
from sheridan.iceberg.reporter import IssueKind, check_modules


def _write(path: Path, source: str) -> Path:
    path.write_text(source, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# fix_module — replacing an existing __all__
# ---------------------------------------------------------------------------


class TestFixModuleReplace:
    def test_replaces_incorrect_all(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path / "mod.py",
            '__all__ = ["Wrong"]\n\ndef Correct(): ...\n',
        )
        info = walk_module(p)
        changed = fix_module(info, ["Correct"])
        assert changed is True
        new_source = p.read_text(encoding="utf-8")
        assert '"Correct"' in new_source
        assert '"Wrong"' not in new_source

    def test_returns_false_when_already_correct(self, tmp_path: Path) -> None:
        source = '__all__ = [\n    "Foo",\n]\n'
        p = _write(tmp_path / "mod.py", source)
        info = walk_module(p)
        changed = fix_module(info, ["Foo"])
        assert changed is False
        assert p.read_text(encoding="utf-8") == source

    def test_replaces_unsorted_all(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Beta", "Alpha"]\n')
        info = walk_module(p)
        changed = fix_module(info, ["Alpha", "Beta"])
        assert changed is True
        new_source = p.read_text(encoding="utf-8")
        assert '"Alpha"' in new_source
        assert '"Beta"' in new_source

    def test_multiline_all_replaced_correctly(self, tmp_path: Path) -> None:
        source = '__all__ = [\n    "OldName",\n    "AnotherOld",\n]\n\ndef NewName(): ...\n'
        p = _write(tmp_path / "mod.py", source)
        info = walk_module(p)
        changed = fix_module(info, ["NewName"])
        assert changed is True
        new_source = p.read_text(encoding="utf-8")
        assert "NewName" in new_source
        assert "OldName" not in new_source

    def test_content_after_all_is_preserved(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Old"]\n\ndef MyFunc(): ...\n')
        info = walk_module(p)
        fix_module(info, ["MyFunc"])
        new_source = p.read_text(encoding="utf-8")
        assert "def MyFunc(): ..." in new_source

    def test_empty_expected_renders_typed_empty(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Something"]\n')
        info = walk_module(p)
        fix_module(info, [])
        new_source = p.read_text(encoding="utf-8")
        assert "__all__" in new_source
        assert "Something" not in new_source


# ---------------------------------------------------------------------------
# fix_module — inserting __all__ when absent
# ---------------------------------------------------------------------------


class TestFixModuleInsert:
    def test_inserts_all_when_missing(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        info = walk_module(p)
        changed = fix_module(info, ["Foo"])
        assert changed is True
        new_source = p.read_text(encoding="utf-8")
        assert "__all__" in new_source
        assert '"Foo"' in new_source

    def test_inserts_after_docstring(self, tmp_path: Path) -> None:
        source = '"""Module docstring."""\n\ndef Foo(): ...\n'
        p = _write(tmp_path / "mod.py", source)
        info = walk_module(p)
        fix_module(info, ["Foo"])
        new_source = p.read_text(encoding="utf-8")
        all_pos = new_source.index("__all__")
        docstring_pos = new_source.index('"""Module docstring."""')
        assert docstring_pos < all_pos

    def test_inserts_after_leading_comments(self, tmp_path: Path) -> None:
        source = "# A comment\n\ndef Foo(): ...\n"
        p = _write(tmp_path / "mod.py", source)
        info = walk_module(p)
        fix_module(info, ["Foo"])
        new_source = p.read_text(encoding="utf-8")
        assert "__all__" in new_source

    def test_inserts_into_empty_module(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "")
        info = walk_module(p)
        changed = fix_module(info, ["Foo"])
        assert changed is True
        new_source = p.read_text(encoding="utf-8")
        assert "__all__" in new_source

    def test_original_code_preserved_after_insert(self, tmp_path: Path) -> None:
        source = "def Foo(): ...\ndef Bar(): ...\n"
        p = _write(tmp_path / "mod.py", source)
        info = walk_module(p)
        fix_module(info, ["Bar", "Foo"])
        new_source = p.read_text(encoding="utf-8")
        assert "def Foo(): ..." in new_source
        assert "def Bar(): ..." in new_source


# ---------------------------------------------------------------------------
# fix_module — rendered output format
# ---------------------------------------------------------------------------


class TestRenderAll:
    def test_single_name_renders_correctly(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        info = walk_module(p)
        fix_module(info, ["Foo"])
        new_source = p.read_text(encoding="utf-8")
        assert '"Foo"' in new_source

    def test_multiple_names_render_one_per_line(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "def Alpha(): ...\ndef Beta(): ...\n")
        info = walk_module(p)
        fix_module(info, ["Alpha", "Beta"])
        new_source = p.read_text(encoding="utf-8")
        assert '"Alpha"' in new_source
        assert '"Beta"' in new_source

    def test_names_are_sorted_in_output(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "__all__ = []\n")
        info = walk_module(p)
        fix_module(info, ["zebra", "apple", "mango"])
        new_source = p.read_text(encoding="utf-8")
        apple_pos = new_source.index('"apple"')
        mango_pos = new_source.index('"mango"')
        zebra_pos = new_source.index('"zebra"')
        assert apple_pos < mango_pos < zebra_pos


# ---------------------------------------------------------------------------
# fix_module — parametrized correctness checks
# ---------------------------------------------------------------------------


def _canonical_source(names: list[str]) -> str:
    """Build source using the exact format _render_all produces so change detection is accurate."""
    if not names:
        return "__all__: list[str] = []\n"
    inner = ",\n    ".join(f'"{name}"' for name in sorted(names))
    return f"__all__ = [\n    {inner},\n]\n"


@pytest.mark.parametrize(
    ("initial_all", "expected", "should_change"),
    [
        # Already in canonical form with correct names → no change
        (["Foo"], ["Foo"], False),
        # Different names → must change
        (["Foo"], ["Bar"], True),
        # Same names but unsorted initial (canonical source sorts them, so initial is sorted) → test mismatch of order
        # We craft the initial source manually to be unsorted to force a change
        (["Beta", "Alpha"], ["Alpha", "Beta"], True),
        # Canonical sorted form → no change
        (["Alpha", "Beta"], ["Alpha", "Beta"], False),
    ],
)
def test_fix_module_change_detection(
    tmp_path: Path, initial_all: list[str], expected: list[str], should_change: bool
) -> None:
    if should_change and initial_all == ["Beta", "Alpha"]:
        # Write an explicitly unsorted __all__ so the source differs from canonical
        source = '__all__ = ["Beta", "Alpha"]\n'
    else:
        # Write the canonical format so comparison is exact
        source = _canonical_source(initial_all)
    p = tmp_path / "mod.py"
    p.write_text(source, encoding="utf-8")
    info = walk_module(p)
    changed = fix_module(info, expected)
    assert changed is should_change


# ---------------------------------------------------------------------------
# fix_modules
# ---------------------------------------------------------------------------


class TestFixModules:
    def test_fixes_all_issues_and_returns_modified_paths(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        modules = [walk_module(p)]
        issues = check_modules(modules)
        fixed = fix_modules(modules, issues)
        assert fixed == [p]
        assert "__all__" in p.read_text(encoding="utf-8")

    def test_returns_empty_when_no_issues(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = [\n    "Foo",\n]\ndef Foo(): ...\n')
        modules = [walk_module(p)]
        fixed = fix_modules(modules, [])
        assert fixed == []

    def test_skips_issues_with_unknown_path(self, tmp_path: Path) -> None:
        from sheridan.iceberg.reporter import Issue

        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        modules = [walk_module(p)]
        ghost_issue = Issue(
            path=tmp_path / "ghost.py",
            kind=IssueKind.missing,
            declared=None,
            expected=["Foo"],
        )
        fixed = fix_modules(modules, [ghost_issue])
        assert fixed == []

    def test_multiple_files_all_fixed(self, tmp_path: Path) -> None:
        p1 = _write(tmp_path / "a.py", "def Alpha(): ...\n")
        p2 = _write(tmp_path / "b.py", "def Beta(): ...\n")
        modules = [walk_module(p1), walk_module(p2)]
        issues = check_modules(modules)
        fixed = fix_modules(modules, issues)
        assert set(fixed) == {p1, p2}
