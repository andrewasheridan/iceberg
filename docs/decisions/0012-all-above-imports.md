# 0012. `__all__` Is Declared Before Imports

Date: 2026-03-21
Status: Accepted

## Context

Python does not mandate any position for `__all__`. Convention in the broader ecosystem places it after imports and before class/function definitions. However, `__all__` declares the public API surface of a module — the most important thing to know when reading a module. Placing it after a block of imports buries the lead: a reader must scroll past all import noise before seeing what the module actually exports.

## Decision

We decided that in all `sheridan.*` modules, `__all__` is declared immediately after the module docstring (and any shebang line or leading comments), before any import statements. It is the first executable statement in the module.

Example layout:

```python
"""Module docstring."""

__all__ = [
    "PublicThing",
]

import stdlib_module
from sheridan.other import SomeThing
```

This is a project style convention only. `iceberg` does not detect or enforce `__all__` position — it checks for presence, correctness, and sort order. Enforcement of this convention relies on code review and developer discipline.

## Consequences

- The public API surface is visible at a glance without scrolling past imports.
- All five source modules in this repo have been updated to follow this layout.
- `__all__` entries are string literals, so placing the declaration before imports is valid Python — the names do not need to be in scope at the point of the `__all__` assignment.
- This convention applies to all future `sheridan.*` modules and is documented in `CLAUDE.md`.
- `iceberg`'s auto-fix behaviour is not changed; it inserts `__all__` after the docstring regardless of import position, which aligns with this convention in practice.
