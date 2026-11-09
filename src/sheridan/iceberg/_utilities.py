"""Provide the AST helper functions that the iceberg modules share.

``_visitor.py`` and ``_init_resolver.py`` use these helper functions. They use
the ``ast`` module of the standard library. They have no external dependencies.
"""

__all__ = [
    "StarExports",
    "bound_names",
    "collect_imports",
    "extract_all",
    "infer_all",
    "parse_source",
    "read_source",
    "resolve_relative",
    "star_candidate",
]

import ast
import importlib.util
import warnings
from collections.abc import Callable, Collection, Iterator
from pathlib import Path

from sheridan.iceberg._exceptions import ParseError, SourceReadError

#: Find the evaluated ``__all__`` of a different module by dotted name. The
#: result is ``None`` if the module is not in the analyzed tree, or if its
#: ``__all__`` is not known.
type AllLookup = Callable[[str], frozenset[str] | None]

#: Find the names that ``from module import *`` binds, by dotted module name.
#: The result is ``None`` if the module is not in the analyzed tree.
type StarExports = Callable[[str], Collection[str] | None]


def read_source(path: Path) -> str:
    """Read and decode a Python source file.

    The function decodes the bytes in the same way as the interpreter. The
    encoding is UTF-8, unless a PEP 263 encoding declaration or a BOM gives a
    different encoding.

    Args:
        path: The source file to read.

    Returns:
        The decoded source text, with universal newlines.

    Raises:
        SourceReadError: If the function cannot read the file, or cannot decode
            its bytes with its encoding.
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise SourceReadError(f"cannot read file: {exc.strerror or exc}", path=str(path)) from exc

    try:
        return importlib.util.decode_source(data)
    except (SyntaxError, UnicodeDecodeError, LookupError) as exc:
        reason = exc.msg if isinstance(exc, SyntaxError) else str(exc)
        raise SourceReadError(f"cannot decode file: {reason}", path=str(path)) from exc


def parse_source(source: str, path: Path | str | None = None) -> ast.Module:
    """Parse Python source into a module AST.

    The function uses the grammar of the current interpreter. Thus, it accepts
    all the syntax that the interpreter accepts.

    Args:
        source: The raw Python source text.
        path: The file that contains *source*. The error shows this path.

    Returns:
        The parsed module.

    Raises:
        ParseError: If *source* is not valid Python.
    """
    try:
        return ast.parse(source, filename="<unknown>" if path is None else str(path))
    except SyntaxError as exc:
        raise ParseError.from_syntax_error(exc) from exc


class _NotStaticError(Exception):
    """Signal that a statement changes ``__all__`` in a way that iceberg cannot evaluate."""

    def __init__(self, node: ast.AST, reason: str) -> None:
        super().__init__(reason)
        self.lineno: int | None = getattr(node, "lineno", None)
        self.reason = reason


def _is_int_literal(node: ast.expr) -> bool:
    """Check if *node* is an integer literal such as ``0`` or ``-1``."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
        node = node.operand

    return isinstance(node, ast.Constant) and type(node.value) is int


