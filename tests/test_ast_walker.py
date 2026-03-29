"""Tests for sheridan.iceberg.ast_walker."""

from pathlib import Path

import pytest

from sheridan.iceberg.ast_walker import ModuleInfo, load_modules, resolve_reexports, walk_module, walk_path
from sheridan.iceberg.enums import MemberKind, ParamKind
from sheridan.iceberg.models import (
    ClassInfo,
    ClassMember,
    FunctionSignature,
    ParamInfo,
)


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


class TestModuleInfoVariableTypes:
    def test_variable_types_defaults_to_empty_dict(self, tmp_path: Path) -> None:
        info = ModuleInfo(
            path=tmp_path / "m.py",
            declared_all=None,
        )
        assert info.variable_types == {}

    def test_variable_types_can_be_set(self, tmp_path: Path) -> None:
        info = ModuleInfo(
            path=tmp_path / "m.py",
            declared_all=None,
            variable_types={"VERSION": "str", "COUNT": None},
        )
        assert info.variable_types["VERSION"] == "str"
        assert info.variable_types["COUNT"] is None


class TestWalkModuleHappyPaths:
    def test_extracts_declared_all_list(self, tmp_py) -> None:
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

    def test_extracts_declared_all_tuple(self, tmp_py) -> None:
        p = tmp_py(
            "mod.py",
            """\
            __all__ = ("Alpha", "Beta")
            """,
        )
        info = walk_module(p)
        assert info.declared_all == ["Alpha", "Beta"]

    def test_infers_public_names_when_no_all(self, tmp_py) -> None:
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

    def test_inferred_names_are_sorted(self, tmp_py) -> None:
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

    def test_empty_module_has_no_declared_and_empty_inferred(self, tmp_py) -> None:
        p = tmp_py("mod.py", "")
        info = walk_module(p)
        assert info.declared_all is None
        assert info.inferred_all == []

    def test_path_is_preserved(self, tmp_py) -> None:
        p = tmp_py("mod.py", "x = 1\n")
        info = walk_module(p)
        assert info.path == p

    def test_module_with_docstring_only(self, tmp_py) -> None:
        p = tmp_py("mod.py", '"""Module docstring."""\n')
        info = walk_module(p)
        assert info.declared_all is None
        assert info.inferred_all == []

    def test_async_function_is_inferred(self, tmp_py) -> None:
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

    def test_all_variable_itself_not_in_inferred(self, tmp_py) -> None:
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

    def test_multiline_all(self, tmp_py) -> None:
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

    def test_non_string_element_in_all_returns_none(self, tmp_py) -> None:
        p = tmp_py(
            "mod.py",
            """\
            __all__ = ["Foo", some_var]
            """,
        )
        info = walk_module(p)
        # Non-string element makes declared_all unparseable → None
        assert info.declared_all is None

    def test_augmented_assignment_ignored(self, tmp_py) -> None:
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


class TestWalkModuleErrors:
    def test_raises_syntax_error_on_invalid_python(self, tmp_py) -> None:
        p = tmp_py("bad.py", "def (\n")
        with pytest.raises(SyntaxError):
            walk_module(p)

    def test_raises_oserror_on_missing_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "no_such_file.py"
        with pytest.raises(OSError):
            walk_module(missing)


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


class TestLoadModules:
    def test_single_file_returns_one_element_list(self, tmp_path: Path) -> None:
        p = tmp_path / "mod.py"
        p.write_text("x = 1\n", encoding="utf-8")
        results = load_modules(p)
        assert len(results) == 1
        assert results[0].path == p

    def test_directory_returns_all_py_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "b.py").write_text("y = 2\n", encoding="utf-8")
        results = load_modules(tmp_path)
        paths = {r.path for r in results}
        assert tmp_path / "a.py" in paths
        assert tmp_path / "b.py" in paths

    def test_empty_directory_returns_empty_list(self, tmp_path: Path) -> None:
        assert load_modules(tmp_path) == []


