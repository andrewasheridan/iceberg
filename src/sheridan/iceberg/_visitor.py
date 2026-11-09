"""AST visitor that converts a Python source file into a ``Module`` snapshot.

Public names are determined as follows:

- If the source defines ``__all__``, only the literal string values listed
  there are considered public.
- Otherwise every top-level name that does **not** start with ``_`` is public.

Top-level means module level: definitions inside module-level ``if`` and
``try`` blocks (every branch) count, so ``if TYPE_CHECKING:`` blocks,
``sys.version_info`` checks and ``except ImportError:`` fallbacks are
captured. When a name is defined more than once, the first definition in
source order is kept.

Class bodies follow the same rule: methods, nested classes and class
variables inside ``if`` and ``try`` blocks of a class body (every branch)
are captured, and the first definition of a member name is kept.

Names listed in ``__all__`` that are not defined in the module itself (for
example re-exports of imported names) are captured as ``Reference`` entries so
they are never silently dropped.

Each definition is turned into a model by the builders in ``_builders``.
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
    """Parse *source* and return the public API surface as a ``Module``.

    Args:
        source: Raw Python source text.
        dotted_name: Fully-qualified module name (e.g. ``"my_pkg.core"``).
        path: The file *source* was read from. It is reported in the
            ``ParseError`` when *source* has a syntax error.
        known_all: The evaluated ``__all__`` of each module in the analyzed
            tree, by dotted name. When it holds *dotted_name*, that value is
            used as is; otherwise ``__all__`` is evaluated from *source*, and
            this mapping resolves ``__all__ += other.__all__``.
        tree: *source* already parsed, so the caller can parse each file
            once. *source* is not parsed again when it is given.

    Returns:
        A ``Module`` containing only the public names found in *source*.

    Raises:
        ParseError: When *source* cannot be parsed as valid Python.
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
    # The first definition of a name wins, as in ``collect_imports``: in
    # ``if``/``else`` or ``try``/``except`` branches, the first branch is reported.
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
    """Compute the public-name set for a module.

    Args:
        tree: Parsed module AST.
        explicit_all: Literal names from ``__all__``, or ``None`` when absent.

    Returns:
        Names to expose: the explicit list when present, otherwise every
        top-level name not starting with ``_``.
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
    """Build ``Reference`` entries for exported names with no local definition.

    A star import from a module whose ``__all__`` is known binds the names in
    that ``__all__``. Any other star-imported module (outside the analyzed
    tree, or without ``__all__``) is recorded as the candidate source of a
    name no import binds; ``resolve_module_references`` later resolves it when
    the module is in the tree.

    Args:
        tree: Parsed module AST.
        names: Exported names that were not captured as a definition.
        package: Dotted name of the containing package, used to absolutize
            relative imports.
        known_all: The evaluated ``__all__`` of each module in the analyzed
            tree, by dotted name.

    Returns:
        One ``Reference`` per name, sorted by name.
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
