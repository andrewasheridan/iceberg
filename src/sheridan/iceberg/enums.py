"""Enumerations used across sheridan-iceberg."""

__all__ = [
    "IssueKind",
    "OutputFormat",
    "ShowFormat",
]

from enum import StrEnum, auto


class IssueKind(StrEnum):
    """Categories of ``__all__`` issues that iceberg detects.

    Attributes:
        missing: Module has no ``__all__`` declaration.  ``IB001``
        incorrect: Names the AST considers public are absent from ``__all__``.  ``IB002``
        unsorted: ``__all__`` is correct but not in sorted order.  ``IB003``
    """

    missing = auto()
    incorrect = auto()
    unsorted = auto()

    @property
    def code(self) -> str:
        """Return the short error code for this issue kind.

        Returns:
            A ruff-style error code string, e.g. ``"IB001"``.
        """
        _codes: dict[IssueKind, str] = {
            IssueKind.missing: "IB001",
            IssueKind.incorrect: "IB002",
            IssueKind.unsorted: "IB003",
        }
        return _codes[self]


class OutputFormat(StrEnum):
    """Supported output formats for the check command."""

    text = auto()
    json = auto()


class ShowFormat(StrEnum):
    """Supported output formats for the show command."""

    tree = auto()
    json = auto()