class TestFunctionSignatureExtraction:
    def test_simple_function_no_params_no_return(self, tmp_py) -> None:
        p = tmp_py("mod.py", "def f(): ...\n")
        info = walk_module(p)
        sig = info.function_signatures["f"]
        assert sig.params == []
        assert sig.return_annotation is None
        assert sig.is_async is False

    def test_async_function_is_async_true(self, tmp_py) -> None:
        p = tmp_py("mod.py", "async def f(): ...\n")
        info = walk_module(p)
        sig = info.function_signatures["f"]
        assert sig.is_async is True

    def test_positional_or_keyword_params_with_annotations(self, tmp_py) -> None:
        p = tmp_py("mod.py", "def f(x: int, y: str) -> bool: ...\n")
        info = walk_module(p)
        sig = info.function_signatures["f"]
        assert len(sig.params) == 2
        assert sig.params[0] == ParamInfo(name="x", annotation="int", kind=ParamKind.positional_or_keyword)
        assert sig.params[1] == ParamInfo(name="y", annotation="str", kind=ParamKind.positional_or_keyword)
        assert sig.return_annotation == "bool"

    def test_param_with_default_value(self, tmp_py) -> None:
        p = tmp_py("mod.py", "def f(x: int = 5): ...\n")
        info = walk_module(p)
        sig = info.function_signatures["f"]
        assert len(sig.params) == 1
        assert sig.params[0].has_default is True
        assert sig.params[0].annotation == "int"

    def test_var_positional_args(self, tmp_py) -> None:
        p = tmp_py("mod.py", "def f(*args: int): ...\n")
        info = walk_module(p)
        sig = info.function_signatures["f"]
        assert len(sig.params) == 1
        assert sig.params[0].kind is ParamKind.var_positional
        assert sig.params[0].name == "args"
        assert sig.params[0].annotation == "int"

    def test_var_keyword_kwargs(self, tmp_py) -> None:
        p = tmp_py("mod.py", "def f(**kwargs: str): ...\n")
        info = walk_module(p)
        sig = info.function_signatures["f"]
        assert len(sig.params) == 1
        assert sig.params[0].kind is ParamKind.var_keyword
        assert sig.params[0].name == "kwargs"
        assert sig.params[0].annotation == "str"

    def test_keyword_only_param(self, tmp_py) -> None:
        p = tmp_py("mod.py", "def f(*, kw: int): ...\n")
        info = walk_module(p)
        sig = info.function_signatures["f"]
        assert len(sig.params) == 1
        assert sig.params[0].kind is ParamKind.keyword_only
        assert sig.params[0].name == "kw"
        assert sig.params[0].annotation == "int"
        assert sig.params[0].has_default is False

    def test_keyword_only_param_with_default(self, tmp_py) -> None:
        p = tmp_py("mod.py", "def f(*, kw: int = 0): ...\n")
        info = walk_module(p)
        sig = info.function_signatures["f"]
        assert sig.params[0].kind is ParamKind.keyword_only
        assert sig.params[0].has_default is True

    def test_positional_only_param(self, tmp_py) -> None:
        p = tmp_py("mod.py", "def f(x: int, /): ...\n")
        info = walk_module(p)
        sig = info.function_signatures["f"]
        assert len(sig.params) == 1
        assert sig.params[0].kind is ParamKind.positional_only
        assert sig.params[0].name == "x"
        assert sig.params[0].annotation == "int"

    def test_return_annotation_complex(self, tmp_py) -> None:
        p = tmp_py("mod.py", "def f() -> list[str]: ...\n")
        info = walk_module(p)
        sig = info.function_signatures["f"]
        assert sig.return_annotation == "list[str]"

    def test_param_no_annotation_is_none(self, tmp_py) -> None:
        p = tmp_py("mod.py", "def f(x): ...\n")
        info = walk_module(p)
        sig = info.function_signatures["f"]
        assert sig.params[0].annotation is None

    def test_walk_module_populates_function_signatures_for_public(self, tmp_py) -> None:
        p = tmp_py(
            "mod.py",
            """\
            def public_fn(x: int) -> str: ...
            """,
        )
        info = walk_module(p)
        assert "public_fn" in info.function_signatures
        sig = info.function_signatures["public_fn"]
        assert isinstance(sig, FunctionSignature)

    def test_walk_module_excludes_private_functions(self, tmp_py) -> None:
        p = tmp_py(
            "mod.py",
            """\
            def _private(x: int) -> str: ...
            """,
        )
        info = walk_module(p)
        assert "_private" not in info.function_signatures


