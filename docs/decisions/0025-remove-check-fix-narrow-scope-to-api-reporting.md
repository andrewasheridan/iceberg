# 0025. Remove `check` and `fix` Commands; Narrow Scope to API Reporting

Date: 2026-03-23
Status: Accepted

## Context

`iceberg` originally offered three commands:
- `show`: report the effective public API surface of Python modules
- `check`: enforce `__all__` correctness via error codes (IB001 missing `__all__`, IB002 names in AST but not `__all__`, IB003 unsorted `__all__`)
- `fix`: auto-repair `__all__` in place to match the AST

`check` and `fix` are enforcement and linting behaviors — they gate on non-zero exit codes and modify source files. These responsibilities belong in a purpose-built linting tool (a future `sheridan-enforce` or similar), not in a reporting library.

`sheridan-iceberg`'s core strength is static analysis of Python code to determine the effective public API surface. Reporting that surface is its natural function. Enforcement should live elsewhere.

`sheridan-diffract`, the sibling tool that diffs public API surfaces across git commits to infer semantic version bump types, depends only on `get_public_api()` — the library function. It is unaffected by removing `check` and `fix`.

## Decision

We decided to remove the `check` and `fix` commands entirely, flattening the CLI to a single-purpose reporter. The new interface is:

```bash
iceberg src/               # report public API
iceberg --format json src/ # JSON output
```

The `show` subcommand prefix is dropped. This aligns `iceberg` with other Python tools (`mypy src/`, `ruff src/`).

Library API changes:
- `check_api()` and `fix_api()` are removed from `sheridan.iceberg`
- Only `get_public_api()` remains as the public library function

CLI changes:
- `iceberg show <path>` becomes `iceberg <path>`
- Exit code is always 0 (cannot gate commits — `iceberg` never fails)
- `.pre-commit-hooks.yaml` is removed (no entry point to hook into; no error exit codes)

## Alternatives Considered

1. **Keep `check` and `fix` alongside `show`** — rejected because enforcement is a different responsibility. Bundling them muddles the tool's purpose and forces users who only want reporting to accept linting behavior.

2. **Move `check` and `fix` to a separate CLI tool, re-export library functions** — rejected because `sheridan-enforce` (or equivalent) can be built later with its own domain-specific logic, and iceberg's public API surface should reflect its actual scope.

3. **Deprecate `check` and `fix` with a transition period** — rejected because the project is still at 1.x and a clean break is preferable to carrying deprecated code. Users relying on `iceberg check` will migrate to a future tool.

## Consequences

**Positive:**
- `iceberg` has a single, focused responsibility: inspect Python modules and report their effective public API surface.
- Simpler CLI (no subcommand dispatch; tools that integrate `iceberg` have one code path to maintain).
- Smaller codebase: `reporter.py`, `fixer.py`, `Issue` model, `IssueKind` enum, and `OutputFormat` enum are removed.
- Clearer semantics: no exit codes to interpret, no file mutations to account for.

**Negative:**
- Breaking change to both the public Python API (`check_api`, `fix_api` removed) and the CLI.
- Users relying on `iceberg check` or `iceberg fix` must migrate to a future enforcement tool once available.
- The `.pre-commit-hooks.yaml` pre-commit hook entry is gone. Projects using `iceberg` as a pre-commit hook will need a different solution until `sheridan-enforce` exists.
