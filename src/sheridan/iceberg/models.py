"""Data models used across sheridan-iceberg."""

__all__ = [
    "Issue",
    "ModuleInfo",
]

from dataclasses import dataclass, field
from pathlib import Path

from sheridan.iceberg.enums import IssueKind


@dataclass
class ModuleInfo:
    """Information extracted from a single Python module.

    Attributes:
        path: Absolute path to the module file.
        declared_all: The list declared in __all__, or None if absent.
        inferred_all: Names inferred from top-level non-underscore definitions.
    """

    path: Path
    declared_all: list[str] | None
    inferred_all: list[str] = field(default_factory=list)

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
