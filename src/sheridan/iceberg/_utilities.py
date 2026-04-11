"""Shared AST utility helpers for the iceberg package.

These helpers are used by both ``_visitor.py`` and ``_init_resolver.py``.
They operate on the stdlib ``ast`` module and carry no external dependencies
beyond the standard library.
"""

__all__ = ["extract_all"]

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
