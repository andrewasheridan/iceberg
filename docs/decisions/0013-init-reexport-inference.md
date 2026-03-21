# 0013. From-Imports Are Included in Inferred Public API for `__init__.py` Only

Date: 2026-03-21
Status: Accepted

## Context

ADR-0003 established that when `__all__` is absent, iceberg infers the public API from top-level non-underscore names. The original inference logic counted locally-defined names only: functions, classes, and assignments.

`__init__.py` files present a different case. The idiomatic Python pattern for building a clean package-level API is to re-export names from submodules using `from x import y` statements. Without counting these imports, iceberg's inferred set for any `__init__.py` would exclude all re-exported names, producing a suggested `__all__ = []` or a severely undersized one — both wrong.

In non-`__init__.py` modules, `from x import y` is almost always an implementation import, not a re-export. Counting it there would pollute the inferred surface with private dependencies.

## Decision

We decided to treat `__init__.py` files as a special case for inference only. In `__init__.py` modules, names introduced by `from x import y` or `from x import y as z` are included in the inferred public API if the local name does not start with an underscore. In all other modules, from-imports are ignored during inference.

This rule applies only when `__all__` is absent. When `__all__` is present, ADR-0003 applies: it is authoritative and iceberg does not modify it.

Alternatives considered:

- **Always require explicit `__all__` in `__init__.py`, skip inference.** Rejected: removes the fallback guarantee that ADR-0003 depends on. Iceberg must be able to generate a scaffold for any module.
- **Count from-imports in all modules.** Rejected: in regular modules, `from x import y` is an implementation detail. Counting it would produce false positives and inflate the inferred surface.

## Consequences

- Inferred `__all__` for `__init__.py` files will reflect re-exported names, matching author intent in the common case.
- Auto-fix for `__init__.py` files will produce a more accurate scaffold, reducing manual correction after a fix run.
- Inference logic branches on filename (`__init__.py` vs. other). This is a deliberate and bounded special case.
- Non-`__init__.py` modules are unaffected.