def extract_all(
    tree: ast.Module,
    package: str = "",
    lookup: AllLookup | None = None,
    *,
    path: str | None = None,
) -> frozenset[str] | None:
    """Evaluate ``__all__`` statically from the module-level statements.

    The function applies, in source order, each module-level statement that
    changes ``__all__``. This includes the statements in ``if`` and ``try``
    blocks:

    - ``__all__ = ...``, ``__all__ = x = ...`` and ``__all__: list[str] = ...``
    - ``__all__ += ...``
    - ``__all__.extend(...)`` and ``__all__.append("name")``
    - ``__all__.insert(i, "name")`` and ``__all__.remove("name")``
    - ``__all__.sort(...)`` and ``__all__.reverse()``, which keep the names
    - ``from .sub import __all__``, which takes the ``__all__`` of ``sub``

    A value can be one of these:

    - A list or tuple of string literals.
    - A concatenation of values with ``+``.
    - The current ``__all__``.
    - The ``__all__`` of a different module in the analyzed tree. Examples are
      ``sub.__all__`` after ``from . import sub``, or a name that
      ``from .sub import __all__ as sub_all`` binds. The function uses
      *lookup* to find other modules.

    The function evaluates the branches of an ``if`` or ``try`` block
    separately and joins their results. Thus, ``__all__`` keeps each name that
    a branch adds. A ``try`` handler starts from the ``__all__`` before the
    block.

    The function cannot evaluate other statements that bind ``__all__``, such
    as ``import x as __all__`` or ``for __all__ in ...``.

    If the function cannot evaluate a statement, it gives a ``UserWarning``
    with the file and the line. Then it gives ``None``, and the caller uses the
    underscore rule.

    Args:
        tree: The parsed module AST.
        package: The dotted name of the package that holds the module. The
            function uses it to resolve relative imports of other modules.
        lookup: A function that gives the ``__all__`` of a different module by
            dotted name, or ``None`` if it is not known.
        path: The file that the function parsed into *tree*. The warning
            shows this path.

    Returns:
        The names in ``__all__``. ``None`` if there is no ``__all__``, or if
        the function cannot evaluate it statically.
    """
    imports: dict[str, tuple[str, str | None]] | None = None

    def imported(name: str) -> tuple[str, str | None] | None:
        nonlocal imports
        if imports is None:
            imports = collect_imports(tree, package)

        return imports.get(name)

    def is_imported_all(name: str) -> bool:
        source = imported(name)
        return source is not None and source[1] == "__all__"

    def other_all(node: ast.expr, name: str) -> list[str]:
        source = imported(name)
        if source is None:
            raise _NotStaticError(node, f"{name!r} is not an imported module")

        module, attribute = source
        # ``import pkg.sub as sub`` and ``from .sub import __all__`` name the
        # module. ``from . import sub`` names a submodule of ``pkg``.
        target = module if attribute in {None, "__all__"} else f"{module}.{attribute}"
        return module_all(node, target)

    def module_all(node: ast.AST, module: str) -> list[str]:
        found = lookup(module) if lookup is not None else None
        if found is None:
            raise _NotStaticError(node, f"the __all__ of {module!r} is not known")

        return sorted(found)

    def evaluate(node: ast.expr, current: list[str] | None) -> list[str]:
        match node:
            case ast.List(elts=elts) | ast.Tuple(elts=elts):
                names: list[str] = []
                for elt in elts:
                    match elt:
                        case ast.Constant(value=str(s)):
                            names.append(s)
                        case _:
                            raise _NotStaticError(elt, "an element is not a string literal")

                return names

            case ast.BinOp(left=left, op=ast.Add(), right=right):
                return evaluate(left, current) + evaluate(right, current)

            case ast.Name(id="__all__"):
                if current is None:
                    raise _NotStaticError(node, "the code uses __all__ before it assigns it")

                return list(current)

            case ast.Attribute(value=ast.Name(id=name), attr="__all__"):
                return other_all(node, name)

            case ast.Name(id=name) if is_imported_all(name):
                return other_all(node, name)

            case _:
                raise _NotStaticError(node, "the value is not a literal list or tuple")

    def change(node: ast.stmt, current: list[str] | None) -> list[str] | None:
        match node:
            case ast.Assign(targets=targets, value=value) if any(
                "__all__" in bound_names(target) for target in targets
            ):
                if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in targets):
                    raise _NotStaticError(node, "an unpacking assignment binds __all__")

                return evaluate(value, current)

            case ast.AnnAssign(target=ast.Name(id="__all__"), value=value) if value is not None:
                return evaluate(value, current)

            case ast.AugAssign(target=ast.Name(id="__all__"), op=op, value=value):
                if current is None:
                    raise _NotStaticError(node, "the code changes __all__ before it assigns it")

                if not isinstance(op, ast.Add):
                    raise _NotStaticError(node, "iceberg supports only +=")

                return current + evaluate(value, current)

            case ast.Expr(value=ast.Call(func=ast.Attribute(value=ast.Name(id="__all__"), attr=method)) as call):
                if current is None:
                    raise _NotStaticError(node, "the code changes __all__ before it assigns it")

                match method, call.args, call.keywords:
                    case "extend", [arg], []:
                        return current + evaluate(arg, current)

                    case "append", [ast.Constant(value=str(s))], []:
                        return [*current, s]

                    case "insert", [index, ast.Constant(value=str(s))], [] if _is_int_literal(index):
                        # Only the membership is important. Thus, ignore the position.
                        return [*current, s]

                    case "remove", [ast.Constant(value=str(s))], []:
                        if s not in current:
                            raise _NotStaticError(node, f"__all__.remove({s!r}) removes a name that is not in __all__")

                        current = list(current)
                        current.remove(s)
                        return current

                    case "sort", [], keywords if all(kw.arg in {"key", "reverse"} for kw in keywords):
                        return current  # a new order keeps the membership

                    case "reverse", [], []:
                        return current

                    case _:
                        raise _NotStaticError(node, f"iceberg does not support __all__.{method}(...)")

            case ast.ImportFrom(names=aliases) if any(
                alias.name == "__all__" and alias.asname in {None, "__all__"} for alias in aliases
            ):
                return module_all(node, _import_from_source(node, package))

            case _ if _binds_all(node):
                raise _NotStaticError(node, "a statement that iceberg does not evaluate binds __all__")

            case _:
                return current

    def union(*branches: list[str] | None) -> list[str] | None:
        # Without a run of the code, the branch that runs is not known. Thus, keep
        # each name that a branch exports, as for the definitions in all branches.
        assigned = [branch for branch in branches if branch is not None]
        if not assigned:
            return None

        names: dict[str, None] = {}
        for branch in assigned:
            names.update(dict.fromkeys(branch))

        return list(names)

    def run(body: list[ast.stmt], current: list[str] | None) -> list[str] | None:
        for node in body:
            match node:
                case ast.If(body=if_body, orelse=orelse):
                    current = union(run(if_body, current), run(orelse, current))

                case (
                    ast.Try(body=try_body, handlers=handlers, orelse=orelse, finalbody=finalbody)
                    | ast.TryStar(body=try_body, handlers=handlers, orelse=orelse, finalbody=finalbody)
                ):
                    # A handler can start at any line of the try body. The usual
                    # case is an ImportError on the first line. Thus, start the
                    # handler from the state before the try.
                    completed = run(orelse, run(try_body, current))
                    handled = [run(handler.body, current) for handler in handlers]
                    current = run(finalbody, union(completed, *handled))

                case _:
                    current = change(node, current)

        return current

    try:
        result = run(tree.body, None)
    except _NotStaticError as exc:
        parts = [str(part) for part in (path, exc.lineno) if part is not None]
        prefix = f"{':'.join(parts)}: " if parts else ""
        warnings.warn(
            f"{prefix}cannot evaluate __all__ statically ({exc.reason}). "
            "iceberg uses the names without a leading underscore.",
            UserWarning,
            stacklevel=2,
        )
        return None

    return None if result is None else frozenset(result)


