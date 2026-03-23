---
description: Run task check and report CI-equivalent status
allowed-tools: Bash
---

Run the full check suite and report pass/fail per step.

## Steps

1. Run `task check` from `/home/user/iceberg/`:
   ```
   task check
   ```
   This runs: `lint:check` + `format:check` + `typecheck` + `test` + `iceberg`

2. Parse the output and report status for each check:

   | Check | Tool | Status |
   |---|---|---|
   | Lint | `ruff check` | ✓ / ✗ |
   | Format | `ruff format --check` | ✓ / ✗ |
   | Type check | `mypy --strict` | ✓ / ✗ |
   | Tests + coverage | `pytest --cov` | ✓ / ✗ |
   | Iceberg self-check | `iceberg check src/` | ✓ / ✗ |

3. For any failing check, show the relevant error lines and suggest the fix command:
   - Lint failures → `task lint` (auto-fixes ruff issues)
   - Format failures → `task format` (auto-fixes formatting)
   - Type failures → inspect the mypy error, fix manually
   - Test failures → show failing test names and error messages
   - Iceberg failures → `task iceberg` output to understand missing `__all__` entries

4. If all checks pass: report **"All checks passed ✓"**
