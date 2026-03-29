"""Tests for sheridan.iceberg.api."""

from pathlib import Path
from unittest.mock import patch

from sheridan.iceberg.api import get_public_api
from sheridan.iceberg.ast_walker import ModuleInfo


def _write(path: Path, source: str) -> Path:
    path.write_text(source, encoding="utf-8")
    return path


class TestGetPublicApiFile:
    def test_returns_dict(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Foo"]\ndef Foo(): ...\n')
        result = get_public_api(p)
        assert isinstance(result, dict)

    def test_key_is_module_stem(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mymod.py", '__all__ = ["Foo"]\ndef Foo(): ...\n')
        result = get_public_api(p)
        assert "mymod" in result

    def test_value_is_module_info(self, tmp_path: Path) -> None:
        from sheridan.iceberg.models import ModuleInfo

        p = _write(tmp_path / "mod.py", '__all__ = ["Foo", "Bar"]\ndef Foo(): ...\ndef Bar(): ...\n')
        result = get_public_api(p)
        assert isinstance(result["mod"], ModuleInfo)
        assert result["mod"].effective_all == ["Foo", "Bar"]

    def test_uses_declared_all_by_default(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Declared"]\ndef Inferred(): ...\n')
        result = get_public_api(p)
        assert result["mod"].effective_all == ["Declared"]

    def test_uses_inferred_when_no_all(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "def PublicFn(): ...\ndef _private(): ...\n")
        result = get_public_api(p)
        assert result["mod"].effective_all == ["PublicFn"]

    def test_use_ast_returns_inferred_names(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Declared"]\ndef Inferred(): ...\n')
        result = get_public_api(p, use_ast=True)
        assert result["mod"].inferred_all == ["Inferred"]

    def test_use_ast_false_returns_declared_names(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", '__all__ = ["Alpha"]\ndef Beta(): ...\n')
        result = get_public_api(p, use_ast=False)
        assert result["mod"].effective_all == ["Alpha"]

    def test_accepts_str_path(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "def Foo(): ...\n")
        result = get_public_api(str(p))
        assert "mod" in result

    def test_empty_module_returns_empty_list(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "empty.py", "")
        result = get_public_api(p)
        assert result["empty"].effective_all == []

    def test_module_with_empty_all_returns_empty_list(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "__all__: list[str] = []\n")
        result = get_public_api(p)
        assert result["mod"].effective_all == []

    def test_use_ast_empty_module_returns_empty_list(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "mod.py", "")
        result = get_public_api(p, use_ast=True)
        assert result["mod"].effective_all == []


class TestGetPublicApiDirectory:
    def test_returns_entry_for_each_module(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.py", "def Alpha(): ...\n")
        _write(tmp_path / "b.py", "def Beta(): ...\n")
        result = get_public_api(tmp_path)
        assert "a" in result
        assert "b" in result

    def test_accepts_str_directory(self, tmp_path: Path) -> None:
        _write(tmp_path / "mod.py", "def Foo(): ...\n")
        result = get_public_api(str(tmp_path))
        assert "mod" in result

    def test_empty_directory_returns_empty_dict(self, tmp_path: Path) -> None:
        result = get_public_api(tmp_path)
        assert result == {}

    def test_module_keys_are_relative_dotted(self, tmp_path: Path) -> None:
        sub = tmp_path / "pkg"
        sub.mkdir()
        _write(sub / "util.py", "def helper(): ...\n")
        result = get_public_api(tmp_path)
        assert "pkg.util" in result

    def test_init_module_key_strips_dunder_init(self, tmp_path: Path) -> None:
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        _write(pkg / "__init__.py", '__all__ = ["Pub"]\ndef Pub(): ...\n')
        result = get_public_api(tmp_path)
        assert "mypkg" in result
        assert "mypkg.__init__" not in result

    def test_init_with_all_suppresses_submodules(self, tmp_path: Path) -> None:
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        _write(pkg / "__init__.py", '__all__ = ["Pub"]\ndef Pub(): ...\n')
        _write(pkg / "sub.py", "def SubFn(): ...\n")
        result = get_public_api(tmp_path)
        assert "mypkg" in result
        assert "mypkg.sub" not in result

    def test_init_without_all_does_not_suppress_submodules(self, tmp_path: Path) -> None:
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        _write(pkg / "__init__.py", "")
        _write(pkg / "sub.py", "def SubFn(): ...\n")
        result = get_public_api(tmp_path)
        assert "mypkg.sub" in result

    def test_use_ast_true_shows_all_modules(self, tmp_path: Path) -> None:
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        _write(pkg / "__init__.py", '__all__ = ["Pub"]\ndef Pub(): ...\n')
        _write(pkg / "sub.py", "def SubFn(): ...\n")
        result = get_public_api(tmp_path, use_ast=True)
        assert "mypkg" in result
        assert "mypkg.sub" in result

    def test_use_ast_true_values_are_inferred(self, tmp_path: Path) -> None:
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        _write(pkg / "__init__.py", '__all__ = ["Declared"]\ndef Inferred(): ...\n')
        result = get_public_api(tmp_path, use_ast=True)
        assert result["mypkg"].inferred_all == ["Inferred"]

    def test_skips_test_files(self, tmp_path: Path) -> None:
        _write(tmp_path / "mod.py", "def Foo(): ...\n")
        _write(tmp_path / "test_mod.py", "def test_foo(): ...\n")
        result = get_public_api(tmp_path)
        assert "mod" in result
        assert "test_mod" not in result

    def test_skips_unparseable_files(self, tmp_path: Path) -> None:
        _write(tmp_path / "good.py", "def Foo(): ...\n")
        _write(tmp_path / "bad.py", "def (\n")
        result = get_public_api(tmp_path)
        assert "good" in result
        assert "bad" not in result

    def test_path_outside_base_uses_str_fallback(self, tmp_path: Path) -> None:
        # Single file: when base=parent, relative_to always succeeds for files.
        # Test with a directory path to confirm no ValueError is raised.
        _write(tmp_path / "mod.py", "def Foo(): ...\n")
        result = get_public_api(tmp_path)
        assert isinstance(result, dict)


def test_get_public_api_path_outside_base_uses_str_key(tmp_path: Path) -> None:
    # Construct a ModuleInfo whose path is NOT under the base so that
    # relative_to raises ValueError and the except branch is exercised.
    other = tmp_path / "other" / "mod.py"
    other.parent.mkdir()
    _write(other, "def Foo(): ...\n")

    outside_info = ModuleInfo(
        path=other,
        declared_all=["Foo"],
        inferred_all=["Foo"],
    )

    base_dir = tmp_path / "base"
    base_dir.mkdir()
    _write(base_dir / "placeholder.py", "")

    with (
        patch("sheridan.iceberg.api.load_modules", return_value=[outside_info]),
        patch("sheridan.iceberg.api.resolve_show_modules", return_value=[outside_info]),
    ):
        result = get_public_api(base_dir)

    # The key should be the str() of the path, not a dotted module name.
    assert str(other) in result


class TestReexportResolutionIntegration:
    """Integration tests verifying resolve_reexports is wired into get_public_api."""

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

    def test_reexport_resolution_populates_function_signatures(self, tmp_path: Path) -> None:
        """Function signatures are copied from source modules into re-exporting __init__.py."""
        self._write(
            tmp_path / "mypkg" / "utils.py",
            "def add(a: int, b: int) -> int: ...\n",
        )
        self._write(
            tmp_path / "mypkg" / "__init__.py",
            '__all__ = ["add"]\nfrom mypkg.utils import add\n',
        )
        result = get_public_api(tmp_path)
        assert "mypkg" in result
        init_info = result["mypkg"]
        assert "add" in init_info.function_signatures
        sig = init_info.function_signatures["add"]
        assert len(sig.params) == 2
        assert sig.params[0].name == "a"
        assert sig.return_annotation == "int"

    def test_reexport_resolution_populates_class_info(self, tmp_path: Path) -> None:
        """Class info is copied from source modules into re-exporting __init__.py."""
        self._write(
            tmp_path / "mypkg" / "models.py",
            "class Product:\n    name: str\n    price: float\n",
        )
        self._write(
            tmp_path / "mypkg" / "__init__.py",
            '__all__ = ["Product"]\nfrom mypkg.models import Product\n',
        )
        result = get_public_api(tmp_path)
        init_info = result["mypkg"]
        assert "Product" in init_info.class_info
        cls = init_info.class_info["Product"]
        member_names = [m.name for m in cls.members]
        assert "name" in member_names
        assert "price" in member_names

    def test_reexport_resolution_populates_variable_types(self, tmp_path: Path) -> None:
        """Variable types are copied from source modules into re-exporting __init__.py."""
        self._write(
            tmp_path / "mypkg" / "version.py",
            '__version__: str = "1.0.0"\n',
        )
        self._write(
            tmp_path / "mypkg" / "__init__.py",
            '__all__ = ["__version__"]\nfrom mypkg.version import __version__\n',
        )
        result = get_public_api(tmp_path)
        init_info = result["mypkg"]
        assert "__version__" in init_info.variable_types
        assert init_info.variable_types["__version__"] == "str"
