"""Data models used across sheridan-iceberg."""

__all__ = [
    "ClassInfo",
    "ClassMember",
    "FunctionSignature",
    "ModuleInfo",
    "ParamInfo",
]

from dataclasses import dataclass, field
from pathlib import Path

from sheridan.iceberg.enums import MemberKind, ParamKind


@dataclass
class ParamInfo:
    """Information about a single function parameter.

    Attributes:
        name: Parameter name.
        annotation: Type annotation as a string, or ``None`` if unannotated.
        has_default: Whether the parameter has a default value.
        kind: Parameter category.
    """

    name: str
    annotation: str | None = None
    has_default: bool = False
    kind: ParamKind = ParamKind.positional_or_keyword


@dataclass
class FunctionSignature:
    """Signature of a function or method.

    Attributes:
        params: Ordered list of parameters.
        return_annotation: Return type annotation as a string, or ``None``.
        is_async: Whether the function is an ``async def``.
    """

    params: list[ParamInfo] = field(default_factory=list)
    return_annotation: str | None = None
    is_async: bool = False


@dataclass
class ClassMember:
    """A single public member of a class.

    Attributes:
        name: Member name.
        kind: Member kind.
        annotation: Type annotation string for attribute members, or ``None``.
        signature: Function signature for callable members, or ``None``.
    """

    name: str
    kind: MemberKind
    annotation: str | None = None
    signature: FunctionSignature | None = None


@dataclass
class ClassInfo:
    """Public-facing information about a class.

    Attributes:
        bases: Base class names as strings.
        members: Public members in declaration order.
    """

    bases: list[str] = field(default_factory=list)
    members: list[ClassMember] = field(default_factory=list)


@dataclass
class ModuleInfo:
    """Information extracted from a single Python module.

    Attributes:
        path: Absolute path to the module file.
        declared_all: The list declared in ``__all__``, or ``None`` if absent.
        inferred_all: Names inferred from top-level non-underscore definitions.
        function_signatures: Signatures of public top-level functions, keyed by name.
        class_info: Public member info for top-level classes, keyed by name.
    """

    path: Path
    declared_all: list[str] | None
    inferred_all: list[str] = field(default_factory=list)
    function_signatures: dict[str, FunctionSignature] = field(default_factory=dict)
    class_info: dict[str, ClassInfo] = field(default_factory=dict)

    @property
    def effective_all(self) -> list[str]:
        """Return the authoritative public API surface.

        Returns:
            ``declared_all`` when present, otherwise ``inferred_all``.
        """
        if self.declared_all is not None:
            return self.declared_all
        return self.inferred_all
