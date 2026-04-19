"""Public utilities for inspecting Python API surfaces."""

__all__ = ["get_assignment", "get_class", "get_function", "get_module", "get_package"]

import ast
import inspect
import textwrap
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any, overload

from sheridan.iceberg._api import get_public_api
from sheridan.iceberg._exceptions import InvalidPathError, ParseError
from sheridan.iceberg._models import Assignment, Class, Function, Module, Package
from sheridan.iceberg._visitor import _build_assignment, _build_class, _build_function, _build_type_alias, visit_module


@overload
def get_function(source: str) -> Function: ...
@overload
def get_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> Function: ...
@overload
def get_function(path: Path, *, name: str) -> Function: ...
@overload
def get_function(func: Callable[..., Any]) -> Function: ...


def get_function(
    source_or_node_or_path_or_func: str | ast.FunctionDef | ast.AsyncFunctionDef | Path | Callable[..., Any],
    *,
    name: str | None = None,
) -> Function:
    """Return a ``Function`` model from one of four accepted input forms.

    Accepted forms:

    - **Raw source string**: A string containing a ``def`` or ``async def``
      statement. The source is dedented before parsing; the first function
      definition found is returned.
    - **AST node**: An ``ast.FunctionDef`` or ``ast.AsyncFunctionDef`` node
      that has already been parsed by the caller.
    - **Path + name**: A ``pathlib.Path`` pointing to a ``.py`` file together
      with the keyword argument ``name`` identifying which function to extract.
    - **Callable**: Any callable object whose source can be retrieved via
      ``inspect.getsource``; the source is forwarded to the string dispatch
      branch.

    Args:
        source_or_node_or_path_or_func: One of: a raw Python source string,
            an ``ast.FunctionDef`` / ``ast.AsyncFunctionDef`` node, a
            ``pathlib.Path`` to a source file, or any callable.
        name: Required when passing a ``Path``; identifies the function to
            extract by name. Ignored for all other input forms.

    Returns:
        A ``Function`` dataclass capturing the name, parameters, return
        annotation, and async flag of the target function.

    Raises:
        ParseError: When a source string or file cannot be parsed as valid
            Python, or when no function definition is found in the provided
            source string.
        InvalidPathError: When a ``Path`` is provided but no function with
            the given ``name`` is found in that file.
        TypeError: When a ``Path`` is provided without supplying ``name``.
    """
    match source_or_node_or_path_or_func:
        case ast.FunctionDef() | ast.AsyncFunctionDef():
            return _build_function(source_or_node_or_path_or_func)

        case str():
            src = textwrap.dedent(source_or_node_or_path_or_func)
            try:
                tree = ast.parse(src)
            except SyntaxError as exc:
                raise ParseError(str(exc)) from exc
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    return _build_function(node)
            raise ParseError("No function definition found in source")

        case Path():
            if name is None:
                raise TypeError("name is required when passing a Path")
            src = source_or_node_or_path_or_func.read_text(encoding="utf-8")
            try:
                tree = ast.parse(src)
            except SyntaxError as exc:
                raise ParseError(str(exc)) from exc
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                    return _build_function(node)
            raise InvalidPathError(f"No function {name!r} found in {source_or_node_or_path_or_func}")

        case _:
            src = inspect.getsource(source_or_node_or_path_or_func)
            return get_function(src)


@overload
def get_class(source: str) -> Class: ...
@overload
def get_class(node: ast.ClassDef) -> Class: ...
@overload
def get_class(path: Path, *, name: str) -> Class: ...
@overload
def get_class(cls: type) -> Class: ...


