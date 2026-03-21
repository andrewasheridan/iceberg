# 0015. Ruff-Style `IB` Error Codes

Date: 2026-03-21
Status: Accepted

## Context

iceberg produces diagnostics when a module has a missing, incorrect, or unsorted `__all__`. Without short, stable codes, those diagnostics are hard to grep for, cite in documentation, or reference in issue trackers. Long-form names like `"missing"` already exist as `IssueKind` values but are not reference-friendly.

Ruff popularised short prefix-plus-number codes (`E501`, `F401`) that Python developers already recognise and know how to use.

## Decision

We chose to adopt ruff-style short error codes with the `IB` prefix ("IceBerg"). The `code` property on `IssueKind` holds the code string. Current assignments:

| Code | Meaning |
|------|---------|
| IB001 | Missing `__all__` |
| IB002 | Incorrect `__all__` |
| IB003 | `__all__` is not sorted |

Codes appear in text output (`path/to/file.py: IB001 missing __all__ ...`) and in the `"code"` field of JSON output. Future codes continue from IB004 upward.

The `IB` prefix namespaces codes to this tool, avoiding collision with ruff's own code namespaces if iceberg output is ever consumed alongside ruff output.

## Consequences

- Diagnostics are grep-friendly and can be cited precisely in documentation, issues, and CI output.
- The `IB` prefix makes the tool of origin unambiguous when output is mixed with other linters.
- Users can search for a code by name (`IB002`) to find the relevant documentation or rule.
- Future iceberg rules have a clear, consistent naming convention to follow.
- Long-form `IssueKind` names remain as the human-readable description alongside each code; codes do not replace them.
- Using a new prefix means no coordination with the ruff project is needed, and no collision risk exists today.
