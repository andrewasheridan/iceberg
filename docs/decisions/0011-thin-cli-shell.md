# 0011. Thin CLI Shell

Date: 2026-03-21
Status: Accepted

## Context

The original `cli.py` contained `_load_modules()` (path-to-modules dispatch) and the check/fix orchestration logic inline in private `_check()` and `_fix()` handlers. This made the logic inaccessible to programmatic callers. The planned sibling tool `sheridan-diffract` needs to compose iceberg's API surface extraction without invoking the CLI.

## Decision

We decided to keep `cli.py` as a thin shell responsible only for argument parsing, output formatting, and exit codes. All reusable logic was moved to library modules:

- `load_modules(path: Path) -> list[ModuleInfo]` added to `ast_walker.py` — handles file-or-directory dispatch
- `check_modules(modules: list[ModuleInfo]) -> list[Issue]` added to `reporter.py` — pure issue detection with no I/O
- Both functions exported from `sheridan.iceberg.__init__`

`cli.py` now calls these public functions. Check and fix coordination that is inherently CLI-specific (I/O, path validation, exit codes) remains in the CLI.

This is a standing convention for all `sheridan.*` tools: the CLI is a user-facing shell over a programmatic library API.

## Consequences

- Downstream tools and scripts can use `load_modules` + `check_modules` + `fix_module` without invoking the CLI. `sheridan-diffract` can compose directly against the library API.
- The public API surface of `sheridan.iceberg` is now explicit and testable independently of CLI concerns.
- New logic added to iceberg must be placed in library modules first; the CLI calls the library, not the reverse.
