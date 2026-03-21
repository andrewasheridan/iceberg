# 0002. Static Analysis Only

Date: 2026-03-21
Status: Accepted

## Context

`iceberg` needs to inspect Python modules to determine their public API surface. There are two broad approaches: import the module at runtime, or parse it statically using the `ast` module. Runtime import gives a fully resolved view of the module's namespace but carries significant risks and constraints.

## Decision

`iceberg` uses Python's `ast` module for all analysis. It never imports or executes user code.

## Consequences

- Safe to run on untrusted codebases — no arbitrary code execution occurs.
- No side effects from module-level code (network calls, file writes, database connections, etc.).
- No need to install user project dependencies before running `iceberg`.
- Works correctly even when user code has import errors or missing dependencies.
- Analysis is limited to statically visible information; dynamically constructed names (e.g. `__all__ = list(globals())`) will not be resolved.
