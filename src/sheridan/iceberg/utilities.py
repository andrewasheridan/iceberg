"""Provide public utilities that inspect the API of Python code."""

__all__ = ["get_assignment", "get_class", "get_function", "get_module", "get_package"]

import ast
import inspect
import textwrap
import types
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, overload

from sheridan.iceberg._api import get_public_api
from sheridan.iceberg._builders import (
    build_assignment,
    build_assignments,
    build_class,
    build_function,
    build_type_alias,
)
from sheridan.iceberg._exceptions import InvalidPathError, NotFoundError, ParseError
from sheridan.iceberg._models import Assignment, Class, Function, Module, Package
from sheridan.iceberg._utilities import module_level_statements, parse_source, read_source
from sheridan.iceberg._visitor import visit_module


def _read(source: str | Path) -> str:
    """Dedent a source string, or read the text of the file at a ``Path``.

    Raises:
        InvalidPathError: If the function cannot read a ``Path``.
    """
    if isinstance(source, Path):
        return read_source(source)

    return textwrap.dedent(source)


def _parse(source: str | Path) -> ast.Module:
    """Parse a source string or the file at a ``Path``, as ``_read`` reads it.

    Raises:
        ParseError: If the source is not valid Python.
        InvalidPathError: If the function cannot read a ``Path``.
    """
    path = source if isinstance(source, Path) else None
    return parse_source(_read(source), path)


def _required_name(name: str | None) -> str:
    """Check that the caller gave *name*. A ``Path`` input needs it to select a definition.

    Raises:
        TypeError: If *name* is ``None``.
    """
    if name is None:
        raise TypeError("give name when you give a Path")

    return name


def _get_source(obj: object) -> str:
    """Find the source of *obj* with ``inspect.getsource``.

    Args:
        obj: A function or class object.

    Returns:
        The source code of *obj*.

    Raises:
        InvalidPathError: If *obj* is a lambda, or if the function cannot find
            its source (builtins, C extension types, objects that a REPL or
            ``exec`` defined).
    """
    if getattr(obj, "__name__", None) == "<lambda>":
        raise InvalidPathError(f"Cannot build a Function from a lambda: {obj!r}. Give a def function.")

    try:
        return inspect.getsource(obj)  # type: ignore[arg-type]
    except (OSError, TypeError) as exc:
        raise InvalidPathError(f"Cannot find the source of {obj!r}: {exc}") from exc


_DefNode = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


def _scope_definitions(body: list[ast.stmt]) -> Iterator[_DefNode]:
    """Yield the definitions in the scope that has the statements *body*.

    The function includes, in source order, the definitions in compound
    statements that do not open a new scope (``if``, ``try``, ``with``,
    ``for``, ``while``, ``match``). It does not go into the bodies of
    functions and classes.
    """
    for stmt in body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield stmt
            continue

        for field in ("body", "orelse", "finalbody"):
            yield from _scope_definitions(getattr(stmt, field, []))

        for handler in getattr(stmt, "handlers", []):
            yield from _scope_definitions(handler.body)

        for case in getattr(stmt, "cases", []):
            yield from _scope_definitions(case.body)


def _find_definition(tree: ast.Module, name: str, kind: type[_DefNode] | tuple[type[_DefNode], ...]) -> _DefNode | None:
    """Find the definition of *kind* with the name *name* in *tree*.

    The function resolves a dotted *name* (``Outer.Inner.method``) one part at
    a time. It finds each part in the scope of the definition before it. For a
    plain *name*, it first searches the module-level definitions. If none
    matches, it gives the first nested definition with that name.
    """
    *parents, leaf = name.split(".")

    body: list[ast.stmt] = tree.body
    for part in parents:
        parent = next((node for node in _scope_definitions(body) if node.name == part), None)
        if parent is None:
            return None

        body = parent.body

    for node in _scope_definitions(body):
        if isinstance(node, kind) and node.name == leaf:
            return node

    if parents:
        return None

    for walked in ast.walk(tree):
        if isinstance(walked, kind) and walked.name == leaf:
            return walked

    return None


