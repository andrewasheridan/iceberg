"""Define the dataclass models for the public API that iceberg collects."""

__all__ = [
    "Assignment",
    "Class",
    "Diagnostic",
    "Function",
    "FunctionKind",
    "Module",
    "Package",
    "Parameter",
    "Reference",
    "Report",
    "Severity",
]

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

type FunctionKind = Literal["function", "method", "classmethod", "staticmethod", "property"]
"""How callers use a function: a plain function, or one of the kinds of class member.

``"function"`` is a module-level function. In a class body, these kinds apply:

- ``"method"`` is an instance method.
- ``"classmethod"`` and ``"staticmethod"`` come from the decorators with these names.
- ``"property"`` is a getter with ``@property`` or ``@functools.cached_property``.
  Callers read it as an attribute (``obj.p``). They do not call it.
"""

type Severity = Literal["error", "warning"]
"""How serious a ``Diagnostic`` is.

An ``"error"`` is a module that iceberg cannot read or parse, and skipped. A
``"warning"`` is a public name that a module exports but never binds.
"""


def _is_public_name(name: str) -> bool:
    """Check if the name of a function, class, attribute or parameter is public.

    Names without a leading underscore are public. Dunder names such as
    ``__init__``, ``__call__`` or ``__slots__`` are also public, because they
    define how users work with a class. Names with one leading underscore
    (``_x``) and name-mangled names (``__x``) are private.

    Args:
        name: The bare name to check.

    Returns:
        ``True`` if the name is public.
    """
    is_dunder = len(name) > 4 and name.startswith("__") and name.endswith("__")

    return is_dunder or not name.startswith("_")


def _is_public_module_stem(stem: str) -> bool:
    """Check if the stem of a module or package is public.

    ``__init__`` is public. All other stems with a leading underscore (also
    ``__main__``) are private.

    Args:
        stem: The last component of a dotted module or package name.

    Returns:
        ``True`` if the stem is public.
    """
    return stem == "__init__" or not stem.startswith("_")


@dataclass(frozen=True, slots=True)
class Parameter:
    """One function parameter.

    Attributes:
        name: The bare parameter name, as the source gives it.
        annotation: The unparsed annotation string, or ``None`` if there is none.
        default: The unparsed default-value string, or ``None`` if there is none.
    """

    name: str
    """The bare parameter name, as the source gives it."""

    annotation: str | None
    """The unparsed type annotation string, or ``None`` if there is none."""

    default: str | None
    """The unparsed default-value string, or ``None`` if there is none."""

    @property
    def is_public(self) -> bool:
        return _is_public_name(self.name)


@dataclass(frozen=True, slots=True)
class Function:
    """A function or method in the public API that iceberg collected.

    Attributes:
        name: The unqualified function or method name.
        positional_parameters: An ordered tuple of the positional-only and
            positional-or-keyword parameters.
        keyword_parameters: An unordered frozenset of the keyword-only parameters.
        var_positional: The ``*args`` parameter, or ``None`` if there is none.
        var_keyword: The ``**kwargs`` parameter, or ``None`` if there is none.
        returns: The unparsed return-annotation string, or ``None`` if there is none.
        is_async: ``True`` for ``async def`` functions.
        kind: How callers use the function. See ``FunctionKind``.
        decorators: The unparsed decorator expressions in source order, for
            example ``("property", "abc.abstractmethod")``.
        overloads: The ``typing.overload`` signatures of this function in
            source order, or ``()`` if it has none. Each overload is a
            ``Function`` without overloads.
    """

    name: str
    """The unqualified function or method name."""

    positional_parameters: tuple[Parameter, ...]
    """An ordered tuple of the positional-only and positional-or-keyword parameters."""

    keyword_parameters: frozenset[Parameter]
    """An unordered frozenset of the keyword-only parameters."""

    var_positional: Parameter | None
    """The ``*args`` parameter, or ``None`` if there is none."""

    var_keyword: Parameter | None
    """The ``**kwargs`` parameter, or ``None`` if there is none."""

    returns: str | None
    """The unparsed return-annotation string, or ``None`` if there is none."""

    is_async: bool
    """``True`` for ``async def`` functions. ``False`` for all other functions."""

    kind: FunctionKind = "function"
    """How callers use the function: function, method, classmethod, staticmethod or property."""

    decorators: tuple[str, ...] = ()
    """The unparsed decorator expressions in source order, without the leading ``@``."""

    overloads: tuple[Function, ...] = ()
    """The ``typing.overload`` signatures of this function in source order, or ``()``."""

    @property
    def is_public(self) -> bool:
        return _is_public_name(self.name)


@dataclass(frozen=True, slots=True)
class Assignment:
    """An assignment at module level or class level.

    Attributes:
        name: The target name, as the source gives it.
        annotation: The unparsed annotation string (from annotated
            assignments), or ``None`` for plain assignments.
    """

    name: str
    """The target name, as the source gives it."""

    annotation: str | None
    """The unparsed annotation string, or ``None`` for plain assignments."""

    @property
    def is_public(self) -> bool:
        return _is_public_name(self.name)


