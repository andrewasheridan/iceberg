"""Issue detection and reporting for __all__ correctness."""

__all__ = [
    "Issue",
    "IssueKind",
    "check_modules",
    "report",
]

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from sheridan.iceberg.ast_walker import ModuleInfo


class IssueKind(StrEnum):
    """Categories of __all__ issues that iceberg detects.

    Attributes:
        MISSING: Module has no ``__all__`` declaration.  ``IB001``
        INCORRECT: Names the AST considers public are absent from ``__all__``.  ``IB002``
        UNSORTED: ``__all__`` is correct but not in sorted order.  ``IB003``
    """

    MISSING = "missing"
    INCORRECT = "incorrect"
    UNSORTED = "unsorted"

    @property
    def code(self) -> str:
        """Return the short error code for this issue kind.

        Returns:
            A ruff-style error code string, e.g. ``"IB001"``.
        """
        _codes: dict[IssueKind, str] = {
            IssueKind.MISSING: "IB001",
            IssueKind.INCORRECT: "IB002",
            IssueKind.UNSORTED: "IB003",
        }
        return _codes[self]


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
            Dictionary with ``code``, ``path``, ``kind``, ``declared``, and ``expected``.
        """
        return {
            "code": self.kind.code,
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
        code = self.kind.code
        match self.kind:
            case IssueKind.MISSING:
                return f"{self.path}: {code} missing __all__ (expected {self.expected!r})"
            case IssueKind.INCORRECT:
                missing = sorted(set(self.expected) - set(self.declared or []))
                return f"{self.path}: {code} names appear public but missing from __all__: {missing!r}"
            case IssueKind.UNSORTED:
                return f"{self.path}: {code} __all__ is not sorted (expected {self.expected!r})"


def _check_module(info: ModuleInfo) -> list[Issue]:
    """Check a single module for __all__ issues.

    IB002 fires when names the AST considers public are absent from ``__all__``
    (one-directional: names in ``__all__`` that don't exist in the AST are not
    reported).  IB003 is independent and can fire on the same module as IB002.

    Args:
        info: Parsed module information.

    Returns:
        List of issues found (empty if the module is clean).
    """
    issues: list[Issue] = []
    expected = sorted(info.inferred_all)

    if info.declared_all is None:
        issues.append(Issue(path=info.path, kind=IssueKind.MISSING, declared=None, expected=expected))
        return issues

    # IB002: names the AST considers public but absent from __all__
    missing_from_all = sorted(set(info.inferred_all) - set(info.declared_all))
    if missing_from_all:
        issues.append(
            Issue(
                path=info.path,
                kind=IssueKind.INCORRECT,
                declared=info.declared_all,
                expected=expected,  # full inferred list — fixer uses this
            )
        )

    # IB003: __all__ is not sorted (independent of IB002)
    if info.declared_all != sorted(info.declared_all):
        issues.append(
            Issue(
                path=info.path,
                kind=IssueKind.UNSORTED,
                declared=info.declared_all,
                expected=sorted(info.declared_all),
            )
        )

    return issues


def check_modules(modules: list[ModuleInfo]) -> list[Issue]:
    """Check a list of modules for ``__all__`` issues.

    The programmatic entry point for issue detection. Returns issues only,
    with no formatting — callers decide how to render or handle them.

    Args:
        modules: Parsed module information to check.

    Returns:
        List of issues found across all modules (empty if all are clean).
    """
    all_issues: list[Issue] = []
    for info in modules:
        all_issues.extend(_check_module(info))
    return all_issues


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

    all_issues = check_modules(modules)

    if fmt == "json":
        output = json.dumps([i.to_dict() for i in all_issues], indent=2)
    else:
        output = "\n".join(i.to_text() for i in all_issues)

    return all_issues, output