def _find_assignment(tree: ast.Module, name: str | None) -> Assignment | None:
    """Find the first module-level assignment that binds *name* in *tree*.

    The function searches the module-level ``if`` and ``try`` blocks, as
    ``get_module`` does. It uses each name that an ``Assign`` binds. This
    includes each target of a chained assignment (``a = b = 1``) and each name
    in tuple, list or starred unpacking. The first definition of *name* has
    priority.

    Args:
        tree: The parsed module AST.
        name: The name to find, or ``None`` for the first assignment.

    Returns:
        The ``Assignment`` that binds *name*, or ``None`` if there is no such assignment.
    """
    for node in module_level_statements(tree.body):
        candidates: list[Assignment]
        match node:
            case ast.Assign():
                candidates = build_assignments(node)

            case ast.AnnAssign():
                result = build_assignment(node)
                candidates = [] if result is None else [result]

            case ast.TypeAlias():
                candidates = [build_type_alias(node)]

            case _:
                continue

        for candidate in candidates:
            if name is None or candidate.name == name:
                return candidate

    return None


@overload
def get_function(source: str, /) -> Function: ...
@overload
def get_function(node: ast.FunctionDef | ast.AsyncFunctionDef, /) -> Function: ...
@overload
def get_function(path: Path, /, *, name: str) -> Function: ...
@overload
def get_function(func: Callable[..., Any], /) -> Function: ...