@dataclass(frozen=True, slots=True)
class Reference:
    """A public name that iceberg cannot resolve to a definition.

    A module exports these names (usually through ``__all__``), but their
    definition is not in the analyzed source. Examples:

    - A re-export from a different distribution (``from math import sqrt``).
    - A name that no code binds statically, for example a name that a
      module-level ``__getattr__`` supplies.

    iceberg reports these names and does not remove them. Thus, the public API
    never becomes smaller silently.

    Attributes:
        name: The public name, as the module exports it.
        module: The fully qualified module that the name comes from, or
            ``None`` if no import binds the name.
        attribute: The original attribute name for ``from module import
            attribute`` imports. ``None`` for ``import module`` bindings and
            for names without an import.
    """

    name: str
    """The public name, as the module exports it."""

    module: str | None
    """The fully qualified source module, or ``None`` if no import binds the name."""

    attribute: str | None
    """The original attribute name for ``from ... import`` bindings. ``None`` for all other names."""

    @property
    def is_public(self) -> bool:
        return _is_public_name(self.name)


@dataclass(frozen=True, slots=True)
class Class:
    """A class in the public API that iceberg collected.

    Attributes:
        name: The unqualified class name.
        bases: The unparsed base class expressions in source order, for example
            ``("Base", "Generic[T]")``.
        keywords: The unparsed keyword arguments of the class statement in
            source order, for example ``("metaclass=ABCMeta",)``.
        assignments: A tuple of the class-level assignments (class variables).
        methods: A tuple of the methods that the class body defines directly.
        nested_classes: A tuple of the classes in this class.
    """

    name: str
    """The unqualified class name."""

    bases: tuple[str, ...]
    """The unparsed base class expressions in source order."""

    keywords: tuple[str, ...]
    """The unparsed keyword arguments of the class statement, such as ``metaclass=ABCMeta``, in source order."""

    assignments: tuple[Assignment, ...]
    """The class-level assignments (class variables) in source order."""

    methods: tuple[Function, ...]
    """The methods that the class body defines directly, in source order."""

    nested_classes: tuple[Class, ...]
    """The classes in this class, in source order."""

    @property
    def is_public(self) -> bool:
        return _is_public_name(self.name)


@dataclass(frozen=True, slots=True)
class Module:
    """The public API of a Python module.

    Attributes:
        name: The fully qualified dotted module name (for example ``"pkg.sub.mod"``).
        assignments: The public module-level assignments in source order.
        classes: The public classes in source order.
        functions: The public functions in source order.
        references: The public names that iceberg cannot resolve to a
            definition, sorted by name.
    """

    name: str
    """The fully qualified dotted module name, for example ``"pkg.sub.mod"``."""

    assignments: tuple[Assignment, ...]
    """The public module-level assignments in source order."""

    classes: tuple[Class, ...]
    """The public classes that this module defines, in source order."""

    functions: tuple[Function, ...]
    """The public functions that this module defines, in source order."""

    references: tuple[Reference, ...] = ()
    """The public names that iceberg cannot resolve to a definition, sorted by name."""

    @property
    def is_public(self) -> bool:
        *_, stem = self.name.split(".")
        return _is_public_module_stem(stem)


@dataclass(frozen=True, slots=True)
class Package:
    """The public API of a Python package (a trie of modules).

    Attributes:
        name: The fully qualified dotted package name (for example ``"pkg.sub"``).
        path: The path to the package directory on disk. The JSON output shows
            it relative to the analyzed root.
        modules: A tuple of the ``Module`` objects directly in this package.
        subpackages: A tuple of the child ``Package`` objects, sorted by name.
    """

    name: str
    """The fully qualified dotted package name, for example ``"pkg.sub"``."""

    path: Path
    """The path to the package directory on disk. The JSON output shows it relative to the analyzed root."""

    modules: tuple[Module, ...]
    """The modules directly in this package."""

    subpackages: tuple[Package, ...]
    """The child packages one level below this package, sorted by name."""

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
class Diagnostic:
    """A problem that iceberg found in the analysis of one module.

    Attributes:
        severity: ``"error"`` for a module that iceberg skipped, because it
            cannot read or parse it. ``"warning"`` for an unresolved public name.
        module: The fully qualified dotted name of the module that has the problem.
        path: The source file of the module. The JSON output shows it relative
            to the analyzed root.
        message: A description of the problem, without the location.
        lineno: The 1-based line of the problem, or ``None`` if it is not known.
    """

    severity: Severity
    """``"error"`` for a skipped module. ``"warning"`` for an unresolved name."""

    module: str
    """The fully qualified dotted name of the module that has the problem."""

    path: Path
    """The source file of the module."""

    message: str
    """A description of the problem, without the location."""

    lineno: int | None = None
    """The 1-based line of the problem, or ``None`` if it is not known."""


@dataclass(frozen=True, slots=True)
class Report:
    """The public API of a path, together with the problems that the analysis found.

    Attributes:
        api: The analyzed package, or the module if the input was one file.
        diagnostics: The errors for skipped modules, then the warnings for
            unresolved public names. Each group is sorted by module.
    """

    api: Package | Module
    """The analyzed package, or the module if the input was one file."""

    diagnostics: tuple[Diagnostic, ...] = ()
    """The errors for skipped modules, then the warnings for unresolved public names."""

    @property
    def has_errors(self) -> bool:
        return any(diagnostic.severity == "error" for diagnostic in self.diagnostics)
