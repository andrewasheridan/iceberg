# 0003. __all__ Is Authoritative; AST Inference Is a Fallback Only

Date: 2026-03-21
Status: Accepted

## Context

A Python module's public API can be expressed in two ways: explicitly via `__all__`, or implicitly via the set of top-level names that do not begin with an underscore. When both signals exist, iceberg must decide which to trust. When neither exists, iceberg must decide what to report.

## Decision

When `__all__` is present in a module, it is the sole authoritative source of the public API. iceberg accepts it as-is and does not cross-reference it against top-level names, add missing names, or remove names the author chose to include. The author's intent is final.

When `__all__` is absent, iceberg falls back to inferring the public API from top-level non-underscore names discovered via AST. This inferred set is used only to drive reporting (flag the missing `__all__`) and fixing (write a generated `__all__`). The inferred set is never treated as semantically equivalent to an explicit `__all__` — it is a best-effort scaffold, not a declaration of intent.

## Consequences

- Modules with a present but wrong `__all__` (e.g. misspelled names, stale entries) will not be silently corrected; iceberg will report the `__all__` as written. Correctness of the contents is the author's responsibility.
- The distinction between "has `__all__`" and "lacks `__all__`" is preserved in all output formats, allowing consumers to distinguish authoritative surfaces from inferred ones.
- Auto-fix always produces an explicit `__all__`, moving a module from the inferred category into the authoritative one.
- This rule keeps iceberg's scope narrow: it enforces the presence and form of `__all__`, not the semantic correctness of its contents.
