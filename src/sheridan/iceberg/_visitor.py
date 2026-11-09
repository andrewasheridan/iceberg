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

Names listed in ``__all__`` that are not defined in the module itself (for
example re-exports of imported names) are captured as ``Reference`` entries so
they are never silently dropped.

Assignments contribute one ``Assignment`` per bound name: ``a = b = 1``
yields ``a`` and ``b``, and ``c, *rest = ...`` yields ``c`` and ``rest``.
Attribute and subscript targets are not captured.

PEP 695 ``type X = int`` statements are captured as ``Assignment`` with
``annotation="TypeAlias"``. This maps the new syntax onto the same model
used for ``X: TypeAlias = int`` style aliases so downstream tools see a
consistent representation regardless of which form the source uses.

Explicitly excluded from capture: docstrings, decorators, class bases.
"""

__all__ = ["visit_module"]

import ast

from sheridan.iceberg._exceptions import ParseError
from sheridan.iceberg._models import Assignment, Class, Function, Module, Parameter, Reference
from sheridan.iceberg._utilities import (
    bound_names,
    collect_imports,
    extract_all,
    infer_all,
    module_level_statements,
)


def visit_module(source: str, dotted_name: str) -> Module:
    """Parse *source* and return the public API surface as a ``Module``.

    Args:
        source: Raw Python source text.
        dotted_name: Fully-qualified module name (e.g. ``"my_pkg.core"``).

    Returns:
        A ``Module`` containing only the public names found in *source*.

    Raises:
        ParseError: When *source* cannot be parsed as valid Python.
    """
    try:
        tree = ast.parse(source, feature_version=(3, 14))
    except SyntaxError as exc:
        raise ParseError(str(exc)) from exc

    explicit_all = extract_all(tree)
    public = _top_level_public_names(tree, explicit_all)

    assignments: list[Assignment] = []
    classes: list[Class] = []
    functions: list[Function] = []
    # The first definition of a name wins, as in ``collect_imports``: in
    # ``if``/``else`` or ``try``/``except`` branches, the first branch is reported.
    seen: set[str] = set()

    def keep(name: str) -> bool:
        if name not in public or name in seen:
            return False
        seen.add(name)
        return True

    for node in module_level_statements(tree.body):
        match node:
            case (ast.FunctionDef() | ast.AsyncFunctionDef()) as fn_node:
                if keep(fn_node.name):
                    functions.append(_build_function(fn_node))

            case ast.ClassDef() as cls_node:
                if keep(cls_node.name):
                    classes.append(_build_class(cls_node))

            case ast.Assign() as assign_node:
                assignments.extend(a for a in _build_assignments(assign_node) if keep(a.name))

            case ast.AnnAssign() as ann_node:
                result = _build_assignment(ann_node)
                if result is not None and keep(result.name):
                    assignments.append(result)

            case ast.TypeAlias() as alias_node:
                alias = _build_type_alias(alias_node)
                if keep(alias.name):
                    assignments.append(alias)

            case _:
                pass

    references: tuple[Reference, ...] = ()
    if explicit_all is not None:
        references = _build_references(tree, explicit_all - seen, dotted_name.rpartition(".")[0])

    return Module(
        name=dotted_name,
        assignments=tuple(assignments),
        classes=tuple(classes),
        functions=tuple(functions),
        references=references,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


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


def _build_references(tree: ast.Module, names: frozenset[str], package: str) -> tuple[Reference, ...]:
    """Build ``Reference`` entries for exported names with no local definition.

    Args:
        tree: Parsed module AST.
        names: Exported names that were not captured as a definition.
        package: Dotted name of the containing package, used to absolutize
            relative imports.

    Returns:
        One ``Reference`` per name, sorted by name.
    """
    imports = collect_imports(tree, package)
    references: list[Reference] = []
    for name in sorted(names):
        module, attribute = imports.get(name, (None, None))
        references.append(Reference(name=name, module=module, attribute=attribute))
    return tuple(references)


def _build_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Function:
    """Build a ``Function`` model from a function definition node.

    Args:
        node: A ``FunctionDef`` or ``AsyncFunctionDef`` AST node.

    Returns:
        A ``Function`` capturing the name, parameters, return annotation, and
        whether the function is async.
    """
    positional, keyword_only, var_positional, var_keyword = _build_parameters(node.args)
    return Function(
        name=node.name,
        positional_parameters=positional,
        keyword_parameters=keyword_only,
        var_positional=var_positional,
        var_keyword=var_keyword,
        returns=_annotation_source(node.returns),
        is_async=isinstance(node, ast.AsyncFunctionDef),
    )


def _build_parameters(
    args: ast.arguments,
) -> tuple[
    tuple[Parameter, ...],
    frozenset[Parameter],
    Parameter | None,
    Parameter | None,
]:
    """Split an ``arguments`` node into the four parameter groups.

    Args:
        args: The ``arguments`` node from a function definition.

    Returns:
        A four-tuple of ``(positional, keyword_only, var_positional,
        var_keyword)`` where *positional* is an ordered tuple covering
        positional-only and positional-or-keyword parameters, *keyword_only*
        is an unordered frozenset, and the last two are optional ``Parameter``
        instances for ``*args`` and ``**kwargs``.
    """
    # Defaults for positional params are right-aligned.
    all_positional_nodes = args.posonlyargs + args.args
    n_pos = len(all_positional_nodes)
    n_defaults = len(args.defaults)
    padding = n_pos - n_defaults

    positional: list[Parameter] = []
    for i, arg in enumerate(all_positional_nodes):
        default_index = i - padding
        default: str | None = None
        if default_index >= 0:
            default = _value_source(args.defaults[default_index])
        positional.append(
            Parameter(
                name=arg.arg,
                annotation=_annotation_source(arg.annotation),
                default=default,
            )
        )

    keyword_only: set[Parameter] = set()
    for arg, default_node in zip(
        args.kwonlyargs,
        args.kw_defaults,
        strict=True,
    ):
        kw_default: str | None = None
        if default_node is not None:
            kw_default = _value_source(default_node)
        keyword_only.add(
            Parameter(
                name=arg.arg,
                annotation=_annotation_source(arg.annotation),
                default=kw_default,
            )
        )

    var_positional: Parameter | None = None
    if args.vararg is not None:
        var_positional = Parameter(
            name=args.vararg.arg,
            annotation=_annotation_source(args.vararg.annotation),
            default=None,
        )

    var_keyword: Parameter | None = None
    if args.kwarg is not None:
        var_keyword = Parameter(
            name=args.kwarg.arg,
            annotation=_annotation_source(args.kwarg.annotation),
            default=None,
        )

    return tuple(positional), frozenset(keyword_only), var_positional, var_keyword


def _build_class(node: ast.ClassDef) -> Class:
    """Build a ``Class`` model from a class definition node.

    Recurses into nested class definitions. Extracts methods and class-level
    assignments. Does **not** read ``node.bases``, ``node.decorator_list``,
    or any docstring.

    Args:
        node: A ``ClassDef`` AST node.

    Returns:
        A ``Class`` capturing the name, assignments, methods, and nested
        classes found in the class body.
    """
    assignments: list[Assignment] = []
    methods: list[Function] = []
    nested_classes: list[Class] = []

    for child in node.body:
        match child:
            case (ast.FunctionDef() | ast.AsyncFunctionDef()) as fn_child:
                fn = _build_function(fn_child)
                if fn.is_public:
                    methods.append(fn)

            case ast.ClassDef() as cls_child:
                nested = _build_class(cls_child)
                if nested.is_public:
                    nested_classes.append(nested)

            case ast.Assign() as assign_child:
                assignments.extend(a for a in _build_assignments(assign_child) if a.is_public)

            case ast.AnnAssign() as ann_child:
                result = _build_assignment(ann_child)
                if result is not None and result.is_public:
                    assignments.append(result)

            case ast.TypeAlias() as alias_child:
                alias = _build_type_alias(alias_child)
                if alias.is_public:
                    assignments.append(alias)

            case _:
                pass

    return Class(
        name=node.name,
        assignments=tuple(assignments),
        methods=tuple(methods),
        nested_classes=tuple(nested_classes),
    )


def _build_assignments(node: ast.Assign) -> list[Assignment]:
    """Build one ``Assignment`` for every name an ``Assign`` statement binds.

    Covers chained assignment (``a = b = 1``) and tuple, list, and starred
    unpacking (``c, *rest = ...``). Attribute and subscript targets are
    skipped. A name bound twice in the same statement is reported once.

    Args:
        node: An ``Assign`` AST node.

    Returns:
        The assignments in source order, each with ``annotation=None``.
    """
    names: dict[str, None] = {}
    for target in node.targets:
        names.update(dict.fromkeys(bound_names(target)))
    return [Assignment(name=name, annotation=None) for name in names]


def _build_assignment(node: ast.Assign | ast.AnnAssign) -> Assignment | None:
    """Build an ``Assignment`` from a simple name target, or return ``None``.

    Returns ``None`` for non-simple targets such as tuple unpacking or
    attribute assignment.

    Args:
        node: An ``Assign`` or ``AnnAssign`` AST node.

    Returns:
        An ``Assignment`` when the target is a plain name, otherwise ``None``.
    """
    match node:
        case ast.AnnAssign(target=ast.Name(id=name), annotation=ann):
            return Assignment(
                name=name,
                annotation=_annotation_source(ann),
            )

        case ast.Assign(targets=[ast.Name(id=name)]):
            return Assignment(
                name=name,
                annotation=None,
            )

        case _:
            return None


def _annotation_source(node: ast.expr | None) -> str | None:
    """Return the source representation of an annotation node.

    Args:
        node: An AST expression node, or ``None``.

    Returns:
        The unparsed string for *node*, or ``None`` when *node* is ``None``.
    """
    if node is None:
        return None
    return ast.unparse(node)


_MAX_DEFAULT_LENGTH = 80
"""Defaults whose source is longer than this are reported as ``...``."""


def _value_source(node: ast.expr | None) -> str | None:
    """Return the source representation of a parameter default.

    Any expression is rendered with ``ast.unparse``. A rendering longer than
    ``_MAX_DEFAULT_LENGTH`` characters is replaced by ``...`` so that the
    parameter is still reported as having a default.

    Args:
        node: An AST expression node, or ``None``.

    Returns:
        The unparsed string for *node* (or ``...`` when it is too long), or
        ``None`` when *node* is ``None``.
    """
    if node is None:
        return None

    source = ast.unparse(node)
    if len(source) > _MAX_DEFAULT_LENGTH:
        return "..."
    return source


def _build_type_alias(node: ast.TypeAlias) -> Assignment:
    """Build an ``Assignment`` from a PEP 695 ``type X = ...`` statement.

    The alias is stored with ``annotation="TypeAlias"`` so that downstream
    tools receive a representation consistent with ``X: TypeAlias = ...``
    style aliases.

    Args:
        node: A ``TypeAlias`` AST node.

    Returns:
        An ``Assignment`` with ``annotation="TypeAlias"``.
    """
    match node.name:
        case ast.Name(id=name):
            return Assignment(
                name=name,
                annotation="TypeAlias",
            )
        case _:
            # TypeAlias.name is always ast.Name per the grammar; this branch
            # is unreachable but satisfies exhaustive type checking.
            raise ParseError(  # pragma: no cover
                f"Unexpected TypeAlias name node: {ast.dump(node.name)}"
            )
