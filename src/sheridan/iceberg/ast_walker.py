"""AST-based walker for extracting public API surface from Python modules."""

__all__ = [
    "ModuleInfo",
    "base_for",
    "load_modules",
    "module_id",
    "resolve_show_modules",
    "walk_module",
    "walk_path",
]

import ast
import contextlib
from pathlib import Path

from sheridan.iceberg.enums import MemberKind, ParamKind
from sheridan.iceberg.models import (
    ClassInfo,
    ClassMember,
    FunctionSignature,
    ModuleInfo,
    ParamInfo,
)


def _annotation_to_str(node: ast.expr | None) -> str | None:
    """Convert an AST annotation node to its source string representation.

    Args:
        node: An AST expression node representing a type annotation, or ``None``.

    Returns:
        The unparsed annotation string, or ``None`` if ``node`` is ``None``.
    """
    if node is None:
        return None
    return ast.unparse(node)


def _extract_function_signature(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> FunctionSignature:
    """Extract a :class:`FunctionSignature` from an AST function node.

    Args:
        node: A function or async-function definition node.

    Returns:
        The function's signature including all parameters and return annotation.
    """
    args = node.args
    params: list[ParamInfo] = []

    # defaults for positional args are right-aligned across posonlyargs + args
    all_positional = args.posonlyargs + args.args
    n_no_default = len(all_positional) - len(args.defaults)

    for i, arg in enumerate(args.posonlyargs):
        params.append(
            ParamInfo(
                name=arg.arg,
                annotation=_annotation_to_str(arg.annotation),
                has_default=i >= n_no_default,
                kind=ParamKind.positional_only,
            )
        )

    for i, arg in enumerate(args.args):
        idx = len(args.posonlyargs) + i
        params.append(
            ParamInfo(
                name=arg.arg,
                annotation=_annotation_to_str(arg.annotation),
                has_default=idx >= n_no_default,
                kind=ParamKind.positional_or_keyword,
            )
        )

    if args.vararg:
        params.append(
            ParamInfo(
                name=args.vararg.arg,
                annotation=_annotation_to_str(args.vararg.annotation),
                kind=ParamKind.var_positional,
            )
        )

    for i, arg in enumerate(args.kwonlyargs):
        params.append(
            ParamInfo(
                name=arg.arg,
                annotation=_annotation_to_str(arg.annotation),
                has_default=args.kw_defaults[i] is not None,
                kind=ParamKind.keyword_only,
            )
        )

    if args.kwarg:
        params.append(
            ParamInfo(
                name=args.kwarg.arg,
                annotation=_annotation_to_str(args.kwarg.annotation),
                kind=ParamKind.var_keyword,
            )
        )

    return FunctionSignature(
        params=params,
        return_annotation=_annotation_to_str(node.returns),
        is_async=isinstance(node, ast.AsyncFunctionDef),
    )


def _get_method_kind(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> MemberKind | None:
    """Determine a method's :class:`MemberKind` from its decorators.

    Args:
        node: A function or async-function definition node.

    Returns:
        The appropriate :class:`MemberKind`, or ``None`` if the method should
        be skipped (e.g. a property setter or deleter).
    """
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name):
            if decorator.id == "property":
                return MemberKind.property
            if decorator.id == "classmethod":
                return MemberKind.classmethod
            if decorator.id == "staticmethod":
                return MemberKind.staticmethod
        elif isinstance(decorator, ast.Attribute):
            if decorator.attr in ("setter", "deleter"):
                return None
    return MemberKind.method


def _extract_instance_attrs(
    init_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ClassMember]:
    """Extract public instance attributes assigned via ``self`` in ``__init__``.

    Scans the body of an ``__init__`` method for ``self.attr = ...`` and
    ``self.attr: type = ...`` patterns and returns a member for each unique
    public attribute found.

    Args:
        init_node: The ``__init__`` method's AST node.

    Returns:
        List of :class:`ClassMember` with kind ``instance_attr``.
    """
    attrs: list[ClassMember] = []
    seen: set[str] = set()

    for stmt in ast.walk(init_node):
        if isinstance(stmt, ast.AnnAssign):
            target = stmt.target
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
                and not target.attr.startswith("_")
                and target.attr not in seen
            ):
                attrs.append(
                    ClassMember(
                        name=target.attr,
                        kind=MemberKind.instance_attr,
                        annotation=_annotation_to_str(stmt.annotation),
                    )
                )
                seen.add(target.attr)
        elif isinstance(stmt, ast.Assign):
            for t in stmt.targets:
                if (
                    isinstance(t, ast.Attribute)
                    and isinstance(t.value, ast.Name)
                    and t.value.id == "self"
                    and not t.attr.startswith("_")
                    and t.attr not in seen
                ):
                    attrs.append(ClassMember(name=t.attr, kind=MemberKind.instance_attr))
                    seen.add(t.attr)

    return attrs