def _binds_all(node: ast.AST) -> bool:
    """Check if *node* binds or deletes the module-level name ``__all__``.

    The function skips function, class and lambda bodies, because the names
    that they bind are local.
    """
    match node:
        case ast.FunctionDef(name=name) | ast.AsyncFunctionDef(name=name) | ast.ClassDef(name=name):
            return name == "__all__"

        case ast.Lambda():
            return False

        case ast.AnnAssign(value=None):
            return False  # a bare annotation does not bind a name

        case ast.Import(names=aliases) | ast.ImportFrom(names=aliases):
            # ``import a.b`` binds ``a``.
            return any((alias.asname or alias.name.split(".")[0]) == "__all__" for alias in aliases)

        case ast.Name(id="__all__", ctx=ctx):
            return not isinstance(ctx, ast.Load)

        case _:
            return any(_binds_all(child) for child in ast.iter_child_nodes(node))


def bound_names(target: ast.expr) -> Iterator[str]:
    """Yield each plain name that an assignment target binds, in source order.

    The function goes into tuple unpacking, list unpacking and starred targets
    recursively. It skips attribute targets and subscript targets, because they
    do not bind a module-level name.

    Args:
        target: One target of an ``Assign`` or ``AnnAssign`` node.

    Yields:
        Each name that *target* binds, from left to right.
    """
    match target:
        case ast.Name(id=name):
            yield name
        case ast.Tuple(elts=elts) | ast.List(elts=elts):
            for elt in elts:
                yield from bound_names(elt)
        case ast.Starred(value=value):
            yield from bound_names(value)
        case _:
            pass


