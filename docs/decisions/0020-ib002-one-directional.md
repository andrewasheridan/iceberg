# 0020. IB002 is One-Directional (AST → `__all__`)

Date: 2026-03-22
Status: Accepted

## Context

The original IB002 ("incorrect `__all__`") fired on any set difference between `declared_all` and `inferred_all` in either direction, making it a catch-all for any mismatch. This produced false positives for packages that intentionally re-export names from submodules: those names appear in `__all__` but have no corresponding top-level AST definition in the same file.

## Decision

We decided to make IB002 one-directional. IB002 now fires only when the AST contains public names absent from `__all__` — i.e., `set(inferred_all) - set(declared_all)` is non-empty. Names present in `__all__` with no corresponding AST definition (phantom exports, intentional re-exports, dynamically defined names) do not trigger IB002.

IB003 (unsorted) is now independent of IB002 and can fire on the same module simultaneously.

The `fix` subcommand retains a full bidirectional comparison (`fix_needed` in `fixer.py`): it rewrites `__all__` to exactly `sorted(inferred_all)`, removing phantom exports. Check and fix therefore have intentionally divergent scopes — `check` is conservative, `fix` is authoritative.

## Consequences

**Positive:**
- IB002 is a narrower, more actionable signal — it fires only when something looks public but is explicitly unlisted.
- Phantom exports and intentional re-exports are not flagged by `check`, reducing false positives.
- IB002 and IB003 can now both fire on the same module without one masking the other.

**Negative:**
- `check` and `fix` have intentionally different semantics; this asymmetry must be clearly documented to avoid user confusion.
- Users who rely on re-exports should ensure their `__init__.py` is captured by the AST walker's from-import logic (ADR 0013); otherwise `fix` will remove those names from `__all__`.