def _extract_class_info(node: ast.ClassDef) -> ClassInfo:
    """Extract public-facing :class:`ClassInfo` from an AST class definition.

    Collects public class variables (``ast.Assign`` / ``ast.AnnAssign`` at
    class body level), public instance attributes assigned in ``__init__``,
    and all public methods (regular, property, classmethod, staticmethod).
    Property setters and deleters are intentionally omitted.

    Args:
        node: A class definition AST node.

    Returns:
        :class:`ClassInfo` describing the class's public surface.
    """
    members: list[ClassMember] = []
    seen: set[str] = set()

    for item in node.body:
        if isinstance(item, ast.AnnAssign):
            if isinstance(item.target, ast.Name) and not item.target.id.startswith("_") and item.target.id not in seen:
                members.append(
                    ClassMember(
                        name=item.target.id,
                        kind=MemberKind.class_var,
                        annotation=_annotation_to_str(item.annotation),
                    )
                )
                seen.add(item.target.id)
        elif isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_") and target.id not in seen:
                    members.append(ClassMember(name=target.id, kind=MemberKind.class_var))
                    seen.add(target.id)
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if item.name == "__init__":
                for attr in _extract_instance_attrs(item):
                    if attr.name not in seen:
                        members.append(attr)
                        seen.add(attr.name)
            elif not item.name.startswith("_"):
                kind = _get_method_kind(item)
                if kind is None:
                    continue
                members.append(
                    ClassMember(
                        name=item.name,
                        kind=kind,
                        signature=_extract_function_signature(item),
                    )
                )
                seen.add(item.name)

    return ClassInfo(
        bases=[ast.unparse(b) for b in node.bases],
        members=members,
    )


def _extract_declared_all(tree: ast.Module) -> list[str] | None:
    """Extract the value of ``__all__`` from a parsed AST, if present.

    Only handles the common pattern ``__all__ = [...]`` or ``__all__ = (...)``.
    More exotic assignments (augmented, annotated, etc.) are ignored and treated
    as absent.

    Args:
        tree: Parsed AST of a module.

    Returns:
        A list of names, or ``None`` if ``__all__`` is not found or unparseable.
    """
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not (isinstance(target, ast.Name) and target.id == "__all__"):
                continue
            value = node.value
            if isinstance(value, (ast.List, ast.Tuple)):
                names: list[str] = []
                for elt in value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        names.append(elt.value)
                    else:
                        # Non-string element — treat as unparseable
                        return None
                return names
    return None


def _infer_public_names(tree: ast.Module, is_init: bool = False) -> list[str]:
    """Infer public names from top-level definitions.

    Collects names of top-level functions, classes, and simple variable
    assignments that do not start with an underscore.

    When ``is_init`` is ``True`` (i.e. the module is an ``__init__.py``),
    also collects names re-exported via ``from ... import`` statements.
    For each alias the local name is ``alias.asname`` when present, otherwise
    ``alias.name``; names starting with ``_`` are excluded.

    Args:
        tree: Parsed AST of a module.
        is_init: When ``True``, treat ``from ... import`` names as public.

    Returns:
        Sorted list of inferred public names.
    """
    names: list[str] = []
    for node in ast.iter_child_nodes(tree):
        match node:
            case ast.FunctionDef(name=name) | ast.AsyncFunctionDef(name=name):
                if not name.startswith("_"):
                    names.append(name)
            case ast.ClassDef(name=name):
                if not name.startswith("_"):
                    names.append(name)
            case ast.Assign(targets=targets):
                for target in targets:
                    if isinstance(target, ast.Name) and not target.id.startswith("_") and target.id != "__all__":
                        names.append(target.id)
            case ast.ImportFrom(names=aliases) if is_init:
                for alias in aliases:
                    local_name = alias.asname if alias.asname else alias.name
                    if not local_name.startswith("_"):
                        names.append(local_name)
    return sorted(names)


def _is_test_file(path: Path) -> bool:
    """Return True if *path* is a test module that should be skipped.

    Matches pytest's default discovery conventions: files named ``test_*.py``,
    ``*_test.py``, or ``conftest.py``.

    Args:
        path: Path to a ``.py`` file.

    Returns:
        ``True`` if the file is a test module, ``False`` otherwise.
    """
    name = path.name
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def load_modules(path: Path) -> list[ModuleInfo]:
    """Load module info from a file or directory.

    Convenience wrapper: if ``path`` is a file, returns a single-element list;
    if it is a directory, delegates to :func:`walk_path`.  Test files are
    always skipped.

    Args:
        path: A ``.py`` file or a directory to walk recursively.

    Returns:
        List of parsed :class:`ModuleInfo`.  Empty if the file is a test module.

    Raises:
        SyntaxError: If a single file cannot be parsed.
        OSError: If a single file cannot be read.
    """
    if path.is_dir():
        return walk_path(path)
    if _is_test_file(path):
        return []
    return [walk_module(path)]