def infer_all(tree: ast.Module) -> frozenset[str]:
    """Collect the public top-level names that a module AST defines.

    The function goes through the module-level statements of the given
    ``ast.Module`` (also the statements in ``if`` and ``try`` blocks). It
    collects the names that are public by convention: the names that do not
    start with an underscore. It examines these node types:

    - Function and async function definitions
    - Class definitions
    - Variable assignments (``Assign`` and ``AnnAssign``)
    - Type aliases (``TypeAlias``)

    An assignment gives each name that it binds. This includes each target of
    a chained assignment (``a = b = 1``) and each name in tuple, list or
    starred unpacking (``c, *rest = ...``).

    Args:
        tree: The ``ast.Module`` node of the parsed Python module.

    Returns:
        A frozenset of the public names (strings) that the module defines at
        the top level.

    Notes:
        - This function does not evaluate ``__all__``. It uses only the naming
          convention to find public names.
        - The function includes definitions in module-level ``if`` and ``try``
          blocks (all branches), for example ``if TYPE_CHECKING:`` blocks and
          ``try: ... except ImportError:`` fallbacks.
        - The function ignores nested definitions (for example in functions
          or classes).
        - The function does not include attribute targets and subscript targets.
    """
    names: set[str] = set()

    for node in module_level_statements(tree.body):
        match node:
            case ast.FunctionDef(name=name) | ast.AsyncFunctionDef(name=name):
                if not name.startswith("_"):
                    names.add(name)

            case ast.ClassDef(name=name):
                if not name.startswith("_"):
                    names.add(name)

            case ast.Assign(targets=targets):
                for target in targets:
                    for name in bound_names(target):
                        if not name.startswith("_"):
                            names.add(name)

            case ast.AnnAssign(target=ast.Name(id=name)):
                if not name.startswith("_"):
                    names.add(name)

            case ast.TypeAlias(name=ast.Name(id=name)):
                if not name.startswith("_"):
                    names.add(name)

            case _:
                pass

    return frozenset(names)


def resolve_relative(package: str, module: str | None, level: int) -> str:
    """Compute the fully qualified module name of a relative import.

    Args:
        package: The dotted name of the package that holds the module with
            the import (the anchor for one leading dot).
        module: The module part after the dots, or ``None`` for ``from . import``.
        level: The number of leading dots (always >= 1 for relative imports).

    Returns:
        The fully qualified dotted module name.
    """
    # level=1 is "this package". level>1 is the same number of levels up.
    parts = package.split(".")
    anchor = ".".join(parts[: len(parts) - (level - 1)])

    if not module:
        return anchor

    return f"{anchor}.{module}" if anchor else module