class TestClassInfoExtraction:
    def test_empty_class(self, tmp_py) -> None:
        p = tmp_py("mod.py", "class Foo: pass\n")
        info = walk_module(p)
        cls = info.class_info["Foo"]
        assert cls.bases == []
        assert cls.members == []

    def test_class_var_with_annotation(self, tmp_py) -> None:
        p = tmp_py(
            "mod.py",
            """\
            class Foo:
                x: int = 5
            """,
        )
        info = walk_module(p)
        cls = info.class_info["Foo"]
        assert len(cls.members) == 1
        assert cls.members[0] == ClassMember(name="x", kind=MemberKind.class_var, annotation="int")

    def test_class_var_without_annotation(self, tmp_py) -> None:
        p = tmp_py(
            "mod.py",
            """\
            class Foo:
                x = 5
            """,
        )
        info = walk_module(p)
        cls = info.class_info["Foo"]
        assert len(cls.members) == 1
        assert cls.members[0] == ClassMember(name="x", kind=MemberKind.class_var, annotation=None)

    def test_private_class_var_excluded(self, tmp_py) -> None:
        p = tmp_py(
            "mod.py",
            """\
            class Foo:
                _x: int = 5
            """,
        )
        info = walk_module(p)
        cls = info.class_info["Foo"]
        assert cls.members == []

    def test_instance_attr_from_init_with_annotation(self, tmp_py) -> None:
        p = tmp_py(
            "mod.py",
            """\
            class Foo:
                def __init__(self) -> None:
                    self.name: str = "hello"
            """,
        )
        info = walk_module(p)
        cls = info.class_info["Foo"]
        assert len(cls.members) == 1
        assert cls.members[0] == ClassMember(name="name", kind=MemberKind.instance_attr, annotation="str")

    def test_instance_attr_from_init_without_annotation(self, tmp_py) -> None:
        p = tmp_py(
            "mod.py",
            """\
            class Foo:
                def __init__(self) -> None:
                    self.name = "hello"
            """,
        )
        info = walk_module(p)
        cls = info.class_info["Foo"]
        assert len(cls.members) == 1
        assert cls.members[0] == ClassMember(name="name", kind=MemberKind.instance_attr, annotation=None)

    def test_private_instance_attr_excluded(self, tmp_py) -> None:
        p = tmp_py(
            "mod.py",
            """\
            class Foo:
                def __init__(self) -> None:
                    self._x = 5
            """,
        )
        info = walk_module(p)
        cls = info.class_info["Foo"]
        assert cls.members == []

    def test_regular_method(self, tmp_py) -> None:
        p = tmp_py(
            "mod.py",
            """\
            class Foo:
                def update(self) -> None: ...
            """,
        )
        info = walk_module(p)
        cls = info.class_info["Foo"]
        assert len(cls.members) == 1
        assert cls.members[0].name == "update"
        assert cls.members[0].kind is MemberKind.method

    def test_private_method_excluded(self, tmp_py) -> None:
        p = tmp_py(
            "mod.py",
            """\
            class Foo:
                def _helper(self) -> None: ...
            """,
        )
        info = walk_module(p)
        cls = info.class_info["Foo"]
        assert cls.members == []

    def test_property_method(self, tmp_py) -> None:
        p = tmp_py(
            "mod.py",
            """\
            class Foo:
                @property
                def value(self) -> int: ...
            """,
        )
        info = walk_module(p)
        cls = info.class_info["Foo"]
        assert len(cls.members) == 1
        assert cls.members[0].name == "value"
        assert cls.members[0].kind is MemberKind.property

    def test_property_setter_excluded_no_duplicate(self, tmp_py) -> None:
        p = tmp_py(
            "mod.py",
            """\
            class Foo:
                @property
                def value(self) -> int: ...
                @value.setter
                def value(self, v: int) -> None: ...
            """,
        )
        info = walk_module(p)
        cls = info.class_info["Foo"]
        value_members = [m for m in cls.members if m.name == "value"]
        assert len(value_members) == 1
        assert value_members[0].kind is MemberKind.property

    def test_classmethod(self, tmp_py) -> None:
        p = tmp_py(
            "mod.py",
            """\
            class Foo:
                @classmethod
                def create(cls) -> "Foo": ...
            """,
        )
        info = walk_module(p)
        cls = info.class_info["Foo"]
        assert len(cls.members) == 1
        assert cls.members[0].name == "create"
        assert cls.members[0].kind is MemberKind.classmethod

    def test_staticmethod(self, tmp_py) -> None:
        p = tmp_py(
            "mod.py",
            """\
            class Foo:
                @staticmethod
                def parse(s: str) -> "Foo": ...
            """,
        )
        info = walk_module(p)
        cls = info.class_info["Foo"]
        assert len(cls.members) == 1
        assert cls.members[0].name == "parse"
        assert cls.members[0].kind is MemberKind.staticmethod

    def test_inheritance_bases(self, tmp_py) -> None:
        p = tmp_py("mod.py", "class Foo(Bar, Baz): pass\n")
        info = walk_module(p)
        cls = info.class_info["Foo"]
        assert cls.bases == ["Bar", "Baz"]

    def test_walk_module_populates_class_info_for_public(self, tmp_py) -> None:
        p = tmp_py("mod.py", "class MyClass: pass\n")
        info = walk_module(p)
        assert "MyClass" in info.class_info
        assert isinstance(info.class_info["MyClass"], ClassInfo)

    def test_walk_module_excludes_private_classes(self, tmp_py) -> None:
        p = tmp_py("mod.py", "class _Private: pass\n")
        info = walk_module(p)
        assert "_Private" not in info.class_info


