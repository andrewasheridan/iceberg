# 0005. Taskfile Task Runner

Date: 2026-03-21
Status: Accepted

## Context

Python projects commonly use `make` as a task runner, but `make` is a build tool with Makefile syntax that is error-prone, tab-sensitive, and not natively available on Windows. Alternatives like `just` offer cleaner syntax but require a separate binary with less ecosystem momentum. A standard, cross-platform task runner was needed for all `sheridan.*` repos that integrates cleanly with `uv` and CI pipelines.

## Decision

All `sheridan.*` repos use `task` (Taskfile) as the task runner. The task file is named `Taskfile.yaml` (`.yaml` extension preferred over `.yml` throughout the project).

The following standard tasks are defined in every repo:

| Task | Purpose |
|---|---|
| `install` | `uv sync --all-extras --dev` |
| `lint` | `uv run ruff check .` |
| `format` | `uv run ruff format .` |
| `typecheck` | `uv run mypy --strict .` |
| `test` | `uv run pytest --cov` |
| `check` | lint + format + typecheck + test |
| `mutmut` | incremental mutation test run |
| `docs` | `uv run mkdocs build` |
| `docs-serve` | `uv run mkdocs serve` |

`make` and `just` are not used in any `sheridan.*` repo.

## Consequences

- Developers need `task` installed locally. It is available via `brew`, `winget`, `scoop`, and direct binary download, making it genuinely cross-platform.
- CI pipelines install `task` as a setup step before running checks.
- The standard task names provide a consistent interface across all `sheridan.*` repos — contributors only need to learn one set of commands.
- `Taskfile.yaml` lives at the repo root and is the single source of truth for how to run all development workflows.
