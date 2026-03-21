# 0010. Exclude .claude/worktrees from Ruff

Date: 2026-03-21
Status: Accepted

## Context

Claude Code agents run in git worktrees under `.claude/worktrees/`. These directories contain copies of source files. Ruff was picking them up during linting and producing spurious errors on files that are not part of the active codebase.

## Decision

We decided to add `.claude/worktrees` to ruff's `exclude` list in `pyproject.toml`. Agent worktrees are operational artifacts of the development workflow, not source to be linted.

## Consequences

- Ruff lints only the actual source tree. Stale worktrees from agent runs do not produce false lint failures.
- The exclusion must be updated if the worktree location changes.