class TestWalkModuleVariableTypes:
    def test_annotated_variable_extracted(self, tmp_path: Path) -> None:
        p = tmp_path / "m.py"
        p.write_text('__version__: str = "1.0"\n', encoding="utf-8")
        info = walk_module(p)
        assert info.variable_types.get("__version__") == "str"

    def test_unannotated_variable_extracted(self, tmp_path: Path) -> None:
        p = tmp_path / "m.py"
        p.write_text("FOO = 42\n", encoding="utf-8")
        info = walk_module(p)
        assert "FOO" in info.variable_types
        assert info.variable_types["FOO"] is None

    def test_function_not_in_variable_types(self, tmp_path: Path) -> None:
        p = tmp_path / "m.py"
        p.write_text("def greet(name: str) -> str: ...\n", encoding="utf-8")
        info = walk_module(p)
        assert "greet" not in info.variable_types

    def test_class_not_in_variable_types(self, tmp_path: Path) -> None:
        p = tmp_path / "m.py"
        p.write_text("class Foo:\n    pass\n", encoding="utf-8")
        info = walk_module(p)
        assert "Foo" not in info.variable_types

    def test_all_itself_excluded(self, tmp_path: Path) -> None:
        p = tmp_path / "m.py"
        p.write_text('__all__ = ["FOO"]\nFOO = 1\n', encoding="utf-8")
        info = walk_module(p)
        assert "__all__" not in info.variable_types

    def test_dunder_variable_included(self, tmp_path: Path) -> None:
        p = tmp_path / "m.py"
        p.write_text('__version__: str = "2.0"\n', encoding="utf-8")
        info = walk_module(p)
        assert "__version__" in info.variable_types

    def test_complex_annotation_extracted(self, tmp_path: Path) -> None:
        p = tmp_path / "m.py"
        p.write_text("MAPPING: dict[str, int] = {}\n", encoding="utf-8")
        info = walk_module(p)
        assert info.variable_types.get("MAPPING") == "dict[str, int]"


