"""Dataclass models representing the public API surface captured by iceberg."""

__all__ = [
    "Assignment",
    "Class",
    "Function",
    "Module",
    "Package",
    "Parameter",
]
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Parameter:
    """A single function parameter."""

    name: str
    annotation: str | None
    default: str | None


@dataclass(frozen=True, slots=True)
class Function:
    """A function or method in the captured public API."""

    name: str
    positional_parameters: tuple[Parameter, ...]
    keyword_parameters: frozenset[Parameter]
    var_positional: Parameter | None
    var_keyword: Parameter | None
    returns: str | None
    is_async: bool


@dataclass(frozen=True, slots=True)
class Assignment:
    """A module- or class-level assignment."""

    name: str
    annotation: str | None
    value_repr: str | None


@dataclass(frozen=True, slots=True)
class Class:
    """A class in the captured public API."""

    name: str
    assignments: tuple[Assignment, ...]
    methods: tuple[Function, ...]
    nested_classes: tuple[Class, ...]


@dataclass(frozen=True, slots=True)
class Module:
    """A Python module's public API surface."""

    name: str
    assignments: tuple[Assignment, ...]
    classes: tuple[Class, ...]
    functions: tuple[Function, ...]


@dataclass(frozen=True, slots=True)
class Package:
    """A Python package's public API surface (a trie of modules)."""

    name: str
    path: Path
    modules: tuple[Module, ...]
    subpackages: tuple[Package, ...]
