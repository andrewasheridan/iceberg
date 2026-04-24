"""Tests for sheridan.iceberg._init_resolver (resolve_init and ResolveReport)."""

import pytest

from sheridan.iceberg._config import Config
from sheridan.iceberg._exceptions import ParseError
from sheridan.iceberg._init_resolver import ResolveReport, resolve_init
from sheridan.iceberg._models import Assignment, Class, Function, Module

# ---------------------------------------------------------------------------
# Shared helpers / fixtures
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = Config()
_CONFIG_SUBPKG_FALSE = Config(include_subpackages_in_all=False)
_CONFIG_SUBPKG_TRUE = Config(include_subpackages_in_all=True)

_EMPTY_MODULE = Module(name="", assignments=(), classes=(), functions=())
_EMPTY_SIBLINGS: dict[str, Module] = {}
_EMPTY_SUBPKGS: frozenset[str] = frozenset()


def _make_function(name: str) -> Function:
    return Function(
        name=name,
        positional_parameters=(),
        keyword_parameters=frozenset(),
        var_positional=None,
        var_keyword=None,
        returns=None,
        is_async=False,
    )


def _make_class(name: str) -> Class:
    return Class(name=name, assignments=(), methods=(), nested_classes=())


def _make_assignment(name: str) -> Assignment:
    return Assignment(name=name, annotation=None)


def _make_module(
    name: str,
    *,
    functions: tuple[Function, ...] = (),
    classes: tuple[Class, ...] = (),
    assignments: tuple[Assignment, ...] = (),
) -> Module:
    return Module(name=name, functions=functions, classes=classes, assignments=assignments)


def _resolve(
    source: str,
    package: str = "mypkg",
    siblings: dict[str, Module] | None = None,
    subpackage_names: frozenset[str] = frozenset(),
    config: Config = _DEFAULT_CONFIG,
) -> tuple[Module, ResolveReport]:
    return resolve_init(
        init_source=source,
        dotted_package=package,
        sibling_modules=siblings if siblings is not None else {},
        subpackage_names=subpackage_names,
        config=config,
    )


# ---------------------------------------------------------------------------
# Scenario 1: No __all__ — underscore-prefix filtering
# ---------------------------------------------------------------------------


def test_no_all_public_function_included() -> None:
    source = """
from .core import public_func

def _local_helper():
    pass
"""
    fn = _make_function("public_func")
    sibling = _make_module("mypkg.core", functions=(fn,))
    module, _ = _resolve(source, siblings={"mypkg.core": sibling})
    names = {f.name for f in module.functions}
    assert "public_func" in names


def test_no_all_private_import_excluded() -> None:
    source = "from .core import _private_func\n"
    fn = _make_function("_private_func")
    sibling = _make_module("mypkg.core", functions=(fn,))
    module, _ = _resolve(source, siblings={"mypkg.core": sibling})
    names = {f.name for f in module.functions}
    assert "_private_func" not in names


def test_no_all_public_and_private_imports_separated() -> None:
    source = """
from .utils import helper, _internal
"""
    helper_fn = _make_function("helper")
    internal_fn = _make_function("_internal")
    sibling = _make_module("mypkg.utils", functions=(helper_fn, internal_fn))
    module, _ = _resolve(source, siblings={"mypkg.utils": sibling})
    names = {f.name for f in module.functions}
    assert "helper" in names
    assert "_internal" not in names


def test_no_all_locally_defined_public_class_included() -> None:
    source = """
class PublicClass:
    pass

class _PrivateClass:
    pass
"""
    module, _ = _resolve(source)
    names = {c.name for c in module.classes}
    assert "PublicClass" in names
    assert "_PrivateClass" not in names


def test_no_all_locally_defined_public_assignment_included() -> None:
    source = """
VERSION: str = "1.0.0"
_INTERNAL: int = 0
"""
    module, _ = _resolve(source)
    names = {a.name for a in module.assignments}
    assert "VERSION" in names
    assert "_INTERNAL" not in names


