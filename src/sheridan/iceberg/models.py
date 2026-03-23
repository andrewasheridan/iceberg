"""Data models used across sheridan-iceberg."""

__all__ = [
    "ClassInfo",
    "ClassMember",
    "FunctionSignature",
    "Issue",
    "MemberKind",
    "ModuleInfo",
    "ParamInfo",
    "ParamKind",
]

from dataclasses import dataclass, field
from enum import StrEnum, auto
from pathlib import Path

from sheridan.iceberg.enums import IssueKind


class ParamKind(StrEnum):
    """Kind of a function parameter, matching Python's parameter categories.

    Attributes:
        positional_only: Parameter before the ``/`` separator.
        positional_or_keyword: Regular parameter, passable by position or name.
        var_positional: ``*args`` parameter.
        keyword_only: Parameter after ``*`` or ``*args``, keyword-only.
        var_keyword: ``**kwargs`` parameter.
    """

    positional_only = auto()
    positional_or_keyword = auto()
    var_positional = auto()
    keyword_only = auto()
    var_keyword = auto()


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


class MemberKind(StrEnum):
    """Kind of a public class member.

    Attributes:
        class_var: Class-level variable or annotated attribute.
        instance_attr: Instance attribute assigned in ``__init__``.
        property: ``@property``-decorated method.
        classmethod: ``@classmethod``-decorated method.
        staticmethod: ``@staticmethod``-decorated method.
        method: Regular instance method.
    """

    class_var = auto()
    instance_attr = auto()
    property = auto()
    classmethod = auto()
    staticmethod = auto()
    method = auto()


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


@dataclass
class Issue:
    """A single ``__all__`` issue found in a module.

    Attributes:
        path: Path to the affected module.
        kind: The category of issue.
        declared: The current ``__all__`` value, or ``None`` if absent.
        expected: The correct ``__all__`` value that would fix the issue.
    """

    path: Path
    kind: IssueKind
    declared: list[str] | None
    expected: list[str]

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-compatible dictionary.

        Returns:
            Dictionary with ``code``, ``path``, ``kind``, ``declared``,
            ``expected``, and ``message`` keys.
        """
        return {
            "code": self.kind.code,
            "path": str(self.path),
            "kind": self.kind.value,
            "declared": self.declared,
            "expected": self.expected,
            "message": self.to_text(),
        }

    def to_text(self) -> str:
        """Format as a human-readable single-line string.

        Returns:
            A message string suitable for terminal output.
        """
        code = self.kind.code
        match self.kind:
            case IssueKind.missing:
                return f"{self.path}: {code} missing __all__ (expected {self.expected!r})"
            case IssueKind.incorrect:
                missing = sorted(set(self.expected) - set(self.declared or []))
                return f"{self.path}: {code} names appear public but missing from __all__: {missing!r}"
            case IssueKind.unsorted:
                return f"{self.path}: {code} __all__ is not sorted (expected {self.expected!r})"
