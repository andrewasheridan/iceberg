# 0006. Typer CLI

Date: 2026-03-21
Status: Accepted

## Context

The project requires a CLI entry point for the `iceberg` tool. The two natural
choices are Click (the dominant Python CLI framework) and Typer (a thin layer
built on top of Click). The project enforces `mypy --strict` across all code,
which creates a preference for type-annotation-driven patterns over imperative
decorator-based ones.

## Decision

The CLI is built with Typer. Commands and options are defined using standard
Python type annotations, which mypy can verify without special plugins or
stubs. This keeps the CLI consistent with the rest of the codebase and avoids
a context switch into Click's decorator-heavy style.

The command is exposed as `iceberg` (not `sheridan-iceberg`). The shorter name
is ergonomic for pre-commit hooks and CI pipelines, and the `sheridan.*`
namespace is already conveyed by the package name. The entry point is declared
as `sheridan.iceberg.cli:app` in `pyproject.toml`.

## Consequences

- CLI construction is type-checked end-to-end with no extra effort.
- Typer is added as a runtime dependency (it pulls in Click transitively).
- The `iceberg` command name must not collide with any other tool in the
  environment; operators installing multiple `sheridan.*` tools should be aware
  of this.
- Future CLI authors follow the Typer pattern established here rather than
  dropping down to raw Click unless Typer proves insufficient.
