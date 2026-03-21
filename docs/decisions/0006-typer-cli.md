# 0006. CLI Framework: argparse (migrated from Typer)

Date: 2026-03-21
Status: Accepted

## Context

The CLI was originally built with Typer, which pulls in Click as a transitive
runtime dependency. A dependency audit found that Typer/Click add install weight
that is inappropriate for a tool designed to run as a pre-commit hook, where
fast, lean installs matter. The project also has a strong preference for stdlib
over third-party dependencies when the stdlib is sufficient.

The CLI surface is simple: two subcommands (`check` and `fix`) and three
options total. This is well within the scope of `argparse`.

## Decision

We migrated the CLI from Typer to stdlib `argparse`. The `typer` package was
removed from `dependencies` in `pyproject.toml`; the project now has no runtime
dependencies at all. The entry point was updated from `sheridan.iceberg.cli:app`
to `sheridan.iceberg.cli:main`.

## Consequences

- Runtime dependencies are now empty — install is as lean as possible.
- `argparse` is less ergonomic than Typer for larger CLIs, but is sufficient
  for this tool's two-subcommand surface and will remain so unless the CLI
  grows substantially.
- Type annotations on CLI handler functions are no longer verified by the
  framework itself; mypy still checks the handlers as regular functions.
- Pre-commit hook installs are faster and carry no third-party transitive deps.
- Future CLI additions must use `argparse` conventions rather than Typer's
  annotation-driven style.