class TestResolveReexports:
    """Tests for resolve_reexports post-processing pass."""

    @staticmethod
    def _write(path: Path, source: str) -> Path:
        """Write source text to path, creating parent directories as needed.

        Args:
            path: Destination file path.
            source: Python source text to write.

        Returns:
            The path that was written.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        return path

    def test_resolve_copies_function_from_source(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "pkg" / "utils.py",
            "def greet(name: str) -> str: ...\n",
        )
        self._write(
            tmp_path / "pkg" / "__init__.py",
            '__all__ = ["greet"]\nfrom pkg.utils import greet\n',
        )
        modules = walk_path(tmp_path)
        resolved = resolve_reexports(modules)
        init_info = next(m for m in resolved if m.path.name == "__init__.py")
        assert "greet" in init_info.function_signatures

    def test_resolve_copies_class_from_source(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "pkg" / "models.py",
            "class Point:\n    x: float\n    y: float\n",
        )
        self._write(
            tmp_path / "pkg" / "__init__.py",
            '__all__ = ["Point"]\nfrom pkg.models import Point\n',
        )
        modules = walk_path(tmp_path)
        resolved = resolve_reexports(modules)
        init_info = next(m for m in resolved if m.path.name == "__init__.py")
        assert "Point" in init_info.class_info

    def test_resolve_copies_variable_from_source(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "pkg" / "version.py",
            '__version__: str = "1.0"\n',
        )
        self._write(
            tmp_path / "pkg" / "__init__.py",
            '__all__ = ["__version__"]\nfrom pkg.version import __version__\n',
        )
        modules = walk_path(tmp_path)
        resolved = resolve_reexports(modules)
        init_info = next(m for m in resolved if m.path.name == "__init__.py")
        assert "__version__" in init_info.variable_types
        assert init_info.variable_types["__version__"] == "str"

    def test_resolve_handles_alias(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "pkg" / "core.py",
            "def internal_fn(x: int) -> bool: ...\n",
        )
        self._write(
            tmp_path / "pkg" / "__init__.py",
            '__all__ = ["public_fn"]\nfrom pkg.core import internal_fn as public_fn\n',
        )
        modules = walk_path(tmp_path)
        resolved = resolve_reexports(modules)
        init_info = next(m for m in resolved if m.path.name == "__init__.py")
        assert "public_fn" in init_info.function_signatures
        assert "internal_fn" not in init_info.function_signatures

    def test_resolve_skips_already_defined(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "pkg" / "utils.py",
            "def greet(name: str) -> str: ...\n",
        )
        self._write(
            tmp_path / "pkg" / "__init__.py",
            '__all__ = ["greet"]\nfrom pkg.utils import greet\ndef greet() -> None: ...\n',
        )
        modules = walk_path(tmp_path)
        resolved = resolve_reexports(modules)
        init_info = next(m for m in resolved if m.path.name == "__init__.py")
        sig = init_info.function_signatures["greet"]
        assert len(sig.params) == 0  # local def, not the imported one

    def test_resolve_skips_external_modules(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "pkg" / "__init__.py",
            '__all__ = ["Path"]\nfrom pathlib import Path\n',
        )
        modules = walk_path(tmp_path)
        resolved = resolve_reexports(modules)
        init_info = next(m for m in resolved if m.path.name == "__init__.py")
        assert "Path" not in init_info.function_signatures
        assert "Path" not in init_info.class_info

    def test_resolve_handles_nested_package(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "pkg" / "sub" / "core.py",
            "class Widget:\n    label: str\n",
        )
        self._write(
            tmp_path / "pkg" / "sub" / "__init__.py",
            '__all__ = ["Widget"]\nfrom pkg.sub.core import Widget\n',
        )
        self._write(
            tmp_path / "pkg" / "__init__.py",
            '__all__ = ["Widget"]\nfrom pkg.sub import Widget\n',
        )
        modules = walk_path(tmp_path)
        resolved = resolve_reexports(modules)
        sub_init = next(m for m in resolved if m.path.name == "__init__.py" and m.path.parent.name == "sub")
        assert "Widget" in sub_init.class_info
