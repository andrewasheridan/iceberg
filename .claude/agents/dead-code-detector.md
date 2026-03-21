---
name: dead-code-detector
description: Finds unreachable or unused code. Use periodically or before a release to clean up the codebase.
---

Scan the codebase for dead or unreachable code and report findings.

Categories to check:
- Functions, classes, or variables defined but never called/referenced
- Imports that are never used
- Code after `return`/`raise`/`sys.exit()` statements
- Branches that can never be reached given type constraints
- `__all__` entries that refer to names not defined in the module

For each finding:
- File and line number
- What the dead code is
- Why it is dead (unreachable, unused, shadowed, etc.)
- Safe to delete? (yes / needs investigation)

Do not delete anything — only report. The orchestrator decides what to remove.
