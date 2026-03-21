"""Tests for sheridan.iceberg.ast_walker."""

from pathlib import Path

import pytest

from sheridan.iceberg.ast_walker import ModuleInfo, walk_module, walk_path

# ---------------------------------------------------------------------------
# ModuleInfo
# ---------------------------------------------------------------------------


class TestModuleInfoEffectiveAll:
    def test_uses_declared_when_present(self, tmp_path: Path) -> None:
        info = ModuleInfo(
            path=tmp_path / "m.py",
            declared_all=["Foo", "Bar"],
            inferred_all=["Baz"],
        )
        assert info.effective_all == ["Foo", "Bar"]

    def test_uses_inferred_when_declared_is_none(self, tmp_path: Path) -> None:
        info = ModuleInfo(
            path=tmp_path / "m.py",
            declared_all=None,
            inferred_all=["Baz"],
        )
        assert info.effective_all == ["Baz"]

    def test_uses_empty_declared_over_inferred(self, tmp_path: Path) -> None:
        info = ModuleInfo(
            path=tmp_path / "m.py",
            declared_all=[],
            inferred_all=["Baz"],
        )
        assert info.effective_all == []

    def test_inferred_all_defaults_to_empty_list(self, tmp_path: Path) -> None:
        info = ModuleInfo(path=tmp_path / "m.py", declared_all=None)
        assert info.inferred_all == []


# ---------------------------------------------------------------------------
# walk_module — happy paths
# ---------------------------------------------------------------------------


class TestWalkModuleHappyPaths:
    def test_extracts_declared_all_list(self, tmp_py) -> None:  # type: ignore[no-untyped-def]
        p = tmp_py(
            "mod.py",
            """\
            __all__ = ["Alpha", "Beta"]

            def Alpha(): ...
            def Beta(): ...
            """,
        )
        info = walk_module(p)
        assert info.declared_all == ["Alpha", "Beta"]

    def test_extracts_declared_all_tuple(self, tmp_py) -> None:  # type: ignore[no-untyped-def]
        p = tmp_py(
            "mod.py",
            """\
            __all__ = ("Alpha", "Beta")
            """,
        )
        info = walk_module(p)
        assert info.declared_all == ["Alpha", "Beta"]

    def test_infers_public_names_when_no_all(self, tmp_py) -> None:  # type: ignore[no-untyped-def]
        p = tmp_py(
            "mod.py",
            """\
            def public_fn(): ...
            def _private_fn(): ...
            class PublicClass: ...
            class _PrivateClass: ...
            PUBLIC_VAR = 1
            _private_var = 2
            """,
        )
        info = walk_module(p)
        assert info.declared_all is None
        assert "public_fn" in info.inferred_all
        assert "PublicClass" in info.inferred_all
        assert "PUBLIC_VAR" in info.inferred_all
        assert "_private_fn" not in info.inferred_all
        assert "_PrivateClass" not in info.inferred_all
        assert "_private_var" not in info.inferred_all

    def test_inferred_names_are_sorted(self, tmp_py) -> None:  # type: ignore[no-untyped-def]
        p = tmp_py(
            "mod.py",
            """\
            def zebra(): ...
            def apple(): ...
            def mango(): ...
            """,
        )
        info = walk_module(p)
        assert info.inferred_all == sorted(info.inferred_all)

    def test_empty_module_has_no_declared_and_empty_inferred(self, tmp_py) -> None:  # type: ignore[no-untyped-def]
        p = tmp_py("mod.py", "")
        info = walk_module(p)
        assert info.declared_all is None
        assert info.inferred_all == []

    def test_path_is_preserved(self, tmp_py) -> None:  # type: ignore[no-untyped-def]
        p = tmp_py("mod.py", "x = 1\n")
        info = walk_module(p)
        assert info.path == p

    def test_module_with_docstring_only(self, tmp_py) -> None:  # type: ignore[no-untyped-def]
        p = tmp_py("mod.py", '"""Module docstring."""\n')
        info = walk_module(p)
        assert info.declared_all is None
        assert info.inferred_all == []

    def test_async_function_is_inferred(self, tmp_py) -> None:  # type: ignore[no-untyped-def]
        p = tmp_py(
            "mod.py",
            """\
            async def public_coro(): ...
            async def _private_coro(): ...
            """,
        )
        info = walk_module(p)
        assert "public_coro" in info.inferred_all
        assert "_private_coro" not in info.inferred_all

    def test_all_variable_itself_not_in_inferred(self, tmp_py) -> None:  # type: ignore[no-untyped-def]
        p = tmp_py(
            "mod.py",
            """\
            __all__ = ["Foo"]
            Foo = 1
            """,
        )
        info = walk_module(p)
        # __all__ should not appear in inferred_all
        assert "__all__" not in info.inferred_all

    def test_multiline_all(self, tmp_py) -> None:  # type: ignore[no-untyped-def]
        p = tmp_py(
            "mod.py",
            """\
            __all__ = [
                "Alpha",
                "Beta",
                "Gamma",
            ]
            """,
        )
        info = walk_module(p)
        assert info.declared_all == ["Alpha", "Beta", "Gamma"]

    def test_non_string_element_in_all_returns_none(self, tmp_py) -> None:  # type: ignore[no-untyped-def]
        p = tmp_py(
            "mod.py",
            """\
            __all__ = ["Foo", some_var]
            """,
        )
        info = walk_module(p)
        # Non-string element makes declared_all unparseable → None
        assert info.declared_all is None

    def test_augmented_assignment_ignored(self, tmp_py) -> None:  # type: ignore[no-untyped-def]
        p = tmp_py(
            "mod.py",
            """\
            __all__ = []
            __all__ += ["Foo"]
            """,
        )
        info = walk_module(p)
        # augmented assign is not ast.Assign so it is ignored; only the simple assign is picked up
        assert info.declared_all == []


