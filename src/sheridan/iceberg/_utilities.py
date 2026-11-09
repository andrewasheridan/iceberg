"""Shared AST utility helpers for the iceberg package.

These helpers are used by both ``_visitor.py`` and ``_init_resolver.py``.
They operate on the stdlib ``ast`` module and carry no external dependencies
beyond the standard library.
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

#: Look up the evaluated ``__all__`` of another module by dotted name. Returns
#: ``None`` when the module is not in the analyzed tree or its ``__all__`` is
#: unknown.
type AllLookup = Callable[[str], frozenset[str] | None]

#: Look up the names that ``from module import *`` binds, by dotted module
#: name. Returns ``None`` when the module is not in the analyzed tree.
type StarExports = Callable[[str], Collection[str] | None]


def read_source(path: Path) -> str:
    """Read and decode a Python source file.

    The bytes are decoded the way the interpreter decodes them: UTF-8 unless
    a PEP 263 encoding declaration or a BOM says otherwise.

    Args:
        path: The source file to read.

    Returns:
        The decoded source text, with universal newlines.

    Raises:
        SourceReadError: If the file cannot be read, or its bytes cannot be
            decoded with its encoding.
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

    The grammar is the running interpreter's, so any syntax it accepts is
    accepted here.

    Args:
        source: Raw Python source text.
        path: The file *source* was read from, reported in the error.

    Returns:
        The parsed module.

    Raises:
        ParseError: When *source* is not valid Python.
    """
    try:
        return ast.parse(source, filename="<unknown>" if path is None else str(path))
    except SyntaxError as exc:
        raise ParseError.from_syntax_error(exc) from exc


class _NotStaticError(Exception):
    """Signal that a statement changes ``__all__`` in a way iceberg cannot evaluate."""

    def __init__(self, node: ast.AST, reason: str) -> None:
        super().__init__(reason)
        self.lineno: int | None = getattr(node, "lineno", None)
        self.reason = reason


def _is_int_literal(node: ast.expr) -> bool:
    """Check whether *node* is an integer literal such as ``0`` or ``-1``."""
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

    Applies, in source order, every top-level statement that changes
    ``__all__``:

    - ``__all__ = ...`` and ``__all__: list[str] = ...``
    - ``__all__ += ...``
    - ``__all__.extend(...)`` and ``__all__.append("name")``
    - ``__all__.insert(i, "name")`` and ``__all__.remove("name")``
    - ``__all__.sort(...)`` and ``__all__.reverse()``, which keep the names

    A value may be a list or tuple of string literals, a concatenation of
    values with ``+``, the current ``__all__``, or the ``__all__`` of another
    module in the analyzed tree (``sub.__all__`` after ``from . import sub``,
    or a name bound by ``from .sub import __all__ as sub_all``). Other modules
    are looked up with *lookup*.

    When a statement cannot be evaluated, a ``UserWarning`` names the file and
    line, and the function returns ``None`` so the caller falls back to
    underscore inference.

    Args:
        tree: Parsed module AST.
        package: Dotted name of the package the module lives in, used to
            resolve relative imports of other modules.
        lookup: Returns the ``__all__`` of another module by dotted name, or
            ``None`` when it is unknown.
        path: The file *tree* was parsed from, used in the warning.

    Returns:
        The names in ``__all__``, or ``None`` when ``__all__`` is absent or
        cannot be evaluated statically.
    """
    current: list[str] | None = None
    imports: dict[str, tuple[str, str | None]] | None = None

    def imported(name: str) -> tuple[str, str | None] | None:
        nonlocal imports
        if imports is None:
            imports = collect_imports(tree, package)
        return imports.get(name)

    def other_all(node: ast.expr, name: str) -> list[str]:
        source = imported(name)
        if source is None:
            raise _NotStaticError(node, f"{name!r} is not an imported module")
        module, attribute = source
        # ``import pkg.sub as sub`` and ``from .sub import __all__`` name the
        # module itself; ``from . import sub`` names a submodule of ``pkg``.
        target = module if attribute in {None, "__all__"} else f"{module}.{attribute}"
        found = lookup(target) if lookup is not None else None
        if found is None:
            raise _NotStaticError(node, f"the __all__ of {target!r} is not known")
        return sorted(found)

    def evaluate(node: ast.expr) -> list[str]:
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
                return evaluate(left) + evaluate(right)
            case ast.Name(id="__all__"):
                if current is None:
                    raise _NotStaticError(node, "__all__ is used before it is assigned")
                return list(current)
            case ast.Attribute(value=ast.Name(id=name), attr="__all__"):
                return other_all(node, name)
            case ast.Name(id=name) if (imported(name) or ("", None))[1] == "__all__":
                return other_all(node, name)
            case _:
                raise _NotStaticError(node, "the value is not a literal list or tuple")

    try:
        for node in tree.body:
            match node:
                case ast.Assign(targets=[ast.Name(id="__all__")], value=value):
                    current = evaluate(value)

                case ast.AnnAssign(target=ast.Name(id="__all__"), value=value) if value is not None:
                    current = evaluate(value)

                case ast.AugAssign(target=ast.Name(id="__all__"), op=op, value=value):
                    if current is None:
                        raise _NotStaticError(node, "__all__ is changed before it is assigned")
                    if not isinstance(op, ast.Add):
                        raise _NotStaticError(node, "only += is supported")
                    current = current + evaluate(value)

                case ast.Expr(value=ast.Call(func=ast.Attribute(value=ast.Name(id="__all__"), attr=method)) as call):
                    if current is None:
                        raise _NotStaticError(node, "__all__ is changed before it is assigned")
                    match method, call.args, call.keywords:
                        case "extend", [arg], []:
                            current = current + evaluate(arg)
                        case "append", [ast.Constant(value=str(s))], []:
                            current = [*current, s]
                        case "insert", [index, ast.Constant(value=str(s))], [] if _is_int_literal(index):
                            # Only membership matters, so the position is ignored.
                            current = [*current, s]
                        case "remove", [ast.Constant(value=str(s))], []:
                            if s not in current:
                                raise _NotStaticError(node, f"__all__.remove({s!r}) removes a missing name")
                            current = list(current)
                            current.remove(s)
                        case "sort", [], keywords if all(kw.arg in {"key", "reverse"} for kw in keywords):
                            pass  # reordering keeps the membership
                        case "reverse", [], []:
                            pass
                        case _:
                            raise _NotStaticError(node, f"__all__.{method}(...) is not supported")

                case _:
                    pass
    except _NotStaticError as exc:
        location = ":".join(str(part) for part in (path, exc.lineno) if part is not None)
        prefix = f"{location}: " if location else ""
        warnings.warn(
            f"{prefix}cannot evaluate __all__ statically ({exc.reason}); "
            "falling back to names without a leading underscore",
            UserWarning,
            stacklevel=2,
        )
        return None

    return None if current is None else frozenset(current)