def get_function(
    source_or_node_or_path_or_func: str | ast.FunctionDef | ast.AsyncFunctionDef | Path | Callable[..., Any],
    *,
    name: str | None = None,
) -> Function:
    """Build a ``Function`` model from one of four input forms.

    The function accepts these forms:

    - **Raw source string**: A string that contains a ``def`` or ``async def``
      statement. The function dedents the source before it parses it. It gives
      the first function definition that it finds.
    - **AST node**: An ``ast.FunctionDef`` or ``ast.AsyncFunctionDef`` node
      that the caller parsed.
    - **Path + name**: A ``pathlib.Path`` to a ``.py`` file, together with the
      keyword argument ``name``. ``name`` identifies the function to extract.
      The function searches the module-level functions first. A dotted name
      such as ``"MyClass.method"`` selects a function in a class or function.
    - **Callable**: A callable object with a source that
      ``inspect.getsource`` can get. The function sends the source to the
      branch for strings.

    Args:
        source_or_node_or_path_or_func: A raw Python source string, an
            ``ast.FunctionDef`` / ``ast.AsyncFunctionDef`` node, a
            ``pathlib.Path`` to a source file, or a callable.
        name: Necessary if you give a ``Path``. It identifies the function to
            extract by name or by dotted qualified name. The other input forms ignore it.

    Returns:
        A ``Function`` dataclass with the name, the parameters, the return
        annotation, the async flag, the kind, the decorators and the overloads
        of the target function.

    Raises:
        ParseError: If a source string or file is not valid Python, or if the
            source string has no function definition.
        NotFoundError: If you give a ``Path``, but the file has no function
            with the given ``name``.
        InvalidPathError: If a callable is a lambda, or if the function cannot
            find the source of a callable (builtins, functions that a REPL or
            ``exec`` defined).
        TypeError: If you give a ``Path`` without ``name``.
    """
    match source_or_node_or_path_or_func:
        case ast.FunctionDef() | ast.AsyncFunctionDef():
            return build_function(source_or_node_or_path_or_func)

        case str():
            for node in ast.walk(_parse(source_or_node_or_path_or_func)):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    return build_function(node)

            raise ParseError("The source has no function definition")

        case Path():
            tree = _parse(source_or_node_or_path_or_func)
            func_node = _find_definition(tree, _required_name(name), (ast.FunctionDef, ast.AsyncFunctionDef))
            if isinstance(func_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return build_function(func_node)

            raise NotFoundError(f"{source_or_node_or_path_or_func} has no function {name!r}")

        case _:
            return get_function(_get_source(source_or_node_or_path_or_func))


@overload
def get_class(source: str, /) -> Class: ...
@overload
def get_class(node: ast.ClassDef, /) -> Class: ...
@overload
def get_class(path: Path, /, *, name: str) -> Class: ...
@overload
def get_class(cls: type, /) -> Class: ...


def get_class(
    source_or_node_or_path_or_cls: str | ast.ClassDef | Path | type,
    *,
    name: str | None = None,
) -> Class:
    """Build a ``Class`` model from one of four input forms.

    The function accepts these forms:

    - **Raw source string**: A string that contains a ``class`` statement. The
      function dedents the source before it parses it. It gives the first
      class definition that it finds.
    - **AST node**: An ``ast.ClassDef`` node that the caller parsed.
    - **Path + name**: A ``pathlib.Path`` to a ``.py`` file, together with the
      keyword argument ``name``. ``name`` identifies the class to extract. The
      function searches the module-level classes first. A dotted name such as
      ``"Outer.Inner"`` selects a nested class.
    - **type**: A class object with a source that ``inspect.getsource`` can
      get. The function sends the source to the branch for strings.

    Args:
        source_or_node_or_path_or_cls: A raw Python source string, an
            ``ast.ClassDef`` node, a ``pathlib.Path`` to a source file, or a
            class object.
        name: Necessary if you give a ``Path``. It identifies the class to
            extract by name or by dotted qualified name. The other input forms ignore it.

    Returns:
        A ``Class`` dataclass with the name, the bases, the keyword arguments
        (such as ``metaclass=``) and the members of the target class.

    Raises:
        ParseError: If a source string or file is not valid Python, or if the
            source string has no class definition.
        NotFoundError: If you give a ``Path``, but the file has no class with
            the given ``name``.
        InvalidPathError: If the function cannot find the source of a class
            object (C extension types, classes that a REPL or ``exec``
            defined).
        TypeError: If you give a ``Path`` without ``name``.
    """
    match source_or_node_or_path_or_cls:
        case ast.ClassDef():
            return build_class(source_or_node_or_path_or_cls)

        case str():
            for node in ast.walk(_parse(source_or_node_or_path_or_cls)):
                if isinstance(node, ast.ClassDef):
                    return build_class(node)

            raise ParseError("The source has no class definition")

        case Path():
            tree = _parse(source_or_node_or_path_or_cls)
            class_node = _find_definition(tree, _required_name(name), ast.ClassDef)
            if isinstance(class_node, ast.ClassDef):
                return build_class(class_node)

            raise NotFoundError(f"{source_or_node_or_path_or_cls} has no class {name!r}")

        case _:
            return get_class(_get_source(source_or_node_or_path_or_cls))


@overload
def get_assignment(source: str, /, *, name: str | None = ...) -> Assignment: ...
@overload
def get_assignment(node: ast.Assign | ast.AnnAssign | ast.TypeAlias, /) -> Assignment: ...
@overload
def get_assignment(path: Path, /, *, name: str) -> Assignment: ...


def get_assignment(
    source_or_node_or_path: str | ast.Assign | ast.AnnAssign | ast.TypeAlias | Path,
    *,
    name: str | None = None,
) -> Assignment:
    """Build an ``Assignment`` model from one of three input forms.

    The function accepts these forms:

    - **Raw source string**: A string that contains an assignment statement.
      The function dedents the source before it parses it. It gives the first
      assignment that matches. To select an assignment by target name, give ``name``.
    - **AST node**: An ``ast.Assign``, ``ast.AnnAssign`` or ``ast.TypeAlias``
      node that the caller parsed.
    - **Path + name**: A ``pathlib.Path`` to a ``.py`` file, together with the
      keyword argument ``name``. ``name`` identifies the assignment to extract.

    For the string and path forms, the function searches the module-level
    ``if`` and ``try`` blocks. You can select each name that an assignment
    binds. This includes each target of a chained assignment (``a = b = 1``)
    and each name in tuple, list or starred unpacking (``c, *rest = ...``). If
    many assignments bind the same name, the function gives the first one, as
    ``get_module`` does.

    Args:
        source_or_node_or_path: A raw Python source string, an
            ``ast.Assign`` / ``ast.AnnAssign`` / ``ast.TypeAlias`` node, or a
            ``pathlib.Path`` to a source file.
        name: Necessary if you give a ``Path``. It identifies the assignment
            to extract by target name. If you give a source string, it is
            optional. It then selects the assignment with the given target name.

    Returns:
        An ``Assignment`` dataclass with the target name and the annotation of
        the assignment.

    Raises:
        ParseError: If a source string or file is not valid Python, if the
            target of an AST node is not a simple name, or if no assignment in the
            source matches.
        NotFoundError: If you give a ``Path``, but the file has no assignment
            with the given ``name``.
        TypeError: If you give a ``Path`` without ``name``.
    """
    match source_or_node_or_path:
        case ast.TypeAlias():
            return build_type_alias(source_or_node_or_path)

        case ast.Assign() | ast.AnnAssign():
            result = build_assignment(source_or_node_or_path)
            if result is None:
                raise ParseError("The target of the assignment is not a simple name")

            return result

        case str():
            found = _find_assignment(_parse(source_or_node_or_path), name)
            if found is not None:
                return found

            if name is not None:
                raise ParseError(f"The source has no assignment {name!r}")

            raise ParseError("The source has no assignment")

        case Path():
            found = _find_assignment(_parse(source_or_node_or_path), _required_name(name))
            if found is not None:
                return found

            raise NotFoundError(f"{source_or_node_or_path} has no assignment {name!r}")


@overload
def get_module(source: str, /, *, name: str | None = ...) -> Module: ...
@overload
def get_module(path: Path, /, *, name: str | None = ...) -> Module: ...
@overload
def get_module(mod: types.ModuleType, /) -> Module: ...


def get_module(
    source_or_path_or_mod: str | Path | types.ModuleType,
    *,
    name: str | None = None,
) -> Module:
    """Build a ``Module`` model from one of three input forms.

    The function accepts these forms:

    - **Raw source string**: A string that contains the body of a Python
      module. The function dedents the source before it parses it. To set the
      dotted module name, give ``name``. The default is ``"<module>"``.
    - **Path**: A ``pathlib.Path`` to a ``.py`` file. To set a different
      dotted module name, give ``name``. The default is the file stem.
    - **ModuleType**: A live ``types.ModuleType`` object. The function finds
      its source file with ``inspect.getsourcefile``. The default dotted name
      is ``mod.__name__``.

    Args:
        source_or_path_or_mod: A raw Python source string, a ``pathlib.Path``
            to a source file, or a ``types.ModuleType`` object.
        name: The dotted module name for the ``Module`` model. It replaces the
            default name. It is optional for all input forms.

    Returns:
        A ``Module`` dataclass with the name and the public API of the target
        module.

    Raises:
        ParseError: If a source string or file is not valid Python.
        InvalidPathError: If you give a ``ModuleType``, but the function cannot
            find its source file (for example, a builtin module).
    """
    match source_or_path_or_mod:
        case str():
            return visit_module(_read(source_or_path_or_mod), name or "<module>")

        case Path():
            text = _read(source_or_path_or_mod)
            return visit_module(text, name or source_or_path_or_mod.stem, path=source_or_path_or_mod)

        case _:
            try:
                sf = inspect.getsourcefile(source_or_path_or_mod)
            except TypeError:
                sf = None

            if sf is None:
                raise InvalidPathError(f"Cannot find the source of module {source_or_path_or_mod!r}")

            return get_module(Path(sf), name=name or source_or_path_or_mod.__name__)


@overload
def get_package(path: Path, /) -> Package: ...
@overload
def get_package(path: str, /) -> Package: ...
@overload
def get_package(mod: types.ModuleType, /) -> Package: ...


def get_package(
    path_or_mod: Path | str | types.ModuleType,
) -> Package:
    """Build a ``Package`` model from one of three input forms.

    The function accepts these forms:

    - **Path**: A ``pathlib.Path`` to a package directory (a directory that
      contains an ``__init__.py``). The function walks through the directory
      to build the public API.
    - **str**: A string filesystem path. The function converts it to a
      ``pathlib.Path`` and sends it to the branch for ``Path``.
    - **ModuleType**: A live package object. The function reads the package
      directory from its ``__path__``. The function does not accept a plain
      module (no ``__path__``) or a namespace package with more than one
      portion.

    Args:
        path_or_mod: A ``pathlib.Path`` to a package directory, a string path
            to a package directory, or a package object.

    Returns:
        A ``Package`` dataclass with the name and the public API of the target
        package.

    Raises:
        InvalidPathError: If the resolved path points to a module and not to a
            package, if a ``ModuleType`` is a plain module and not a package,
            or if it is a namespace package with more than one portion.
    """
    match path_or_mod:
        case str():
            return get_package(Path(path_or_mod))

        case Path():
            result = get_public_api(path_or_mod)
            if isinstance(result, Package):
                return result

            raise InvalidPathError(f"{path_or_mod} points to a module, not a package. Use get_module().")

        case _:
            return get_package(_package_dir(path_or_mod))


def _package_dir(mod: types.ModuleType) -> Path:
    """Find the directory of the package *mod* from its ``__path__``.

    Raises:
        InvalidPathError: If *mod* is not a package (it has no ``__path__``),
            or if it is a namespace package with more than one portion.
    """
    search_path = getattr(mod, "__path__", None)
    if search_path is None:
        raise InvalidPathError(f"{mod.__name__} is a module, not a package. Use get_module().")

    portions = list(dict.fromkeys(search_path))
    if len(portions) != 1:
        raise InvalidPathError(
            f"{mod.__name__} is a namespace package with {len(portions)} portions "
            f"({', '.join(portions)}). Give the path of one portion to get_package()."
        )

    return Path(portions[0])