def module_level_statements(body: list[ast.stmt]) -> Iterator[ast.stmt]:
    """Yield the statements that run when Python imports the module.

    The function goes into ``if`` and ``try`` blocks (all branches), because
    the names that they bind are also module globals. An example is the usual
    fallback ``try: from ._version import version``. The function skips
    function and class bodies.

    Args:
        body: A list of statements, usually ``ast.Module.body``.

    Yields:
        Each module-level statement, depth first, in source order.
    """
    for node in body:
        yield node

        match node:
            case ast.If(body=if_body, orelse=orelse):
                yield from module_level_statements(if_body)
                yield from module_level_statements(orelse)

            case (
                ast.Try(body=try_body, handlers=handlers, orelse=orelse, finalbody=finalbody)
                | ast.TryStar(body=try_body, handlers=handlers, orelse=orelse, finalbody=finalbody)
            ):
                yield from module_level_statements(try_body)

                for handler in handlers:
                    yield from module_level_statements(handler.body)

                yield from module_level_statements(orelse)
                yield from module_level_statements(finalbody)

            case _:
                pass


def collect_imports(
    tree: ast.Module,
    package: str,
    star_exports: StarExports | None = None,
) -> dict[str, tuple[str, str | None]]:
    """Map each name that a module-level import binds to its source.

    The function resolves relative imports from *package*. The first binding
    of a name has priority. Thus, in ``try: from .a import x`` /
    ``except: from .b import x``, the function reports the ``try`` branch.

    Args:
        tree: The parsed module AST.
        package: The dotted name of the package that holds the module. It is
            the anchor for relative imports. For an ``__init__.py``, this is
            the package. For a regular module, it is the parent package.
        star_exports: A function that gives the names that
            ``from module import *`` binds, or ``None`` if the module is not
            known. If you do not give it, or if it gives ``None``, star
            imports do not bind names.

    Returns:
        A mapping from local name to ``(module, attribute)``. For
        ``from module import attribute`` (and for each name that a star import
        binds), ``attribute`` is the original imported name. For
        ``import module`` bindings, it is ``None``.
    """
    result: dict[str, tuple[str, str | None]] = {}

    for node in module_level_statements(tree.body):
        match node:
            case ast.ImportFrom() as import_from:
                source = _import_from_source(import_from, package)

                for alias in import_from.names:
                    if alias.name == "*":
                        exported = star_exports(source) if star_exports else None
                        for name in sorted(exported or ()):
                            result.setdefault(name, (source, name))

                        continue

                    result.setdefault(alias.asname or alias.name, (source, alias.name))

            case ast.Import(names=aliases):
                for alias in aliases:
                    if alias.asname:
                        result.setdefault(alias.asname, (alias.name, None))
                    else:
                        # ``import a.b`` binds ``a``.
                        top = alias.name.split(".")[0]
                        result.setdefault(top, (top, None))

            case _:
                pass

    return result


def star_candidate(tree: ast.Module, package: str, star_exports: StarExports) -> str | None:
    """Find the star-imported module that can supply a name that iceberg cannot find.

    A star import from a module outside the analyzed tree can bind all names.
    If there are many such imports, the function gives the last one, because
    a later import binds the names of an earlier import again.

    Args:
        tree: The parsed module AST.
        package: The dotted name of the package that holds the module. It is
            the anchor for relative imports (see ``collect_imports``).
        star_exports: A function that gives the names that
            ``from module import *`` binds, or ``None`` if the module is not
            in the analyzed tree.

    Returns:
        The absolute dotted name of the module in the last module-level
        ``from module import *`` that is not in the analyzed tree, or ``None``.
    """
    candidate: str | None = None

    for node in module_level_statements(tree.body):
        if not isinstance(node, ast.ImportFrom):
            continue

        if not any(alias.name == "*" for alias in node.names):
            continue

        source = _import_from_source(node, package)
        if star_exports(source) is None:
            candidate = source

    return candidate


def _import_from_source(node: ast.ImportFrom, package: str) -> str:
    """Resolve the absolute name of the module that a ``from ... import`` statement reads.

    Args:
        node: The ``ImportFrom`` statement.
        package: The dotted name of the package that holds the module with the import.

    Returns:
        The absolute dotted module name. The function resolves relative
        imports from *package*.
    """
    if node.level:
        return resolve_relative(package, node.module, node.level)

    return node.module or ""
