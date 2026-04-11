"""Shared AST utility helpers for the iceberg package.

These helpers are used by both ``_visitor.py`` and ``_init_resolver.py``.
They operate on the stdlib ``ast`` module and carry no external dependencies
beyond the standard library.
"""

__all__ = ["extract_all", "infer_public_api"]

import ast


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


def infer_public_api(tree: ast.Module) -> frozenset[str]:
    """Collect public top-level names defined in a module AST.

    Traverses the top-level statements of the given ``ast.Module`` and
    extracts names that would be considered "public" by convention
    (i.e., names not starting with an underscore). The following node
    types are inspected:

    - Function and async function definitions
    - Class definitions
    - Variable assignments (``Assign`` and ``AnnAssign``)
    - Type aliases (``TypeAlias``)

    Only simple name targets (``ast.Name``) are considered for assignments.

    Args:
        tree: The ``ast.Module`` node representing the parsed Python module.

    Returns:
        A frozenset of public names (strings) defined at the top level
        of the module.

    Notes:
        - This function does not evaluate ``__all__`` and instead infers
          public names purely by naming convention.
        - Nested definitions (e.g., inside functions or classes) are ignored.
        - Complex assignment targets (e.g., attributes, subscripts, tuple
          unpacking) are not included.
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
                    match target:
                        case ast.Name(id=name) if not name.startswith("_"):
                            names.add(name)
                        case _:
                            pass

            case ast.AnnAssign(target=ast.Name(id=name)):
                if not name.startswith("_"):
                    names.add(name)

            case ast.TypeAlias(name=ast.Name(id=name)):
                if not name.startswith("_"):
                    names.add(name)

            case _:
                pass

    return frozenset(names)