def get_class(
    source_or_node_or_path_or_cls: str | ast.ClassDef | Path | type,
    *,
    name: str | None = None,
) -> Class:
    """Return a ``Class`` model from one of four accepted input forms.

    Accepted forms:

    - **Raw source string**: A string containing a ``class`` statement. The
      source is dedented before parsing; the first class definition found is
      returned.
    - **AST node**: An ``ast.ClassDef`` node that has already been parsed by
      the caller.
    - **Path + name**: A ``pathlib.Path`` pointing to a ``.py`` file together
      with the keyword argument ``name`` identifying which class to extract.
    - **type**: Any class object whose source can be retrieved via
      ``inspect.getsource``; the source is forwarded to the string dispatch
      branch.

    Args:
        source_or_node_or_path_or_cls: One of: a raw Python source string,
            an ``ast.ClassDef`` node, a ``pathlib.Path`` to a source file,
            or any class object.
        name: Required when passing a ``Path``; identifies the class to
            extract by name. Ignored for all other input forms.

    Returns:
        A ``Class`` dataclass capturing the name, bases, and members of the
        target class.

    Raises:
        ParseError: When a source string or file cannot be parsed as valid
            Python, or when no class definition is found in the provided
            source string.
        InvalidPathError: When a ``Path`` is provided but no class with the
            given ``name`` is found in that file.
        TypeError: When a ``Path`` is provided without supplying ``name``.
    """
    match source_or_node_or_path_or_cls:
        case ast.ClassDef():
            return _build_class(source_or_node_or_path_or_cls)

        case str():
            src = textwrap.dedent(source_or_node_or_path_or_cls)
            try:
                tree = ast.parse(src)
            except SyntaxError as exc:
                raise ParseError(str(exc)) from exc
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    return _build_class(node)
            raise ParseError("No class definition found in source")

        case Path():
            if name is None:
                raise TypeError("name is required when passing a Path")
            src = source_or_node_or_path_or_cls.read_text(encoding="utf-8")
            try:
                tree = ast.parse(src)
            except SyntaxError as exc:
                raise ParseError(str(exc)) from exc
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == name:
                    return _build_class(node)
            raise InvalidPathError(f"No class {name!r} found in {source_or_node_or_path_or_cls}")

        case _:
            src = inspect.getsource(source_or_node_or_path_or_cls)
            return get_class(src)


@overload
def get_assignment(source: str, *, name: str | None = ...) -> Assignment: ...
@overload
def get_assignment(node: ast.Assign | ast.AnnAssign | ast.TypeAlias) -> Assignment: ...
@overload
def get_assignment(path: Path, *, name: str) -> Assignment: ...


def get_assignment(
    source_or_node_or_path: str | ast.Assign | ast.AnnAssign | ast.TypeAlias | Path,
    *,
    name: str | None = None,
) -> Assignment:
    """Return an ``Assignment`` model from one of three accepted input forms.

    Accepted forms:

    - **Raw source string**: A string containing an assignment statement. The
      source is dedented before parsing; the first matching assignment is
      returned. Pass ``name`` to select a specific assignment by target name.
    - **AST node**: An ``ast.Assign``, ``ast.AnnAssign``, or ``ast.TypeAlias``
      node that has already been parsed by the caller.
    - **Path + name**: A ``pathlib.Path`` pointing to a ``.py`` file together
      with the keyword argument ``name`` identifying which assignment to
      extract.

    Args:
        source_or_node_or_path: One of: a raw Python source string, an
            ``ast.Assign`` / ``ast.AnnAssign`` / ``ast.TypeAlias`` node, or a
            ``pathlib.Path`` to a source file.
        name: When passing a ``Path``, required; identifies the assignment to
            extract by target name. When passing a source string, optionally
            filters to the assignment with the given target name.

    Returns:
        An ``Assignment`` dataclass capturing the target name, annotation, and
        value of the assignment.

    Raises:
        ParseError: When a source string or file cannot be parsed as valid
            Python, when the target of an AST node is non-simple, or when no
            matching assignment is found in the provided source.
        InvalidPathError: When a ``Path`` is provided but no assignment with
            the given ``name`` is found in that file.
        TypeError: When a ``Path`` is provided without supplying ``name``.
    """
    match source_or_node_or_path:
        case ast.TypeAlias():
            return _build_type_alias(source_or_node_or_path)

        case ast.Assign() | ast.AnnAssign():
            result = _build_assignment(source_or_node_or_path)
            if result is None:
                raise ParseError("Assignment has a non-simple target")
            return result

        case str():
            src = textwrap.dedent(source_or_node_or_path)
            try:
                tree = ast.parse(src)
            except SyntaxError as exc:
                raise ParseError(str(exc)) from exc
            for node in tree.body:
                if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.TypeAlias)):
                    continue
                node_name: str | None
                match node:
                    case ast.AnnAssign(target=ast.Name(id=n)):
                        node_name = n
                    case ast.Assign(targets=[ast.Name(id=n)]):
                        node_name = n
                    case ast.TypeAlias(name=ast.Name(id=n)):
                        node_name = n
                    case _:
                        node_name = None
                if name is not None and node_name != name:
                    continue
                if isinstance(node, ast.TypeAlias):
                    return _build_type_alias(node)
                result = _build_assignment(node)
                if result is None:
                    continue
                return result
            if name is not None:
                raise ParseError(f"No assignment {name!r} found in source")
            raise ParseError("No assignment found in source")

        case Path():
            if name is None:
                raise TypeError("name is required when passing a Path")
            src = source_or_node_or_path.read_text(encoding="utf-8")
            try:
                tree = ast.parse(src)
            except SyntaxError as exc:
                raise ParseError(str(exc)) from exc
            for node in tree.body:
                if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.TypeAlias)):
                    continue
                node_name_p: str | None
                match node:
                    case ast.AnnAssign(target=ast.Name(id=n)):
                        node_name_p = n
                    case ast.Assign(targets=[ast.Name(id=n)]):
                        node_name_p = n
                    case ast.TypeAlias(name=ast.Name(id=n)):
                        node_name_p = n
                    case _:
                        node_name_p = None
                if node_name_p != name:
                    continue
                if isinstance(node, ast.TypeAlias):
                    return _build_type_alias(node)
                result = _build_assignment(node)
                if result is None:
                    continue
                return result
            raise InvalidPathError(f"No assignment {name!r} found in {source_or_node_or_path}")


