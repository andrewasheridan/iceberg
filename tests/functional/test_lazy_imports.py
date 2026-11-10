"""Test how iceberg reads lazy imports (PEP 810), which are new in Python 3.15.

iceberg parses source with the ``ast`` module of the interpreter that it runs on, so it
can read ``lazy import`` only on Python 3.15 or later. The fixture packages are written
to ``tmp_path`` and not kept in ``tests/fixtures``, because the tools that run on
Python 3.14 (ruff, pyrefly and the tests that parse every file in ``tests/``) cannot
parse them.
"""

import sys
import textwrap
from pathlib import Path

import pytest

from sheridan.iceberg._api import get_public_api
from sheridan.iceberg._config import Config
from sheridan.iceberg._formatter import format_json, format_tree
from sheridan.iceberg._models import Module, Package

pytestmark = pytest.mark.skipif(sys.version_info < (3, 15), reason="lazy imports need Python 3.15")

_CFG = Config(max_workers=1)

_CORE = """\
def thing(x: int) -> int:
    return x


class Widget:
    pass
"""

_LAZY_INIT = """\
lazy import os.path as osp
lazy from ._core import thing
lazy from ._core import Widget as W

__all__ = ["thing", "W", "osp"]
"""


def _write_package(root: Path, name: str, init_source: str) -> Path:
    """Write a package with ``init_source`` as its ``__init__.py`` and a private ``_core`` module."""
    package = root / name
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(textwrap.dedent(init_source), encoding="utf-8")
    (package / "_core.py").write_text(_CORE, encoding="utf-8")

    return package


def _snapshot_package(path: Path) -> Package:
    result = get_public_api(path, config=_CFG)

    assert isinstance(result, Package)
    return result


def _init_module(package: Package) -> Module:
    assert len(package.modules) == 1
    return package.modules[0]


def test_lazy_reexports_resolve_to_the_original_definitions(tmp_path: Path) -> None:
    init = _init_module(_snapshot_package(_write_package(tmp_path, "pkg", _LAZY_INIT)))

    assert [f.name for f in init.functions] == ["thing"]
    assert init.functions[0].returns == "int"
    assert [c.name for c in init.classes] == ["W"]


def test_lazy_output_is_the_same_as_eager_output(tmp_path: Path) -> None:
    """A lazy import binds the same name to the same object, so iceberg does not show ``lazy``.

    The tree and the JSON output are the same as for eager imports, and the JSON schema
    has no field for the keyword.
    """
    lazy = _snapshot_package(_write_package(tmp_path / "a", "pkg", _LAZY_INIT))
    eager = _snapshot_package(_write_package(tmp_path / "b", "pkg", _LAZY_INIT.replace("lazy ", "")))

    assert format_tree(lazy) == format_tree(eager)
    assert format_json(_init_module(lazy)) == format_json(_init_module(eager))


def test_lazy_module_reference_drops_the_keyword(tmp_path: Path) -> None:
    package = _snapshot_package(_write_package(tmp_path, "pkg", _LAZY_INIT))
    tree = format_tree(package)

    assert "import os.path as osp" in tree
    assert "lazy" not in tree
    assert "lazy" not in format_json(_init_module(package))


def test_lazy_import_in_module_level_if_resolves(tmp_path: Path) -> None:
    """``lazy`` is valid in a module-level ``if`` block."""
    init_source = """\
    if True:
        lazy from ._core import thing
    else:
        lazy from ._core import Widget

    __all__ = ["thing", "Widget"]
    """
    init = _init_module(_snapshot_package(_write_package(tmp_path, "pkg", init_source)))

    assert [f.name for f in init.functions] == ["thing"]
    assert [c.name for c in init.classes] == ["Widget"]


def test_lazy_import_in_module_level_with_is_the_same_as_eager(tmp_path: Path) -> None:
    """``lazy`` is valid in a module-level ``with`` block.

    iceberg does not look inside ``with`` blocks for eager imports either, so the
    output for the two forms must be the same.
    """
    init_source = """\
    import contextlib

    with contextlib.nullcontext():
        lazy from ._core import Widget

    __all__ = ["Widget"]
    """
    lazy = _snapshot_package(_write_package(tmp_path / "a", "pkg", init_source))
    eager = _snapshot_package(_write_package(tmp_path / "b", "pkg", init_source.replace("lazy ", "")))

    assert format_json(_init_module(lazy)) == format_json(_init_module(eager))


def test_lazy_import_in_module_level_try_is_accepted(tmp_path: Path) -> None:
    """``compile`` rejects ``lazy`` inside ``try``, but ``ast.parse`` accepts it.

    iceberg calls only ``ast.parse``, so it reports no error and resolves the import as
    usual.
    """
    init_source = """\
    try:
        lazy from ._core import thing
    except ImportError:
        pass

    __all__ = ["thing"]
    """
    init = _init_module(_snapshot_package(_write_package(tmp_path, "pkg", init_source)))

    assert [f.name for f in init.functions] == ["thing"]


def test_lazy_star_import_is_accepted_as_a_star_import(tmp_path: Path) -> None:
    """``compile`` rejects ``lazy from x import *``, but iceberg treats it as a star import."""
    init_source = """\
    lazy from ._core import *
    """
    init = _init_module(_snapshot_package(_write_package(tmp_path, "pkg", init_source)))

    assert [f.name for f in init.functions] == ["thing"]
    assert [c.name for c in init.classes] == ["Widget"]


def test_lazy_modules_dunder_is_not_public_api(tmp_path: Path) -> None:
    """Without ``__all__``, the module-level ``__lazy_modules__`` is not a public name."""
    source = tmp_path / "mod.py"
    source.write_text('__lazy_modules__ = ["json"]\nimport json\n\n\ndef f() -> None:\n    pass\n', encoding="utf-8")
    module = get_public_api(source, config=_CFG)

    assert isinstance(module, Module)
    assert module.assignments == ()
    assert [f.name for f in module.functions] == ["f"]
