"""Visit the AST of a Python source file and make a ``Module`` snapshot from it.

These rules find the public names:

- If the source defines ``__all__``, only the literal string values in it are
  public.
- If not, each top-level name that does **not** start with ``_`` is public.

Top level means module level. Definitions in module-level ``if`` and ``try``
blocks (in all branches) are included. Thus, the visitor collects
``if TYPE_CHECKING:`` blocks, ``sys.version_info`` checks and
``except ImportError:`` fallbacks. If the module defines a name more than one
time, the visitor keeps the first definition in source order.

Class bodies obey the same rule. The visitor collects methods, nested classes
and class variables in the ``if`` and ``try`` blocks of a class body (in all
branches). It keeps the first definition of a member name.

``__all__`` can list names that the module does not define (for example
re-exports of imported names). The visitor collects these names as
``Reference`` items. Thus, it never removes them silently.

The builders in ``_builders`` make a model from each definition.
"""

__all__ = ["visit_module"]

import ast
from collections.abc import Mapping
from pathlib import Path

from sheridan.iceberg._builders import (
    build_assignment,
    build_assignments,
    build_class,
    build_function,
    build_type_alias,
    group_overloads,
)
from sheridan.iceberg._models import Assignment, Class, Function, Module, Reference
from sheridan.iceberg._utilities import (
    collect_imports,
    extract_all,
    infer_all,
    module_level_statements,
    parse_source,
    star_candidate,
)


def visit_module(
    source: str,
    dotted_name: str,
    path: Path | None = None,
    known_all: Mapping[str, frozenset[str] | None] | None = None,
    *,
    tree: ast.Module | None = None,
) -> Module:
    """Parse *source* and collect its public API in a ``Module``.

    Args:
        source: The raw Python source text.
        dotted_name: The fully qualified module name (for example ``"my_pkg.core"``).
        path: The file that contains *source*. If *source* has a syntax error,
            the ``ParseError`` shows this path.
        known_all: The evaluated ``__all__`` of each module in the analyzed
            tree, by dotted name. If it has *dotted_name*, the function uses
            that value. If not, the function evaluates ``__all__`` from
            *source*, and this mapping resolves ``__all__ += other.__all__``.
        tree: The parsed *source*. With it, the caller parses each file only
            one time. If you give it, the function does not parse *source*
            again.

    Returns:
        A ``Module`` that contains only the public names in *source*.

    Raises:
        ParseError: If *source* is not valid Python.
    """
    if tree is None:
        tree = parse_source(source, path)

    if known_all is not None and dotted_name in known_all:
        explicit_all = known_all[dotted_name]
    else:
        explicit_all = extract_all(
            tree,
            dotted_name.rpartition(".")[0],
            None if known_all is None else known_all.get,
            path=None if path is None else str(path),
        )

    public = _top_level_public_names(tree, explicit_all)

    assignments: list[Assignment] = []
    classes: list[Class] = []
    functions: list[Function] = []
    # The first definition of a name has priority, as in ``collect_imports``. In
    # ``if``/``else`` or ``try``/``except`` branches, the visitor reports the first branch.
    seen: set[str] = set()
    statements = list(module_level_statements(tree.body))
    overloads, grouped = group_overloads(statements)

    def keep(name: str) -> bool:
        if name not in public or name in seen:
            return False

        seen.add(name)
        return True

    for node in statements:
        match node:
            case (ast.FunctionDef() | ast.AsyncFunctionDef()) as fn_node:
                if fn_node not in grouped and keep(fn_node.name):
                    functions.append(build_function(fn_node, overloads=overloads.get(fn_node, ())))

            case ast.ClassDef() as cls_node:
                if keep(cls_node.name):
                    classes.append(build_class(cls_node))

            case ast.Assign() as assign_node:
                for assignment in build_assignments(assign_node):
                    if keep(assignment.name):
                        assignments.append(assignment)

            case ast.AnnAssign() as ann_node:
                result = build_assignment(ann_node)
                if result is not None and keep(result.name):
                    assignments.append(result)

            case ast.TypeAlias() as alias_node:
                alias = build_type_alias(alias_node)
                if keep(alias.name):
                    assignments.append(alias)

            case _:
                pass

    references: tuple[Reference, ...] = ()
    if explicit_all is not None:
        references = _build_references(
            tree,
            explicit_all - seen,
            dotted_name.rpartition(".")[0],
            {} if known_all is None else known_all,
        )

    return Module(
        name=dotted_name,
        assignments=tuple(assignments),
        classes=tuple(classes),
        functions=tuple(functions),
        references=references,
    )


def _top_level_public_names(
    tree: ast.Module,
    explicit_all: frozenset[str] | None,
) -> frozenset[str]:
    """Compute the set of public names of a module.

    Args:
        tree: The parsed module AST.
        explicit_all: The literal names from ``__all__``, or ``None`` if there
            is no ``__all__``.

    Returns:
        The names to show. If there is an explicit list, that list. If not,
        each top-level name that does not start with ``_``.
    """
    if explicit_all is not None:
        return explicit_all

    return infer_all(tree)


def _build_references(
    tree: ast.Module,
    names: frozenset[str],
    package: str,
    known_all: Mapping[str, frozenset[str] | None],
) -> tuple[Reference, ...]:
    """Build ``Reference`` items for the exported names that the module does not define.

    A star import from a module with a known ``__all__`` binds the names in that
    ``__all__``. The function records other star-imported modules (outside the
    analyzed tree, or without ``__all__``) as the possible source of a name
    that no import binds. If the module is in the tree,
    ``resolve_module_references`` resolves the name later.

    Args:
        tree: The parsed module AST.
        names: The exported names that the visitor did not collect as a definition.
        package: The dotted name of the package that holds the module. The
            function uses it to make relative imports absolute.
        known_all: The evaluated ``__all__`` of each module in the analyzed
            tree, by dotted name.

    Returns:
        One ``Reference`` for each name, sorted by name.
    """
    imports = collect_imports(tree, package, known_all.get)
    candidate = star_candidate(tree, package, known_all.get)

    references: list[Reference] = []
    for name in sorted(names):
        if name in imports:
            module, attribute = imports[name]
        elif candidate is not None:
            module, attribute = candidate, name
        else:
            module, attribute = None, None

        references.append(Reference(name=name, module=module, attribute=attribute))

    return tuple(references)
