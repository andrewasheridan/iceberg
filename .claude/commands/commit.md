---
description: Run checks, draft a conventional commit message, and commit staged changes
allowed-tools: Bash
---

Run the full check suite, inspect staged changes, draft a conventional commit message, and create the commit.

## Steps

1. **Run checks first** — Execute `task check` from the project root. If any step fails (lint, format, typecheck, tests, or iceberg self-check), stop immediately and report which check failed with the relevant error output. Do NOT proceed to commit.

2. **Inspect changes** — Run:
   - `git status` — to see staged and unstaged files
   - `git diff --staged` — to see exactly what will be committed
   - `git log --oneline -5` — to understand recent commit style

3. **Draft commit message** — Write a conventional commit message:
   - Format: `type(scope): summary` (scope is optional)
   - Types: `feat` (new feature), `fix` (bug fix), `chore` (maintenance), `refactor` (code change, no feature/fix), `docs` (documentation), `test` (tests only), `perf` (performance)
   - Summary: imperative mood, present tense, ≤72 chars, no period at end
   - If breaking change: append `!` after type, e.g. `feat!: rename show flags`
   - Body (optional): brief explanation of *why*, not *what*

4. **Show the plan** — Display:
   - Files that will be committed
   - The proposed commit message

5. **Commit** — Create the commit with the drafted message. Do NOT push.

If there are unstaged changes in files that are clearly part of the same change as what's staged, ask the user whether to stage them too before committing.
