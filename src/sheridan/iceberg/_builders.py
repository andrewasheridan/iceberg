"""Builders that turn AST definition nodes into iceberg models.

``visit_module`` and the public ``get_*`` utilities share these builders, so a
definition is modelled the same way whichever entry point reads it.

Assignments contribute one ``Assignment`` per bound name: ``a = b = 1``
yields ``a`` and ``b``, and ``c, *rest = ...`` yields ``c`` and ``rest``.
Attribute and subscript targets are not captured.

PEP 695 ``type X = int`` statements are captured as ``Assignment`` with
``annotation="TypeAlias"``. This maps the new syntax onto the same model
used for ``X: TypeAlias = int`` style aliases so downstream tools see a
consistent representation regardless of which form the source uses.

Function decorators are captured as source strings, and decide the
``Function.kind`` of a method: ``@property`` and ``@cached_property``
make a ``"property"``, ``@classmethod`` and ``@staticmethod`` make those
kinds, and any other method is a ``"method"``. Property setters, getters and
deleters (``@p.setter``) are not reported, because they add no new name.

``typing.overload`` signatures are grouped into one ``Function``: the
implementation that follows them carries the overload signatures in
``Function.overloads``, so each name is reported once. When there is no
implementation (for example under ``if TYPE_CHECKING:``), the last overload
stands for the group.

Class bases and keyword arguments (such as ``metaclass=``) are captured as
unparsed source. Docstrings and class decorators are not captured.
"""

__all__ = [
    "build_assignment",
    "build_assignments",
    "build_class",
    "build_function",
    "build_type_alias",
    "group_overloads",
]

import ast

from sheridan.iceberg._exceptions import ParseError
from sheridan.iceberg._models import Assignment, Class, Function, FunctionKind, Parameter
from sheridan.iceberg._utilities import bound_names, module_level_statements


def build_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    in_class: bool = False,
    overloads: tuple[ast.FunctionDef | ast.AsyncFunctionDef, ...] = (),
) -> Function:
    """Build a ``Function`` model from a function definition node.

    Args:
        node: A ``FunctionDef`` or ``AsyncFunctionDef`` AST node.
        in_class: ``True`` when *node* is in a class body, so that its
            decorators decide whether it is a method, classmethod,
            staticmethod or property.
        overloads: The ``@overload`` signatures that *node* implements, in
            source order; see ``group_overloads``.

    Returns:
        A ``Function`` capturing the name, parameters, return annotation,
        whether the function is async, its kind and its decorators.
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
        kind=_method_kind(node.decorator_list) if in_class else "function",
        decorators=tuple(ast.unparse(decorator) for decorator in node.decorator_list),
        overloads=tuple(build_function(overload, in_class=in_class) for overload in overloads),
    )


type _FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


def _is_overload(node: _FunctionNode) -> bool:
    """Check whether *node* is decorated with ``typing.overload``.

    Args:
        node: A function definition.

    Returns:
        ``True`` for ``@overload``, ``@typing.overload`` or
        ``@typing_extensions.overload``.
    """
    return any(_decorator_name(decorator) == "overload" for decorator in node.decorator_list)


def group_overloads(
    statements: list[ast.stmt],
) -> tuple[dict[_FunctionNode, tuple[_FunctionNode, ...]], set[_FunctionNode]]:
    """Group ``@overload`` signatures with the definition that implements them.

    The overloads of a name are the ``@overload`` definitions before the next
    definition of that name without ``@overload``, which is the implementation.
    When no implementation follows, the last overload stands for the group.

    Args:
        statements: The statements of one scope (a module or a class body), in
            source order.

    Returns:
        A mapping from each implementation (or standing-in last overload) to
        its overloads in source order, and the set of overload definitions that
        are not reported on their own.
    """
    overloads: dict[_FunctionNode, tuple[_FunctionNode, ...]] = {}
    grouped: set[_FunctionNode] = set()
    pending: dict[str, list[_FunctionNode]] = {}

    for node in statements:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        if _is_overload(node):
            pending.setdefault(node.name, []).append(node)
        elif node.name in pending:
            group = pending.pop(node.name)
            overloads[node] = tuple(group)
            grouped.update(group)

    for *rest, last in pending.values():
        overloads[last] = (*rest, last)
        grouped.update(rest)

    return overloads, grouped


_PROPERTY_DECORATORS = frozenset({"property", "cached_property", "abstractproperty"})
"""Decorator names (the last dotted part) that make a method a property."""

_ACCESSOR_ATTRIBUTES = frozenset({"setter", "getter", "deleter"})
"""Attributes of a property that redefine one of its accessors (``@p.setter``)."""


def _decorator_name(decorator: ast.expr) -> str | None:
    """Find the last dotted part of a decorator's name.

    Args:
        decorator: A decorator expression, for example ``functools.cached_property``
            or ``lru_cache(maxsize=None)``.

    Returns:
        ``"cached_property"`` for ``functools.cached_property``, the called
        name for a call such as ``lru_cache(...)``, or ``None`` for any other
        expression.
    """
    match decorator:
        case ast.Call(func=func):
            return _decorator_name(func)
        case ast.Name(id=name) | ast.Attribute(attr=name):
            return name
        case _:
            return None


def _method_kind(decorators: list[ast.expr]) -> FunctionKind:
    """Decide the kind of a method from its decorators.

    A property decorator wins over ``classmethod`` and ``staticmethod``.

    Args:
        decorators: The ``decorator_list`` of a function defined in a class body.

    Returns:
        ``"property"``, ``"classmethod"``, ``"staticmethod"`` or ``"method"``.
    """
    names = {_decorator_name(decorator) for decorator in decorators}

    if names & _PROPERTY_DECORATORS:
        return "property"

    if "classmethod" in names:
        return "classmethod"

    if "staticmethod" in names:
        return "staticmethod"

    return "method"


def _is_property_accessor(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check whether *node* redefines an accessor of a property with the same name.

    Args:
        node: A function defined in a class body.

    Returns:
        ``True`` for ``@p.setter``, ``@p.getter`` or ``@p.deleter`` on a
        function named ``p``.
    """
    for decorator in node.decorator_list:
        match decorator:
            case ast.Attribute(value=ast.Name(id=owner), attr=attr):
                if attr in _ACCESSOR_ATTRIBUTES and owner == node.name:
                    return True

            case _:
                pass

    return False


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
    for arg, default_node in zip(args.kwonlyargs, args.kw_defaults, strict=True):
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


