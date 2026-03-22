# 0023. Pass PAT to actions/checkout to Authenticate Tag Pushes

Date: 2026-03-22
Status: Accepted

## Context

The release pipeline chains three workflows: `bump.yaml` (commitizen bump + auto-merge PR), `tag-on-merge.yaml` (creates and pushes an annotated tag on the merge commit), and `publish.yaml` (triggered by `push: tags: "v*"`, publishes to PyPI via OIDC trusted publishing).

`tag-on-merge.yaml` was using `actions/checkout@v4` without a `token:` override, then injecting the `RELEASE_TOKEN` PAT via `git remote set-url`. This approach is defeated by the credential helper that `actions/checkout` installs: when `git push` runs, the helper intercepts authentication and provides `GITHUB_TOKEN` credentials, ignoring the PAT embedded in the remote URL. Tags were created successfully (because `GITHUB_TOKEN` had `contents: write`), but GitHub attributes them to `GITHUB_TOKEN` and suppresses downstream `push.tags` triggers as anti-loop protection. `publish.yaml` was never fired.

## Decision

We decided to pass `token: ${{ secrets.RELEASE_TOKEN }}` directly to `actions/checkout@v4`. This wires the credential helper to the PAT at setup time, so all subsequent git operations — including `git push` — are authenticated as the PAT owner. The `git remote set-url` workaround is removed entirely.

## Consequences

**Positive:**
- Tag pushes are attributed to the PAT owner; GitHub fires the `push.tags` event and `publish.yaml` is triggered as intended.
- Failure is loud: an expired or missing PAT causes the checkout step to fail immediately, rather than silently falling back to `GITHUB_TOKEN`.
- Removes the `git remote set-url` anti-pattern, which operates at the wrong layer for this use case.

**Negative:**
- `RELEASE_TOKEN` must be a valid PAT (classic `repo` scope, or fine-grained with `contents: write` on this repo) stored as a repository secret; the pipeline is inoperable without it.
- This pattern must be applied consistently to any workflow in this repo (or other `sheridan.*` repos) where a PAT-authenticated git push must trigger a downstream workflow — it is easy to regress by omitting the `token:` field.
