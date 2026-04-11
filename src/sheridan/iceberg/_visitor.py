"""AST visitor that converts a Python source file into a ``Module`` snapshot.

Public names are determined as follows:

- If the source defines ``__all__``, only the literal string values listed
  there are considered public.
- Otherwise every top-level name that does **not** start with ``_`` is public.

PEP 695 ``type X = int`` statements are captured as ``Assignment`` with
``annotation="TypeAlias"`` and ``value_repr`` set to the unparsed RHS. This
maps the new syntax onto the same model field used for
``X: TypeAlias = int`` style aliases so downstream tools see a consistent
representation regardless of which form the source uses.

Explicitly excluded from capture: docstrings, decorators, class bases.
"""

__all__ = ["visit_module"]

import ast

from sheridan.iceberg._exceptions import ParseError
from sheridan.iceberg._models import Assignment, Class, Function, Module, Parameter


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

    explicit_all = _extract_all(tree)
    public = _top_level_public_names(tree, explicit_all)

    assignments: list[Assignment] = []
    classes: list[Class] = []
    functions: list[Function] = []

    for node in tree.body:
        match node:
            case (ast.FunctionDef() | ast.AsyncFunctionDef()) as fn_node:
                if fn_node.name in public:
                    functions.append(_build_function(fn_node))

            case ast.ClassDef() as cls_node:
                if cls_node.name in public:
                    classes.append(_build_class(cls_node))

            case ast.Assign() as assign_node:
                result = _build_assignment(assign_node)
                if result is not None and result.name in public:
                    assignments.append(result)

            case ast.AnnAssign() as ann_node:
                result = _build_assignment(ann_node)
                if result is not None and result.name in public:
                    assignments.append(result)

            case ast.TypeAlias() as alias_node:
                alias = _build_type_alias(alias_node)
                if alias.name in public:
                    assignments.append(alias)

            case _:
                pass

    return Module(
        name=dotted_name,
        assignments=tuple(assignments),
        classes=tuple(classes),
        functions=tuple(functions),
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_all(tree: ast.Module) -> frozenset[str] | None:
    """Return the literal string members of ``__all__``, or ``None``.

    Scans the module body for the first simple assignment to ``__all__``
    whose RHS is a list or tuple of string constants.

    Args:
        tree: Parsed module AST.

    Returns:
        A frozen set of string names when ``__all__`` is found and parseable,
        otherwise ``None``.
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


def _collect_string_elements(node: ast.expr) -> frozenset[str] | None:
    """Extract string literals from a list or tuple AST node.

    Args:
        node: An AST expression, expected to be a ``List`` or ``Tuple``.

    Returns:
        A frozen set of strings when all elements are string constants,
        otherwise ``None``.
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
                methods.append(_build_function(fn_child))

            case ast.ClassDef() as cls_child:
                nested_classes.append(_build_class(cls_child))

            case ast.Assign() as assign_child:
                result = _build_assignment(assign_child)
                if result is not None:
                    assignments.append(result)

            case ast.AnnAssign() as ann_child:
                result = _build_assignment(ann_child)
                if result is not None:
                    assignments.append(result)

            case ast.TypeAlias() as alias_child:
                assignments.append(_build_type_alias(alias_child))

            case _:
                pass

    return Class(
        name=node.name,
        assignments=tuple(assignments),
        methods=tuple(methods),
        nested_classes=tuple(nested_classes),
    )


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
        case ast.AnnAssign(target=ast.Name(id=name), annotation=ann, value=value):
            return Assignment(
                name=name,
                annotation=_annotation_source(ann),
                value_repr=_value_source(value) if value is not None else None,
            )

        case ast.Assign(targets=[ast.Name(id=name)], value=value):
            return Assignment(
                name=name,
                annotation=None,
                value_repr=_value_source(value),
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


def _value_source(node: ast.expr | None) -> str | None:
    """Return the source representation for simple RHS expressions only.

    Covers literals, names, attribute accesses, and subscripts. Returns
    ``None`` for anything more complex (calls, comprehensions, etc.).

    Args:
        node: An AST expression node, or ``None``.

    Returns:
        The unparsed string for *node* when it is a supported simple form,
        otherwise ``None``.
    """
    if node is None:
        return None

    match node:
        case ast.Constant():
            return ast.unparse(node)

        case ast.Name():
            return ast.unparse(node)

        case ast.Attribute():
            return ast.unparse(node)

        case ast.Subscript():
            return ast.unparse(node)

        case _:
            return None


def _build_type_alias(node: ast.TypeAlias) -> Assignment:
    """Build an ``Assignment`` from a PEP 695 ``type X = ...`` statement.

    The alias is stored with ``annotation="TypeAlias"`` and ``value_repr``
    set to the unparsed RHS so that downstream tools receive a representation
    consistent with ``X: TypeAlias = ...`` style aliases.

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
                value_repr=ast.unparse(node.value),
            )
        case _:
            # TypeAlias.name is always ast.Name per the grammar; this branch
            # is unreachable but satisfies exhaustive type checking.
            raise ParseError(  # pragma: no cover
                f"Unexpected TypeAlias name node: {ast.dump(node.name)}"
            )