# ---------------------------------------------------------------------------
# Scenario 2: __all__-driven re-export — objects attached by equality
# ---------------------------------------------------------------------------


def test_all_driven_function_reexport() -> None:
    source = """
__all__ = ["my_func"]
from .core import my_func
"""
    fn = _make_function("my_func")
    sibling = _make_module("mypkg.core", functions=(fn,))
    module, _ = _resolve(source, siblings={"mypkg.core": sibling})
    assert len(module.functions) == 1
    assert module.functions[0] == fn


def test_all_driven_class_reexport() -> None:
    source = """
__all__ = ["MyClass"]
from .models import MyClass
"""
    cls = _make_class("MyClass")
    sibling = _make_module("mypkg.models", classes=(cls,))
    module, _ = _resolve(source, siblings={"mypkg.models": sibling})
    assert len(module.classes) == 1
    assert module.classes[0] == cls


def test_all_driven_assignment_reexport() -> None:
    source = """
__all__ = ["CONSTANT"]
from .constants import CONSTANT
"""
    asgn = _make_assignment("CONSTANT")
    sibling = _make_module("mypkg.constants", assignments=(asgn,))
    module, _ = _resolve(source, siblings={"mypkg.constants": sibling})
    assert len(module.assignments) == 1
    assert module.assignments[0] == asgn


def test_all_driven_mixed_reexports() -> None:
    source = """
__all__ = ["func_a", "ClassB", "CONST_C"]
from .a import func_a
from .b import ClassB
from .c import CONST_C
"""
    fn = _make_function("func_a")
    cls = _make_class("ClassB")
    asgn = _make_assignment("CONST_C")
    siblings = {
        "mypkg.a": _make_module("mypkg.a", functions=(fn,)),
        "mypkg.b": _make_module("mypkg.b", classes=(cls,)),
        "mypkg.c": _make_module("mypkg.c", assignments=(asgn,)),
    }
    module, report = _resolve(source, siblings=siblings)
    assert module.functions[0] == fn
    assert module.classes[0] == cls
    assert module.assignments[0] == asgn
    assert report.unresolved == ()


def test_all_driven_aliased_import_resolved() -> None:
    """import X as Y — the resolved symbol must use the local alias Y, not the source name X."""
    source = """
__all__ = ["Y"]
from .core import X as Y
"""
    fn = _make_function("X")
    sibling = _make_module("mypkg.core", functions=(fn,))
    module, _ = _resolve(source, siblings={"mypkg.core": sibling})
    assert len(module.functions) == 1
    assert module.functions[0].name == "Y"


def test_all_locally_defined_name_attached() -> None:
    source = """
__all__ = ["local_fn"]

def local_fn() -> None:
    pass
"""
    module, report = _resolve(source)
    names = {f.name for f in module.functions}
    assert "local_fn" in names
    assert report.unresolved == ()


# ---------------------------------------------------------------------------
# Scenario 3: Unresolvable name recorded in ResolveReport, no exception
# ---------------------------------------------------------------------------


def test_unresolvable_name_in_report() -> None:
    source = """
__all__ = ["ghost"]
"""
    _, report = _resolve(source)
    assert "ghost" in report.unresolved


def test_unresolvable_name_does_not_raise() -> None:
    source = """
__all__ = ["missing_a", "missing_b"]
"""
    # Must not raise; both names go into unresolved
    _, report = _resolve(source)
    assert set(report.unresolved) == {"missing_a", "missing_b"}


def test_unresolvable_sibling_module_not_in_mapping() -> None:
    source = """
__all__ = ["something"]
from .absent_module import something
"""
    # sibling_modules is empty — module not found
    _, report = _resolve(source, siblings={})
    assert "something" in report.unresolved


