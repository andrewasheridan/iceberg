"""Dataclass models representing the public API surface captured by iceberg."""

__all__ = [
    "Assignment",
    "Class",
    "DiscoveredModule",
    "Function",
    "Module",
    "Package",
    "Parameter",
    "Reference",
    "ResolveReport",
]

from dataclasses import dataclass
from pathlib import Path


def _is_public_name(name: str) -> bool:
    """Return whether a function, class, attribute, or parameter name is public.

    Names without a leading underscore are public. Dunder names such as
    ``__init__``, ``__call__`` or ``__slots__`` are public too, because they
    define how users interact with a class. Names with one leading underscore
    (``_x``) and name-mangled names (``__x``) are private.

    Args:
        name: The bare name to check.

    Returns:
        ``True`` when the name is public.
    """
    is_dunder = len(name) > 4 and name.startswith("__") and name.endswith("__")
    return is_dunder or not name.startswith("_")


def _is_public_module_stem(stem: str) -> bool:
    """Return whether a module or package stem is public.

    ``__init__`` is public; any other stem with a leading underscore
    (including ``__main__``) is private.

    Args:
        stem: The last component of a dotted module or package name.

    Returns:
        ``True`` when the stem is public.
    """
    return stem == "__init__" or not stem.startswith("_")


@dataclass(frozen=True, slots=True)
class Parameter:
    """A single function parameter.

    Attributes:
        name: The bare parameter name as written in the source.
        annotation: The unparsed annotation string, or ``None`` when absent.
        default: The unparsed default-value string, or ``None`` when absent.
    """

    name: str
    """Bare parameter name as written in the source."""

    annotation: str | None
    """Unparsed type annotation string, or ``None`` when absent."""

    default: str | None
    """Unparsed default-value string, or ``None`` when absent."""

    @property
    def is_public(self) -> bool:
        return _is_public_name(self.name)


@dataclass(frozen=True, slots=True)
class Function:
    """A function or method in the captured public API.

    Attributes:
        name: The unqualified function or method name.
        positional_parameters: Ordered tuple of positional-only and
            positional-or-keyword parameters.
        keyword_parameters: Unordered frozenset of keyword-only parameters.
        var_positional: The ``*args`` parameter, or ``None`` when absent.
        var_keyword: The ``**kwargs`` parameter, or ``None`` when absent.
        returns: Unparsed return-annotation string, or ``None`` when absent.
        is_async: ``True`` for ``async def`` functions.
    """

    name: str
    """Unqualified function or method name."""

    positional_parameters: tuple[Parameter, ...]
    """Ordered tuple of positional-only and positional-or-keyword parameters."""

    keyword_parameters: frozenset[Parameter]
    """Unordered frozenset of keyword-only parameters."""

    var_positional: Parameter | None
    """The ``*args`` parameter, or ``None`` when absent."""

    var_keyword: Parameter | None
    """The ``**kwargs`` parameter, or ``None`` when absent."""

    returns: str | None
    """Unparsed return-annotation string, or ``None`` when absent."""

    is_async: bool
    """``True`` for ``async def`` functions, ``False`` otherwise."""

    @property
    def is_public(self) -> bool:
        return _is_public_name(self.name)


@dataclass(frozen=True, slots=True)
class Assignment:
    """A module- or class-level assignment.

    Attributes:
        name: The target name as written in the source.
        annotation: Unparsed annotation string (from annotated assignments),
            or ``None`` for plain assignments.
    """

    name: str
    """Target name as written in the source."""

    annotation: str | None
    """Unparsed annotation string, or ``None`` for plain assignments."""

    @property
    def is_public(self) -> bool:
        return _is_public_name(self.name)


@dataclass(frozen=True, slots=True)
class Reference:
    """A public name that iceberg could not resolve to a definition.

    References cover names that a module exports (usually via ``__all__``) but
    whose definition lives outside the analyzed source, for example a
    re-export from another distribution (``from math import sqrt``), or a name
    that is never bound statically at all (for example one provided by a
    module-level ``__getattr__``). They are reported rather than dropped so
    that the public surface never silently shrinks.

    Attributes:
        name: The public name as it is exported.
        module: Fully-qualified module the name was imported from, or ``None``
            when no import binding the name was found.
        attribute: The original attribute name for ``from module import
            attribute`` imports, or ``None`` for ``import module`` bindings and
            names with no import.
    """

    name: str
    """Public name as it is exported."""

    module: str | None
    """Fully-qualified source module, or ``None`` when no import binds the name."""

    attribute: str | None
    """Original attribute name for ``from ... import`` bindings, otherwise ``None``."""

    @property
    def is_public(self) -> bool:
        return _is_public_name(self.name)


