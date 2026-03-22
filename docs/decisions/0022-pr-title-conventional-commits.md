# 0022. Enforce Conventional Commits Format on PR Titles

Date: 2026-03-22
Status: Accepted

## Context

The project uses `commitizen` with `cz_conventional_commits` for local commit message enforcement, and `cz bump` runs on every push to `main` to determine the next version bump type by reading conventional commits. The repository uses squash merges — the PR title becomes the commit message on `main`. Without PR title enforcement, a contributor could open a PR with a freeform title, squash-merge it, and silently produce a non-conventional commit that `cz bump` cannot classify, creating a silent gap in version history.

## Decision

We decided to enforce conventional commits format on PR titles via a GitHub Actions workflow using `amannn/action-semantic-pull-request@v6`, pinned to a full commit SHA (supply chain hardening, following the lesson from CVE-2025-30066/tj-actions compromise). The action is the community standard for this use case and was vetted by the project's `dependency-auditor` agent. The workflow uses the `pull_request_target` trigger (required for fork PRs) and is scoped to `pull-requests: read` only. GitHub repo settings are configured separately by the author to require squash merge only and to require this status check before merging.

## Consequences

**Positive:**
- Every commit that lands on `main` via a PR is guaranteed to be a valid conventional commit — `cz bump` always has clean, parseable input.
- Contributors see an immediate, actionable failure on a malformed PR title before code review begins.
- Pinning to a full commit SHA hardens the workflow against compromised action tags.

**Negative:**
- `pull_request_target` carries elevated risk (it runs with write permissions on the base repo); the `pull-requests: read` scope minimises but does not eliminate this surface.
- Contributors unfamiliar with conventional commits must learn the format before their PR can pass; this adds friction for first-time contributors.
- Local pre-commit hooks remain the enforcement layer for direct commits to `main`; the PR title check covers only the squash-merge point.