# ---------------------------------------------------------------------------
# walk_module — error paths
# ---------------------------------------------------------------------------


class TestWalkModuleErrors:
    def test_raises_syntax_error_on_invalid_python(self, tmp_py) -> None:  # type: ignore[no-untyped-def]
        p = tmp_py("bad.py", "def (\n")
        with pytest.raises(SyntaxError):
            walk_module(p)

    def test_raises_oserror_on_missing_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "no_such_file.py"
        with pytest.raises(OSError):
            walk_module(missing)


# ---------------------------------------------------------------------------
# walk_path
# ---------------------------------------------------------------------------


class TestWalkPath:
    def test_returns_module_info_for_each_py_file(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "b.py").write_text("y = 2\n", encoding="utf-8")
        results = walk_path(tmp_path)
        paths = {r.path for r in results}
        assert tmp_path / "a.py" in paths
        assert tmp_path / "b.py" in paths

    def test_walks_subdirectories_recursively(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "c.py").write_text("z = 3\n", encoding="utf-8")
        results = walk_path(tmp_path)
        paths = {r.path for r in results}
        assert sub / "c.py" in paths

    def test_skips_unparseable_files(self, tmp_path: Path) -> None:
        (tmp_path / "good.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "bad.py").write_text("def (\n", encoding="utf-8")
        results = walk_path(tmp_path)
        paths = {r.path for r in results}
        assert tmp_path / "good.py" in paths
        assert tmp_path / "bad.py" not in paths

    def test_empty_directory_returns_empty_list(self, tmp_path: Path) -> None:
        results = walk_path(tmp_path)
        assert results == []

    def test_non_py_files_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "readme.txt").write_text("hello\n", encoding="utf-8")
        results = walk_path(tmp_path)
        assert results == []

    def test_results_sorted_by_path(self, tmp_path: Path) -> None:
        (tmp_path / "z.py").write_text("a = 1\n", encoding="utf-8")
        (tmp_path / "a.py").write_text("b = 2\n", encoding="utf-8")
        (tmp_path / "m.py").write_text("c = 3\n", encoding="utf-8")
        results = walk_path(tmp_path)
        result_paths = [r.path for r in results]
        assert result_paths == sorted(result_paths)
