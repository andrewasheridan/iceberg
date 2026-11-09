"""Build iceberg models from AST definition nodes.

``visit_module`` and the public ``get_*`` utilities use the same builders.
Thus, the model of a definition is the same for all entry points.

An assignment gives one ``Assignment`` for each bound name. ``a = b = 1`` gives
``a`` and ``b``, and ``c, *rest = ...`` gives ``c`` and ``rest``. The builders
do not collect attribute targets and subscript targets.

The builders collect PEP 695 ``type X = int`` statements as an ``Assignment``
with ``annotation="TypeAlias"``. Thus, the new syntax has the same model as
aliases of the form ``X: TypeAlias = int``. Tools that use the models see the
same representation for the two forms.

The builders collect function decorators as source strings. The decorators set
the ``Function.kind`` of a method:

- ``@property`` and ``@cached_property`` make a ``"property"``.
- ``@classmethod`` and ``@staticmethod`` make the kinds with these names.
- All other methods are a ``"method"``.

The builders do not report property setters, getters and deleters
(``@p.setter``), because they do not add a new name.

The builders put ``typing.overload`` signatures into one ``Function``. The
implementation after the overloads holds the overload signatures in
``Function.overloads``. Thus, the builders report each name one time. If there
is no implementation (for example in ``if TYPE_CHECKING:``), the last overload
represents the group.

The builders collect class bases and keyword arguments (such as
``metaclass=``) as unparsed source. They do not collect docstrings and class
decorators.
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
        in_class: ``True`` if *node* is in a class body. Then its decorators
            decide if it is a method, a classmethod, a staticmethod or a
            property.
        overloads: The ``@overload`` signatures that *node* implements, in
            source order. See ``group_overloads``.

    Returns:
        A ``Function`` with the name, the parameters, the return annotation,
        the async flag, the kind and the decorators of the function.
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
    """Check if *node* has the decorator ``typing.overload``.

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
    definition of that name without ``@overload``. That definition is the
    implementation. If no implementation comes after the overloads, the last
    overload represents the group.

    Args:
        statements: The statements of one scope (a module or a class body), in
            source order.

    Returns:
        Two items. First, a mapping from each implementation (or from the last
        overload that represents the group) to its overloads in source order.
        Second, the set of overload definitions that iceberg does not report
        separately.
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
"""The decorator names (the last dotted part) that make a method a property."""

_ACCESSOR_ATTRIBUTES = frozenset({"setter", "getter", "deleter"})
"""The attributes of a property that define one of its accessors again (``@p.setter``)."""


def _decorator_name(decorator: ast.expr) -> str | None:
    """Find the last dotted part of the name of a decorator.

    Args:
        decorator: A decorator expression, for example ``functools.cached_property``
            or ``lru_cache(maxsize=None)``.

    Returns:
        ``"cached_property"`` for ``functools.cached_property``. The called
        name for a call such as ``lru_cache(...)``. ``None`` for all other
        expressions.
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

    A property decorator has priority over ``classmethod`` and ``staticmethod``.

    Args:
        decorators: The ``decorator_list`` of a function in a class body.

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
    """Check if *node* defines again an accessor of a property with the same name.

    Args:
        node: A function in a class body.

    Returns:
        ``True`` for ``@p.setter``, ``@p.getter`` or ``@p.deleter`` on a
        function with the name ``p``.
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
    """Divide an ``arguments`` node into the four parameter groups.

    Args:
        args: The ``arguments`` node of a function definition.

    Returns:
        A four-tuple ``(positional, keyword_only, var_positional,
        var_keyword)``. *positional* is an ordered tuple of the
        positional-only and positional-or-keyword parameters. *keyword_only*
        is an unordered frozenset. The last two items are optional
        ``Parameter`` instances for ``*args`` and ``**kwargs``.
    """
    # The defaults of positional parameters align with the end of the list.
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

    The function does these steps:

    - It goes into nested class definitions recursively.
    - It collects the methods and the class-level assignments, also in the
      ``if`` and ``try`` blocks of the class body.
    - It skips property setters, getters and deleters.
    - It puts ``@overload`` signatures together with their implementation.

    If the class defines a name more than one time, the function keeps only the
    first definition. It keeps the bases and keyword arguments such as
    ``metaclass=`` as unparsed source. It does **not** read
    ``node.decorator_list`` or docstrings.

    Args:
        node: A ``ClassDef`` AST node.

    Returns:
        A ``Class`` with the name, the bases and the keyword arguments. It also
        has the assignments, the methods and the nested classes of the class body.
    """
    assignments: list[Assignment] = []
    methods: list[Function] = []
    nested_classes: list[Class] = []
    # As in ``visit_module``, read the ``if``/``try`` branches. The first
    # definition of a name has priority.
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
    """Build one ``Assignment`` for each name that an ``Assign`` statement binds.

    The function accepts chained assignment (``a = b = 1``) and tuple, list
    and starred unpacking (``c, *rest = ...``). It skips attribute targets and
    subscript targets. If the statement binds a name two times, the function
    reports it one time.

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
    """Build an ``Assignment`` from a simple name target.

    For targets that are not simple, such as tuple unpacking or attribute
    assignment, the result is ``None``.

    Args:
        node: An ``Assign`` or ``AnnAssign`` AST node.

    Returns:
        An ``Assignment`` if the target is a plain name. If not, ``None``.
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
        The unparsed string for *node*, or ``None`` if *node* is ``None``.
    """
    if node is None:
        return None

    return ast.unparse(node)


_MAX_DEFAULT_LENGTH = 80
"""iceberg reports a default as ``...`` if its source is longer than this value."""


def _value_source(node: ast.expr | None) -> str | None:
    """Unparse a parameter default to source.

    The function renders all expressions with ``ast.unparse``. If the result
    is longer than ``_MAX_DEFAULT_LENGTH`` characters, the function replaces it
    with ``...``. Thus, the report still shows that the parameter has a default.

    Args:
        node: An AST expression node, or ``None``.

    Returns:
        The unparsed string for *node* (or ``...`` if it is too long). ``None``
        if *node* is ``None``.
    """
    if node is None:
        return None

    source = ast.unparse(node)
    if len(source) > _MAX_DEFAULT_LENGTH:
        return "..."

    return source


def build_type_alias(node: ast.TypeAlias) -> Assignment:
    """Build an ``Assignment`` from a PEP 695 ``type X = ...`` statement.

    The function keeps the alias with ``annotation="TypeAlias"``. Thus, tools
    that use the model get the same representation as for aliases of the form
    ``X: TypeAlias = ...``.

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
            # The grammar makes TypeAlias.name always an ast.Name. The code never
            # gets to this branch, but the exhaustive type check needs it.
            raise ParseError(  # pragma: no cover
                f"Unexpected TypeAlias name node: {ast.dump(node.name)}"
            )