@overload
def get_module(source: str, *, name: str = ...) -> Module: ...
@overload
def get_module(path: Path, *, name: str = ...) -> Module: ...
@overload
def get_module(mod: types.ModuleType) -> Module: ...


def get_module(
    source_or_path_or_mod: str | Path | types.ModuleType,
    *,
    name: str | None = None,
) -> Module:
    """Return a ``Module`` model from one of three accepted input forms.

    Accepted forms:

    - **Raw source string**: A string containing a Python module body. The
      source is dedented before parsing. Pass ``name`` to set the dotted
      module name; defaults to ``"<module>"``.
    - **Path**: A ``pathlib.Path`` pointing to a ``.py`` file. Pass ``name``
      to override the dotted module name; defaults to the file stem.
    - **ModuleType**: A live ``types.ModuleType`` object whose source file is
      located via ``inspect.getsourcefile``; the dotted name defaults to
      ``mod.__name__``.

    Args:
        source_or_path_or_mod: One of: a raw Python source string, a
            ``pathlib.Path`` to a source file, or a ``types.ModuleType``
            object.
        name: Overrides the dotted module name used when building the
            ``Module`` model. Optional for all input forms.

    Returns:
        A ``Module`` dataclass capturing the name and public API of the
        target module.

    Raises:
        ParseError: When a source string or file cannot be parsed as valid
            Python.
        InvalidPathError: When a ``ModuleType`` is provided but its source
            file cannot be located.
    """
    match source_or_path_or_mod:
        case str():
            src = textwrap.dedent(source_or_path_or_mod)
            dotted = name or "<module>"
            return visit_module(src, dotted)

        case Path():
            text = source_or_path_or_mod.read_text(encoding="utf-8")
            dotted = name or source_or_path_or_mod.stem
            return visit_module(text, dotted)

        case _:
            sf = inspect.getsourcefile(source_or_path_or_mod)
            if sf is None:
                raise InvalidPathError(f"Cannot locate source for module {source_or_path_or_mod!r}")
            return get_module(Path(sf), name=name or source_or_path_or_mod.__name__)


@overload
def get_package(path: Path) -> Package: ...
@overload
def get_package(path: str) -> Package: ...
@overload
def get_package(mod: types.ModuleType) -> Package: ...


def get_package(
    path_or_mod: Path | str | types.ModuleType,
) -> Package:
    """Return a ``Package`` model from one of three accepted input forms.

    Accepted forms:

    - **Path**: A ``pathlib.Path`` pointing to a package directory (one
      containing an ``__init__.py``). The public API is built by walking
      the directory.
    - **str**: A string file-system path; converted to ``pathlib.Path`` and
      forwarded to the ``Path`` dispatch branch.
    - **ModuleType**: A live ``types.ModuleType`` object; the package
      directory is inferred from the location of the module's source file
      via ``inspect.getfile``.

    Args:
        path_or_mod: One of: a ``pathlib.Path`` to a package directory, a
            string path to a package directory, or a ``types.ModuleType``
            object belonging to the package.

    Returns:
        A ``Package`` dataclass capturing the name and public API of the
        target package.

    Raises:
        InvalidPathError: When the resolved path points to a module rather
            than a package, or when the source file for a ``ModuleType``
            cannot be located.
    """
    match path_or_mod:
        case str():
            return get_package(Path(path_or_mod))

        case Path():
            result = get_public_api(path_or_mod)
            if isinstance(result, Package):
                return result
            raise InvalidPathError(f"{path_or_mod} points to a module, not a package — use get_module() instead")

        case _:
            pkg_file = inspect.getfile(path_or_mod)
            return get_package(Path(pkg_file).parent)
