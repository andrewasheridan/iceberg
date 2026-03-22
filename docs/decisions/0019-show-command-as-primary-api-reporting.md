# 0019. `show` Command as Primary API Reporting Function

Date: 2026-03-22
Status: Accepted

## Context

The project's initial scope was issue-centric — the `check` command reported what was *wrong* with `__all__`. A reevaluation reframes the primary function as API *reporting*: showing what the public surface actually is. Checking for discrepancies and fixing them are secondary, optional concerns.

Downstream tools like `sheridan-diffract` need a reliable way to inspect the effective public API of any module, regardless of whether `__all__` is present or correct.

## Decision

We decided to add a `show` subcommand as the primary way to inspect public API surfaces.

`iceberg show PATH [--format tree|json] [--use-ast]` reports the effective public API for each module — using `__all__` when present (authoritative), falling back to AST inference when absent. The `--use-ast` flag forces AST-only reporting regardless of `__all__`. Output formats are `tree` (default, human-readable, indented hierarchy) and `json` (machine-readable array). Tree and JSON rendering use stdlib only — no new dependencies.

`show` does not exit with code 1 when `__all__` is absent or incorrect; it reports what is there without judgment.

## Consequences

**Positive:**
- `show` gives explorers and downstream tools a clear, judgment-free view of any module's public surface.
- `sheridan-diffract` can drive its API diffing from `show --format json` output directly.
- No new dependencies — stdlib handles both output formats.
- `check` and `fix` retain their roles for enforcement and repair without conflation.

**Negative:**
- The CLI now has three subcommands (`show`, `check`, `fix`); the entry point is slightly more complex to explain to new users.
- `show` must stay in sync with the AST walker and the authoritative/fallback logic as those evolve.