def test_unresolvable_name_not_added_to_module_members() -> None:
    source = """
__all__ = ["ghost"]
"""
    module, _ = _resolve(source)
    all_names = (
        {f.name for f in module.functions} | {c.name for c in module.classes} | {a.name for a in module.assignments}
    )
    assert "ghost" not in all_names


def test_partial_resolution_mixed_resolved_and_unresolved() -> None:
    source = """
__all__ = ["real_func", "ghost"]
from .core import real_func
"""
    fn = _make_function("real_func")
    sibling = _make_module("mypkg.core", functions=(fn,))
    module, report = _resolve(source, siblings={"mypkg.core": sibling})
    assert module.functions[0] == fn
    assert "ghost" in report.unresolved
    assert "real_func" not in report.unresolved


# ---------------------------------------------------------------------------
# Scenario 4: Deep relative import — from .sub.deep import X
# ---------------------------------------------------------------------------


def test_deep_relative_import_resolved() -> None:
    source = """
__all__ = ["deep_fn"]
from .sub.deep import deep_fn
"""
    fn = _make_function("deep_fn")
    sibling = _make_module("mypkg.sub.deep", functions=(fn,))
    module, report = _resolve(source, package="mypkg", siblings={"mypkg.sub.deep": sibling})
    assert module.functions[0] == fn
    assert report.unresolved == ()


def test_deep_relative_import_three_levels() -> None:
    source = """
__all__ = ["leaf_cls"]
from .a.b.c import leaf_cls
"""
    cls = _make_class("leaf_cls")
    sibling = _make_module("pkg.a.b.c", classes=(cls,))
    module, _ = _resolve(source, package="pkg", siblings={"pkg.a.b.c": sibling})
    assert module.classes[0] == cls


def test_deep_relative_import_nested_package() -> None:
    source = """
__all__ = ["helper"]
from .utils.strings import helper
"""
    fn = _make_function("helper")
    sibling = _make_module("mylib.sub.utils.strings", functions=(fn,))
    module, _ = _resolve(
        source,
        package="mylib.sub",
        siblings={"mylib.sub.utils.strings": sibling},
    )
    assert module.functions[0] == fn


# ---------------------------------------------------------------------------
# Scenario 5: include_subpackages_in_all orthogonality
# ---------------------------------------------------------------------------


def test_subpackage_names_excluded_from_members_flag_true() -> None:
    source = """
__all__ = ["sub", "real_fn"]
from .core import real_fn
"""
    fn = _make_function("real_fn")
    sibling = _make_module("mypkg.core", functions=(fn,))
    module, report = _resolve(
        source,
        siblings={"mypkg.core": sibling},
        subpackage_names=frozenset({"sub"}),
        config=_CONFIG_SUBPKG_TRUE,
    )
    names = {f.name for f in module.functions}
    assert "real_fn" in names
    # sub is a subpackage name — resolver skips it silently (not in unresolved)
    assert "sub" not in report.unresolved
    all_names = (
        {f.name for f in module.functions} | {c.name for c in module.classes} | {a.name for a in module.assignments}
    )
    assert "sub" not in all_names


def test_subpackage_names_excluded_from_members_flag_false() -> None:
    source = """
__all__ = ["sub", "real_fn"]
from .core import real_fn
"""
    fn = _make_function("real_fn")
    sibling = _make_module("mypkg.core", functions=(fn,))
    module_false, report_false = _resolve(
        source,
        siblings={"mypkg.core": sibling},
        subpackage_names=frozenset({"sub"}),
        config=_CONFIG_SUBPKG_FALSE,
    )
    module_true, report_true = _resolve(
        source,
        siblings={"mypkg.core": sibling},
        subpackage_names=frozenset({"sub"}),
        config=_CONFIG_SUBPKG_TRUE,
    )
    # Both configs produce identical modules and reports
    assert module_false == module_true
    assert report_false == report_true


