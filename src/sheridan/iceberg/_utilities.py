"""Shared AST utility helpers for the iceberg package.

These helpers are used by both ``_visitor.py`` and ``_init_resolver.py``.
They operate on the stdlib ``ast`` module and carry no external dependencies
beyond the standard library.
"""

__all__ = ["bound_names", "collect_imports", "extract_all", "infer_all", "resolve_relative"]

import ast
from collections.abc import Iterator


def _collect_string_elements(node: ast.expr) -> frozenset[str] | None:
    """Extract string literals from a list or tuple AST node.

    Args:
        node: An AST expression, expected to be a ``List`` or ``Tuple``
            whose elements are all string constants.

    Returns:
        A frozen set of strings when all elements are string constants,
        otherwise ``None``.  Returns ``None`` when *node* is not a list or
        tuple, or when any element is not a plain string constant.

    Example::

        import ast
        node = ast.parse("['foo', 'bar']", mode="eval").body
        result = _collect_string_elements(node)
        # result == frozenset({"foo", "bar"})
    """
    match node:
        case ast.List(elts=elts) | ast.Tuple(elts=elts):
            names: list[str] = []
            for elt in elts:
                match elt:
                    case ast.Constant(value=str(s)):
                        names.append(s)
                    case _:
                        return None
            return frozenset(names)
        case _:
            return None


def extract_all(tree: ast.Module) -> frozenset[str] | None:
    """Return the literal string members of ``__all__``, or ``None``.

    Scans the module body for the first simple assignment to ``__all__``
    whose RHS is a list or tuple of string constants.  Both plain
    ``__all__ = [...]`` and annotated ``__all__: list[str] = [...]`` forms
    are recognised.

    Args:
        tree: Parsed module AST.

    Returns:
        A frozen set of string names when ``__all__`` is found and its value
        is a list or tuple of string literals, otherwise ``None``.
    """
    for node in tree.body:
        match node:
            case ast.Assign(targets=[ast.Name(id="__all__")], value=value):
                return _collect_string_elements(value)

            case ast.AnnAssign(
                target=ast.Name(id="__all__"),
                value=value,
            ) if value is not None:
                return _collect_string_elements(value)

            case _:
                pass

    return None


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

    Traverses the top-level statements of the given ``ast.Module`` and
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
        - Nested definitions (e.g., inside functions or classes) are ignored.
        - Attribute and subscript assignment targets are not included.
    """
    names: set[str] = set()
    for node in tree.body:
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


def _module_level_statements(body: list[ast.stmt]) -> Iterator[ast.stmt]:
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
                yield from _module_level_statements(if_body)
                yield from _module_level_statements(orelse)

            case (
                ast.Try(body=try_body, handlers=handlers, orelse=orelse, finalbody=finalbody)
                | ast.TryStar(body=try_body, handlers=handlers, orelse=orelse, finalbody=finalbody)
            ):
                yield from _module_level_statements(try_body)
                for handler in handlers:
                    yield from _module_level_statements(handler.body)
                yield from _module_level_statements(orelse)
                yield from _module_level_statements(finalbody)

            case _:
                pass


def collect_imports(tree: ast.Module, package: str) -> dict[str, tuple[str, str | None]]:
    """Map each name bound by a module-level import to where it came from.

    Relative imports are resolved against *package*. The first binding of a
    name wins, so in ``try: from .a import x`` / ``except: from .b import x``
    the ``try`` branch is reported.

    Args:
        tree: Parsed module AST.
        package: Dotted name of the package the module lives in, used as the
            anchor for relative imports. For an ``__init__.py`` this is the
            package itself; for a regular module it is the parent package.

    Returns:
        A mapping from local name to ``(module, attribute)``. ``attribute`` is
        the original imported name for ``from module import attribute`` and
        ``None`` for ``import module`` bindings. Star imports are ignored.
    """
    result: dict[str, tuple[str, str | None]] = {}

    for node in _module_level_statements(tree.body):
        match node:
            case ast.ImportFrom(module=module, names=aliases, level=level):
                source = resolve_relative(package, module, level) if level else (module or "")
                for alias in aliases:
                    if alias.name == "*":
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
