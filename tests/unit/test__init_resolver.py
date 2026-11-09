"""Tests for sheridan.iceberg._init_resolver (resolve_init and ResolveReport)."""

from pathlib import Path

import pytest

from sheridan.iceberg._exceptions import ParseError
from sheridan.iceberg._init_resolver import ResolveReport, resolve_init, resolve_module_references
from sheridan.iceberg._models import Assignment, Class, Function, Module, Reference

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
) -> tuple[Module, ResolveReport]:
    return resolve_init(
        init_source=source,
        dotted_package=package,
        sibling_modules=siblings if siblings is not None else {},
        subpackage_names=subpackage_names,
    )


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


def test_subpackage_names_excluded_from_members() -> None:
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
    )
    assert module.functions == (fn,)
    # sub is a subpackage name — resolver skips it silently (not in unresolved)
    assert "sub" not in report.unresolved
    assert module.references == ()


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


def test_returned_module_name_matches_dotted_package() -> None:
    source = "__all__ = []\n"
    module, _ = _resolve(source, package="org.lib.sub")
    assert module.name == "org.lib.sub"


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


def test_unresolved_external_reexport_becomes_reference() -> None:
    source = """
__all__ = ["sqrt"]
from math import sqrt
"""
    module, report = _resolve(source)
    assert module.references == (Reference(name="sqrt", module="math", attribute="sqrt"),)
    assert report.unresolved == ("sqrt",)


def test_unresolved_aliased_external_reexport_keeps_original_attribute() -> None:
    source = """
__all__ = ["Ordered"]
from collections import OrderedDict as Ordered
"""
    module, _ = _resolve(source)
    assert module.references == (Reference(name="Ordered", module="collections", attribute="OrderedDict"),)


def test_unresolved_module_import_becomes_reference() -> None:
    source = """
__all__ = ["json"]
import json
"""
    module, _ = _resolve(source)
    assert module.references == (Reference(name="json", module="json", attribute=None),)


def test_unbound_name_becomes_reference_without_source() -> None:
    source = """
__all__ = ["ghost"]
"""
    module, _ = _resolve(source)
    assert module.references == (Reference(name="ghost", module=None, attribute=None),)


def test_intra_package_lookup_failure_reference_is_absolute() -> None:
    source = """
__all__ = ["missing"]
from ._core import missing
"""
    module, _ = _resolve(source, siblings={"mypkg._core": _make_module("mypkg._core")})
    assert module.references == (Reference(name="missing", module="mypkg._core", attribute="missing"),)


def test_resolved_names_are_not_references() -> None:
    source = """
__all__ = ["real_func"]
from .core import real_func
"""
    sibling = _make_module("mypkg.core", functions=(_make_function("real_func"),))
    module, _ = _resolve(source, siblings={"mypkg.core": sibling})
    assert module.references == ()


def test_child_names_are_not_references() -> None:
    source = """
__all__ = ["sub", "helpers"]
"""
    module, report = _resolve(source, subpackage_names=frozenset({"sub", "helpers"}))
    assert module.references == ()
    assert report.unresolved == ()


def test_no_all_external_imports_are_not_public() -> None:
    source = """
from pathlib import Path
"""
    module, _ = _resolve(source)
    assert module.references == ()


def test_try_except_reexport_resolved_from_first_branch() -> None:
    source = """
__all__ = ["parse"]
try:
    from ._fast import parse
except ImportError:
    from ._slow import parse
"""
    fast = _make_function("parse")
    siblings = {
        "mypkg._fast": _make_module("mypkg._fast", functions=(fast,)),
        "mypkg._slow": _make_module("mypkg._slow", functions=(_make_function("other"),)),
    }
    module, report = _resolve(source, siblings=siblings)
    assert module.functions == (fast,)
    assert report.unresolved == ()


def test_absolute_import_from_elsewhere_in_root_package_resolved() -> None:
    source = """
__all__ = ["fn"]
from mypkg.other import fn
"""
    fn = _make_function("fn")
    module, _ = _resolve(
        source, package="mypkg.sub", siblings={"mypkg.other": _make_module("mypkg.other", functions=(fn,))}
    )
    assert module.functions == (fn,)


def test_namespace_prefixed_absolute_import_resolved() -> None:
    source = """
__all__ = ["get_public_api"]
from sheridan.iceberg._api import get_public_api
"""
    fn = _make_function("get_public_api")
    module, report = resolve_init(
        init_source=source,
        dotted_package="iceberg",
        sibling_modules={"iceberg._api": _make_module("iceberg._api", functions=(fn,))},
        subpackage_names=frozenset(),
        namespace_parents=("home", "src", "sheridan"),
    )
    assert module.functions == (fn,)
    assert report.unresolved == ()