def build_class(node: ast.ClassDef) -> Class:
    """Build a ``Class`` model from a class definition node.

    Recurses into nested class definitions. Extracts methods and class-level
    assignments, including those inside ``if`` and ``try`` blocks of the class
    body, skipping property setters, getters and deleters, and groups
    ``@overload`` signatures with their implementation. When a name is defined
    more than once, only the first definition is kept. Bases and keyword
    arguments such as ``metaclass=`` are kept as unparsed source. Does **not**
    read ``node.decorator_list`` or any docstring.

    Args:
        node: A ``ClassDef`` AST node.

    Returns:
        A ``Class`` capturing the name, bases, keyword arguments, and the
        assignments, methods, and nested classes found in the class body.
    """
    assignments: list[Assignment] = []
    methods: list[Function] = []
    nested_classes: list[Class] = []
    # As in ``visit_module``: ``if``/``try`` branches are read, and the first
    # definition of a name wins.
    seen: set[str] = set()
    statements = list(module_level_statements(node.body))
    overloads, grouped = group_overloads(statements)

    def keep(name: str, *, is_public: bool) -> bool:
        if not is_public or name in seen:
            return False

        seen.add(name)
        return True

    for child in statements:
        match child:
            case (ast.FunctionDef() | ast.AsyncFunctionDef()) as fn_child:
                if fn_child in grouped or _is_property_accessor(fn_child):
                    continue

                fn = build_function(fn_child, in_class=True, overloads=overloads.get(fn_child, ()))
                if keep(fn.name, is_public=fn.is_public):
                    methods.append(fn)

            case ast.ClassDef() as cls_child:
                nested = build_class(cls_child)
                if keep(nested.name, is_public=nested.is_public):
                    nested_classes.append(nested)

            case ast.Assign() as assign_child:
                for assignment in build_assignments(assign_child):
                    if keep(assignment.name, is_public=assignment.is_public):
                        assignments.append(assignment)

            case ast.AnnAssign() as ann_child:
                result = build_assignment(ann_child)
                if result is not None and keep(result.name, is_public=result.is_public):
                    assignments.append(result)

            case ast.TypeAlias() as alias_child:
                alias = build_type_alias(alias_child)
                if keep(alias.name, is_public=alias.is_public):
                    assignments.append(alias)

            case _:
                pass

    return Class(
        name=node.name,
        bases=tuple(ast.unparse(base) for base in node.bases),
        keywords=tuple(ast.unparse(keyword) for keyword in node.keywords),
        assignments=tuple(assignments),
        methods=tuple(methods),
        nested_classes=tuple(nested_classes),
    )


def build_assignments(node: ast.Assign) -> list[Assignment]:
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


def build_assignment(node: ast.Assign | ast.AnnAssign) -> Assignment | None:
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
    """Unparse an annotation node to source.

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
    """Unparse a parameter default to source.

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


def build_type_alias(node: ast.TypeAlias) -> Assignment:
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