def walk_module(path: Path) -> ModuleInfo:
    """Parse a single Python file and extract its public API surface.

    Args:
        path: Path to a ``.py`` file.

    Returns:
        A :class:`ModuleInfo` describing the module's public surface, including
        function signatures and class member info for all public top-level
        definitions.

    Raises:
        SyntaxError: If the file cannot be parsed as valid Python.
        OSError: If the file cannot be read.
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    declared = _extract_declared_all(tree)
    inferred = _infer_public_names(tree, is_init=path.name == "__init__.py")

    function_signatures: dict[str, FunctionSignature] = {}
    class_info: dict[str, ClassInfo] = {}

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                function_signatures[node.name] = _extract_function_signature(node)
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            class_info[node.name] = _extract_class_info(node)

    variable_types: dict[str, str | None] = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.AnnAssign):
            if (
                isinstance(node.target, ast.Name)
                and node.target.id != "__all__"
                and node.target.id not in function_signatures
                and node.target.id not in class_info
            ):
                variable_types[node.target.id] = ast.unparse(node.annotation)
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id != "__all__"
            and node.targets[0].id not in function_signatures
            and node.targets[0].id not in class_info
            and node.targets[0].id not in variable_types
        ):
            variable_types[node.targets[0].id] = None

    return ModuleInfo(
        path=path,
        declared_all=declared,
        inferred_all=inferred,
        function_signatures=function_signatures,
        class_info=class_info,
        variable_types=variable_types,
    )


def base_for(path: Path) -> Path:
    """Return the base directory for computing relative module paths.

    Args:
        path: A file or directory path supplied as the root of a walk.

    Returns:
        ``path`` itself when it is a directory, otherwise its parent.
    """
    return path if path.is_dir() else path.parent


def module_id(path: Path, base: Path) -> str:
    """Convert a module file path to a dotted module identifier.

    Strips the ``.py`` suffix, replaces path separators with dots, and
    collapses ``.__init__`` suffixes so that package init files are
    identified by their package name rather than ``pkg.__init__``.

    Args:
        path: Absolute path to the ``.py`` file.
        base: Root directory used as the anchor for relative path computation.

    Returns:
        Dotted module identifier, e.g. ``"sheridan.iceberg"`` for
        ``src/sheridan/iceberg/__init__.py`` with ``base=src/``.
        Falls back to ``str(path)`` if ``path`` is not relative to ``base``.
    """
    try:
        rel = path.relative_to(base)
        mid = str(rel).removesuffix(".py").replace("/", ".")
        if mid.endswith(".__init__"):
            mid = mid[: -len(".__init__")]
        return mid
    except ValueError:
        return str(path)


def resolve_show_modules(modules: list[ModuleInfo], use_ast: bool = False) -> list[ModuleInfo]:
    """Filter modules for the show command, honoring ``__all__`` as package truth.

    When ``use_ast`` is ``False`` (default), any package whose ``__init__.py``
    declares ``__all__`` is treated as authoritative: only that ``__init__`` is
    kept and all other modules inside that package directory are dropped.
    This reflects the principle that ``__all__`` in ``__init__.py`` is the
    complete public API of the package.

    When ``use_ast`` is ``True``, all modules are returned unchanged so callers
    see every module's AST-inferred names.

    Args:
        modules: Parsed module information to filter.
        use_ast: When ``True``, bypass filtering and return all modules.

    Returns:
        Filtered list of :class:`ModuleInfo` to display.
    """
    if use_ast:
        return list(modules)

    result: list[ModuleInfo] = []
    covered_dirs: set[Path] = set()

    for info in sorted(modules, key=lambda m: len(m.path.parts)):
        parent = info.path.parent
        if any(parent.is_relative_to(d) for d in covered_dirs):
            continue
        if info.path.name == "__init__.py" and info.declared_all is not None:
            covered_dirs.add(parent)
        result.append(info)

    return result


def walk_path(root: Path) -> list[ModuleInfo]:
    """Recursively walk a directory and parse all Python modules.

    Skips files that cannot be parsed (logs a warning but continues).

    Args:
        root: Root directory to walk.

    Returns:
        List of :class:`ModuleInfo` for each parseable ``.py`` file found.
    """
    results: list[ModuleInfo] = []
    for py_file in sorted(root.rglob("*.py")):
        if _is_test_file(py_file):
            continue
        with contextlib.suppress(SyntaxError, OSError):
            results.append(walk_module(py_file))
    return results