def test_namespace_prefix_must_match_directories_above_root() -> None:
    source = """
__all__ = ["get_public_api"]
from other.iceberg._api import get_public_api
"""
    fn = _make_function("get_public_api")
    module, report = resolve_init(
        init_source=source,
        dotted_package="iceberg",
        sibling_modules={"iceberg._api": _make_module("iceberg._api", functions=(fn,))},
        subpackage_names=frozenset(),
        namespace_parents=("src", "sheridan"),
    )
    assert module.functions == ()
    assert module.references == (
        Reference(name="get_public_api", module="other.iceberg._api", attribute="get_public_api"),
    )
    assert report.unresolved == ("get_public_api",)


def test_multi_level_namespace_prefix_resolved() -> None:
    source = """
__all__ = ["fn"]
from org.team.pkg.core import fn
"""
    fn = _make_function("fn")
    module, _ = resolve_init(
        init_source=source,
        dotted_package="pkg",
        sibling_modules={"pkg.core": _make_module("pkg.core", functions=(fn,))},
        subpackage_names=frozenset(),
        namespace_parents=("src", "org", "team"),
    )
    assert module.functions == (fn,)


def test_syntax_error_reports_init_path() -> None:
    with pytest.raises(ParseError) as info:
        resolve_init("def broken(:", "pkg", {}, frozenset(), path=Path("src/pkg/__init__.py"))
    assert info.value.path == "src/pkg/__init__.py"
    assert info.value.lineno == 1


def test_module_references_follow_three_module_chain() -> None:
    cls = _make_class("X")
    modules = {
        "pkg._a": Module("pkg._a", (), (), (), (Reference("X", "pkg._b", "X"),)),
        "pkg._b": Module("pkg._b", (), (), (), (Reference("X", "pkg._c", "X"),)),
        "pkg._c": _make_module("pkg._c", classes=(cls,)),
    }
    resolved = resolve_module_references(modules)
    assert resolved["pkg._a"].classes == (cls,)
    assert resolved["pkg._a"].references == ()
    assert resolved["pkg._b"].classes == (cls,)
    assert resolved["pkg._c"] is modules["pkg._c"]


def test_module_references_aliased_import_renamed() -> None:
    fn = _make_function("f")
    modules = {
        "pkg._a": Module("pkg._a", (), (), (), (Reference("g", "pkg._b", "f"),)),
        "pkg._b": _make_module("pkg._b", functions=(fn,)),
    }
    resolved = resolve_module_references(modules)
    assert resolved["pkg._a"].functions == (_make_function("g"),)


def test_module_references_namespace_prefix_resolved() -> None:
    value = _make_assignment("V")
    modules = {
        "pkg._a": Module("pkg._a", (), (), (), (Reference("V", "org.pkg._b", "V"),)),
        "pkg._b": _make_module("pkg._b", assignments=(value,)),
    }
    resolved = resolve_module_references(modules, namespace_parents=("src", "org"))
    assert resolved["pkg._a"].assignments == (value,)


def test_module_references_cycle_leaves_reference() -> None:
    a_ref = Reference("X", "pkg._b", "X")
    b_ref = Reference("X", "pkg._a", "X")
    modules = {
        "pkg._a": Module("pkg._a", (), (), (), (a_ref,)),
        "pkg._b": Module("pkg._b", (), (), (), (b_ref,)),
    }
    resolved = resolve_module_references(modules)
    assert resolved["pkg._a"].references == (a_ref,)
    assert resolved["pkg._b"].references == (b_ref,)
    assert resolved["pkg._a"].classes == resolved["pkg._b"].classes == ()


def test_module_references_cycle_still_finds_definitions() -> None:
    x = _make_class("X")
    y = _make_class("Y")
    modules = {
        "pkg._a": Module("pkg._a", (), (y,), (), (Reference("X", "pkg._b", "X"),)),
        "pkg._b": Module("pkg._b", (), (x,), (), (Reference("Y", "pkg._a", "Y"),)),
    }
    resolved = resolve_module_references(modules)
    assert resolved["pkg._a"].classes == (y, x)
    assert resolved["pkg._b"].classes == (x, y)


def test_module_references_outside_tree_kept() -> None:
    ref = Reference("sqrt", "math", "sqrt")
    modules = {"pkg._a": Module("pkg._a", (), (), (), (ref,))}
    assert resolve_module_references(modules)["pkg._a"].references == (ref,)
