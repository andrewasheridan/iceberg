"""Issue detection and reporting for __all__ correctness."""

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from sheridan.iceberg.ast_walker import ModuleInfo

__all__ = [
    "Issue",
    "IssueKind",
    "report",
]


class IssueKind(str, Enum):
    """Categories of __all__ issues that iceberg detects.

    Attributes:
        MISSING: Module has no ``__all__`` declaration.
        INCORRECT: ``__all__`` exists but does not match the inferred public API.
        UNSORTED: ``__all__`` is correct but not in sorted order.
    """

    MISSING = "missing"
    INCORRECT = "incorrect"
    UNSORTED = "unsorted"


@dataclass
class Issue:
    """A single __all__ issue found in a module.

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
            Dictionary with ``path``, ``kind``, ``declared``, and ``expected``.
        """
        return {
            "path": str(self.path),
            "kind": self.kind.value,
            "declared": self.declared,
            "expected": self.expected,
        }

    def to_text(self) -> str:
        """Format as a human-readable single-line string.

        Returns:
            A message string suitable for terminal output.
        """
        match self.kind:
            case IssueKind.MISSING:
                return f"{self.path}: missing __all__ (expected {self.expected!r})"
            case IssueKind.INCORRECT:
                return (
                    f"{self.path}: incorrect __all__ "
                    f"(declared {self.declared!r}, expected {self.expected!r})"
                )
            case IssueKind.UNSORTED:
                return f"{self.path}: __all__ is not sorted (expected {self.expected!r})"


def _check_module(info: ModuleInfo) -> list[Issue]:
    """Check a single module for __all__ issues.

    Args:
        info: Parsed module information.

    Returns:
        List of issues found (empty if the module is clean).
    """
    issues: list[Issue] = []
    expected = sorted(info.inferred_all)

    if info.declared_all is None:
        issues.append(
            Issue(
                path=info.path,
                kind=IssueKind.MISSING,
                declared=None,
                expected=expected,
            )
        )
        return issues

    declared_set = set(info.declared_all)
    expected_set = set(expected)

    if declared_set != expected_set:
        issues.append(
            Issue(
                path=info.path,
                kind=IssueKind.INCORRECT,
                declared=info.declared_all,
                expected=expected,
            )
        )
    elif info.declared_all != sorted(info.declared_all):
        issues.append(
            Issue(
                path=info.path,
                kind=IssueKind.UNSORTED,
                declared=info.declared_all,
                expected=sorted(info.declared_all),
            )
        )

    return issues


def report(
    modules: list[ModuleInfo],
    fmt: str = "text",
) -> tuple[list[Issue], str]:
    """Check a list of modules and produce a report.

    Args:
        modules: Parsed module information to check.
        fmt: Output format — ``"text"`` (default) or ``"json"``.

    Returns:
        A tuple of ``(issues, output_string)``.

    Raises:
        ValueError: If ``fmt`` is not ``"text"`` or ``"json"``.
    """
    if fmt not in {"text", "json"}:
        raise ValueError(f"Unknown format {fmt!r}; expected 'text' or 'json'")

    all_issues: list[Issue] = []
    for info in modules:
        all_issues.extend(_check_module(info))

    if fmt == "json":
        output = json.dumps([i.to_dict() for i in all_issues], indent=2)
    else:
        output = "\n".join(i.to_text() for i in all_issues)

    return all_issues, output