@pytest.mark.parametrize("flag", [True, False])
def test_include_subpackages_flag_orthogonal(flag: bool) -> None:
    source = """
__all__ = ["exported_fn"]
from .impl import exported_fn
"""
    fn = _make_function("exported_fn")
    sibling = _make_module("mypkg.impl", functions=(fn,))
    config = Config(include_subpackages_in_all=flag)
    module, report = _resolve(source, siblings={"mypkg.impl": sibling}, config=config)
    assert module.functions[0] == fn
    assert report.unresolved == ()


# ---------------------------------------------------------------------------
# Scenario 6: SyntaxError in init_source raises ParseError
# ---------------------------------------------------------------------------


def test_syntax_error_raises_parse_error() -> None:
    source = "def broken(:"
    with pytest.raises(ParseError):
        _resolve(source)


def test_syntax_error_incomplete_expression_raises_parse_error() -> None:
    source = "x = (1 +"
    with pytest.raises(ParseError):
        _resolve(source)


def test_syntax_error_invalid_class_raises_parse_error() -> None:
    source = "class :"
    with pytest.raises(ParseError):
        _resolve(source)


def test_syntax_error_wrapped_as_iceberg_error() -> None:
    from sheridan.iceberg._exceptions import IcebergError

    source = "!!not_python!!"
    with pytest.raises(IcebergError):
        _resolve(source)


def test_valid_empty_source_does_not_raise() -> None:
    module, report = _resolve("")
    assert module.name == "mypkg"
    assert report.unresolved == ()


# ---------------------------------------------------------------------------
# ResolveReport structural tests
# ---------------------------------------------------------------------------


def test_resolve_report_is_frozen() -> None:
    report = ResolveReport(unresolved=("a",))
    with pytest.raises((AttributeError, TypeError)):
        report.unresolved = ("b",)  # type: ignore[misc]


def test_resolve_report_unresolved_is_tuple() -> None:
    source = """
__all__ = ["x", "y"]
"""
    _, report = _resolve(source)
    assert isinstance(report.unresolved, tuple)


# ---------------------------------------------------------------------------
# Module name preserved on returned Module
# ---------------------------------------------------------------------------


def test_returned_module_name_matches_dotted_package() -> None:
    source = "__all__ = []\n"
    module, _ = _resolve(source, package="org.lib.sub")
    assert module.name == "org.lib.sub"


# ---------------------------------------------------------------------------
# Absolute intra-package import resolved
# ---------------------------------------------------------------------------


def test_absolute_sibling_import_resolved() -> None:
    source = """
__all__ = ["abs_fn"]
from mypkg.core import abs_fn
"""
    fn = _make_function("abs_fn")
    sibling = _make_module("mypkg.core", functions=(fn,))
    module, report = _resolve(source, package="mypkg", siblings={"mypkg.core": sibling})
    assert module.functions[0] == fn
    assert report.unresolved == ()


def test_absolute_import_outside_package_ignored() -> None:
    """Absolute import from a different top-level package should not be resolved."""
    source = """
__all__ = ["foreign_fn"]
from other_pkg.core import foreign_fn
"""
    fn = _make_function("foreign_fn")
    sibling = _make_module("other_pkg.core", functions=(fn,))
    # sibling is provided but shouldn't be used — it's outside mypkg
    _, report = _resolve(source, package="mypkg", siblings={"other_pkg.core": sibling})
    # foreign_fn should be unresolved since other_pkg is not a sibling of mypkg
    assert "foreign_fn" in report.unresolved


# ---------------------------------------------------------------------------
# from . import X (bare relative import, no module part)
# ---------------------------------------------------------------------------


def test_bare_relative_import_resolved() -> None:
    source = """
__all__ = ["bare_fn"]
from . import bare_fn
"""
    fn = _make_function("bare_fn")
    # level=1, no module → resolves to dotted_package itself
    sibling = _make_module("mypkg", functions=(fn,))
    module, _ = _resolve(source, package="mypkg", siblings={"mypkg": sibling})
    assert module.functions[0] == fn