def bound_names(target: ast.expr) -> Iterator[str]:
    """Yield every plain name bound by an assignment target, in source order.

    Recurses into tuple and list unpacking and starred targets. Attribute and
    subscript targets bind no module-level name and are skipped.

    Args:
        target: One target of an ``Assign`` or ``AnnAssign`` node.

    Yields:
        Each name bound by *target*, left to right.
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
    """Collect public top-level names defined in a module AST.

    Traverses the module-level statements of the given ``ast.Module``
    (including those inside ``if`` and ``try`` blocks) and
    extracts names that would be considered "public" by convention
    (i.e., names not starting with an underscore). The following node
    types are inspected:

    - Function and async function definitions
    - Class definitions
    - Variable assignments (``Assign`` and ``AnnAssign``)
    - Type aliases (``TypeAlias``)

    Assignments contribute every name they bind, including each target of
    a chained assignment (``a = b = 1``) and each name in tuple, list, or
    starred unpacking (``c, *rest = ...``).

    Args:
        tree: The ``ast.Module`` node representing the parsed Python module.

    Returns:
        A frozenset of public names (strings) defined at the top level
        of the module.

    Notes:
        - This function does not evaluate ``__all__`` and instead infers
          public names purely by naming convention.
        - Definitions inside module-level ``if`` / ``try`` blocks (all
          branches) are included, e.g. ``if TYPE_CHECKING:`` blocks and
          ``try: ... except ImportError:`` fallbacks.
        - Nested definitions (e.g., inside functions or classes) are ignored.
        - Attribute and subscript assignment targets are not included.
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
                    names.update(name for name in bound_names(target) if not name.startswith("_"))

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
    """Compute the fully-qualified module name for a relative import.

    Args:
        package: Dotted name of the package the importing module lives in
            (the anchor for a single leading dot).
        module: The module part after the dots, or ``None`` for ``from . import``.
        level: The number of leading dots (always >= 1 for relative imports).

    Returns:
        The fully-qualified dotted module name.
    """
    # level=1 means "this package"; level>1 means walk up that many levels.
    parts = package.split(".")
    anchor = ".".join(parts[: len(parts) - (level - 1)])

    if not module:
        return anchor

    return f"{anchor}.{module}" if anchor else module


def module_level_statements(body: list[ast.stmt]) -> Iterator[ast.stmt]:
    """Yield statements that execute at module import time.

    Descends into ``if`` / ``try`` blocks (all branches) because names bound
    there are still module globals, e.g. the common ``try: from ._version
    import version`` fallback pattern. Function and class bodies are skipped.

    Args:
        body: A list of statements, typically ``ast.Module.body``.

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
    """Map each name bound by a module-level import to where it came from.

    Relative imports are resolved against *package*. The first binding of a
    name wins, so in ``try: from .a import x`` / ``except: from .b import x``
    the ``try`` branch is reported.

    Args:
        tree: Parsed module AST.
        package: Dotted name of the package the module lives in, used as the
            anchor for relative imports. For an ``__init__.py`` this is the
            package itself; for a regular module it is the parent package.
        star_exports: Returns the names that ``from module import *`` binds,
            or ``None`` when the module is unknown. Without it, or when it
            returns ``None``, star imports bind nothing.

    Returns:
        A mapping from local name to ``(module, attribute)``. ``attribute`` is
        the original imported name for ``from module import attribute`` (and
        for each name a star import binds) and ``None`` for ``import module``
        bindings.
    """
    result: dict[str, tuple[str, str | None]] = {}

    for node in module_level_statements(tree.body):
        match node:
            case ast.ImportFrom(module=module, names=aliases, level=level):
                source = resolve_relative(package, module, level) if level else (module or "")
                for alias in aliases:
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
    """Name the star-imported module that may provide a name iceberg cannot find.

    A star import from a module outside the analyzed tree may bind any name.
    When several do, the last one is returned, because a later import
    rebinds the names of an earlier one.

    Args:
        tree: Parsed module AST.
        package: Dotted name of the package the module lives in, used as the
            anchor for relative imports (see ``collect_imports``).
        star_exports: Returns the names that ``from module import *`` binds,
            or ``None`` when the module is not in the analyzed tree.

    Returns:
        The absolute dotted name of the last module-level ``from module
        import *`` whose module is not in the analyzed tree, or ``None``.
    """
    candidate: str | None = None
    for node in module_level_statements(tree.body):
        if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
            source = resolve_relative(package, node.module, node.level) if node.level else (node.module or "")
            if star_exports(source) is None:
                candidate = source
    return candidate