@dataclass(frozen=True, slots=True)
class Class:
    """A class in the captured public API.

    Attributes:
        name: The unqualified class name.
        assignments: Tuple of class-level assignments (class variables).
        methods: Tuple of methods defined directly in the class body.
        nested_classes: Tuple of classes nested inside this class.
    """

    name: str
    """Unqualified class name."""

    assignments: tuple[Assignment, ...]
    """Class-level assignments (class variables) in source order."""

    methods: tuple[Function, ...]
    """Methods defined directly in the class body, in source order."""

    nested_classes: tuple[Class, ...]
    """Classes nested inside this class, in source order."""

    @property
    def is_public(self) -> bool:
        return _is_public_name(self.name)


@dataclass(frozen=True, slots=True)
class Module:
    """A Python module's public API surface.

    Attributes:
        name: Fully-qualified dotted module name (e.g. ``"pkg.sub.mod"``).
        assignments: Public module-level assignments in source order.
        classes: Public classes in source order.
        functions: Public functions in source order.
        references: Public names that could not be resolved to a definition,
            sorted by name.
    """

    name: str
    """Fully-qualified dotted module name, e.g. ``"pkg.sub.mod"``."""

    assignments: tuple[Assignment, ...]
    """Public module-level assignments in source order."""

    classes: tuple[Class, ...]
    """Public classes defined in this module, in source order."""

    functions: tuple[Function, ...]
    """Public functions defined in this module, in source order."""

    references: tuple[Reference, ...] = ()
    """Public names that could not be resolved to a definition, sorted by name."""

    @property
    def is_public(self) -> bool:
        *_, stem = self.name.split(".")
        return _is_public_module_stem(stem)


@dataclass(frozen=True, slots=True)
class Package:
    """A Python package's public API surface (a trie of modules).

    Attributes:
        name: Fully-qualified dotted package name (e.g. ``"pkg.sub"``).
        path: Absolute path to the package directory on disk.
        modules: Tuple of ``Module`` objects belonging directly to this package.
        subpackages: Tuple of child ``Package`` objects, sorted by name.
    """

    name: str
    """Fully-qualified dotted package name, e.g. ``"pkg.sub"``."""

    path: Path
    """Absolute path to the package directory on disk."""

    modules: tuple[Module, ...]
    """Modules belonging directly to this package."""

    subpackages: tuple[Package, ...]
    """Child packages nested one level below this package, sorted by name."""

    @property
    def _init_module(self) -> Module | None:
        for module in self.modules:
            if module.name == self.name:
                return module
        return None

    @property
    def assignments(self) -> tuple[Assignment, ...]:
        if init_module := self._init_module:
            return init_module.assignments
        return ()

    @property
    def classes(self) -> tuple[Class, ...]:
        if init_module := self._init_module:
            return init_module.classes
        return ()

    @property
    def functions(self) -> tuple[Function, ...]:
        if init_module := self._init_module:
            return init_module.functions
        return ()

    @property
    def references(self) -> tuple[Reference, ...]:
        if init_module := self._init_module:
            return init_module.references
        return ()

    @property
    def is_public(self) -> bool:
        *_, stem = self.name.split(".")
        return _is_public_module_stem(stem)


@dataclass(frozen=True, slots=True)
class DiscoveredModule:
    """A single Python source file identified during discovery.

    Attributes:
        dotted_name: The fully-qualified dotted module name, e.g. ``pkg.sub.mod``.
        source_path: Absolute path to the ``.py`` file on disk.
        is_init: ``True`` when the file is an ``__init__.py``.
        package_parts: Tuple of ancestor directory names that form the dotted
            prefix, excluding the module's own stem. Empty for top-level modules.
    """

    dotted_name: str
    """Fully-qualified dotted module name, e.g. ``"pkg.sub.mod"``."""

    source_path: Path
    """Absolute path to the ``.py`` source file on disk."""

    is_init: bool
    """``True`` when the file is an ``__init__.py``, ``False`` otherwise."""

    package_parts: tuple[str, ...]
    """Ancestor directory names forming the dotted prefix, excluding the module stem."""

    @property
    def is_public(self) -> bool:
        *_, stem = self.dotted_name.split(".")
        return _is_public_module_stem(stem)


@dataclass(frozen=True, slots=True)
class ResolveReport:
    """Outcome of init re-export resolution.

    Attributes:
        unresolved: Names that appeared in the init's public surface but could
            not be resolved to a concrete object in any sibling module or
            locally within the init file itself.
    """

    unresolved: tuple[str, ...]
    """Names from the public surface that could not be resolved to any concrete symbol."""
