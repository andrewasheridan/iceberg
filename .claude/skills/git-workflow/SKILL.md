---
name: git-workflow
description: Git, GitHub and release workflow for iceberg - Conventional Commits checked by commitizen, branch names, pull requests with the gh CLI, merge approval, and the automatic version bump and PyPI release. Use when you create a branch, write a commit message, commit, push, open or update a pull request, or ask about a release.
---

# Git workflow

## Flow

Each change follows this sequence:

1. **Issue.** Each PR closes one issue. If the work has no issue, create one first.
2. **Branch** from an up-to-date `main`. Use the issue number in the name.
3. **Commits** in Conventional Commits format.
4. **PR** that links the issue, has labels, and passes the checks.
5. **Squash merge.** The merge closes the issue.
6. **Release.** The workflows bump the version and publish to PyPI.

## Issues

- To create an issue, use `gh issue create --template <bug.yml|feature.yml|task.yml>`.
  If you write the content yourself, use `--title`, `--body` and `--label`. The
  templates are in `.github/ISSUE_TEMPLATE/`.
- Title: a short statement in STE, not in commit format. Example: `JSON output drops
  the module docstring`.
- Body: the problem, and the acceptance criteria as a checklist.
- Labels (`scripts/sync-labels.sh` defines them):
  - Exactly one `type:` label: `feature`, `bug`, `docs`, `refactor`, `test`, `perf`,
    `build`, `ci`, `chore`.
  - Exactly one `priority:` label: `high`, `medium`, `low`.
  - `needs triage` on each issue that a sweep opens. The issue loop skips these issues
    until the maintainer removes the label.
  - `blocked` or `breaking change` when they apply.
- If the priority is not clear, ask the user.

## Branches

- `main` is always ready for a release. Do not commit directly to `main`. The
  `no-commit-to-branch` prek hook stops it.
- Name: `<type>/<issue-number>-<short-kebab-description>`, for example
  `feat/12-json-output` or `fix/31-empty-init-crash`. `<type>` is a commit type from
  the list below. `fix` is the type for the `type: bug` label.
- Do not use the `chore/version-bump-` prefix. The release workflows use it.

## Commit messages

Commitizen (`cz_conventional_commits`) checks each commit message. Format:

```
<type>(<optional scope>)<optional !>: <description>

<optional body>

<optional footer(s)>
```

| Type | Use for |
|---|---|
| `feat` | A new feature for the user |
| `fix` | A bug fix for the user |
| `docs` | Documentation only |
| `style` | Format only, no change in behavior |
| `refactor` | A code change that is not a fix and not a feature |
| `perf` | A performance improvement |
| `test` | Add or correct tests |
| `build` | The build system or dependencies (`pyproject.toml`, `uv.lock`) |
| `ci` | CI configuration |
| `chore` | Other maintenance that does not change `src/` or `tests/` |
| `revert` | Revert an earlier commit |

Rules:

- Description: imperative mood, lower case first letter, no period at the end. The full
  header line has 72 characters or fewer. Example: `fix(cli): reject empty file names`.
- The scope is optional. If you use one, it is a noun for a part of the code, for
  example `cli` or `formatter`.
- Breaking change: put `!` before the colon. Add the footer
  `BREAKING CHANGE: <what changed and what users must do>`.
- Body: tell why the change is necessary and what it changes. Do not repeat the diff.
  Wrap at 72 characters. Write the body in STE (see the `ste100` skill).
- Footers: `Closes #12`, `Co-Authored-By: ...`.
- Make one logical change in each commit.
- The commitizen `commit-msg` hook rejects a header that is not in this format. Do not
  use `--no-verify`.
- Do not edit `CHANGELOG.md`. The release process makes it.

## Before you commit

1. Make sure that the prek hooks are installed: `uv run prek install` (once for each
   clone).
2. Run `task check` (see the `python-dev` skill). If a check fails, do not commit.
3. Look at `git status` and `git diff --staged`. Stage only the files of this change.
   Do not stage secrets, `.env` files or generated files.
4. Commit only when the user tells you to commit.
5. If a hook changes files (for example `ruff format`), the commit stops. Look at the
   changes, stage them, and commit again.

## Pull requests

1. Push the branch: `git push -u origin HEAD`.
2. Open the PR:

   ```bash
   gh pr create --base main --title "<type>(<scope>): <description>" \
     --label "type: <type>" --label "priority: <level>" --body-file <file>
   ```

- Title: the same format as a commit header. The squash merge uses this title as the
  commit on `main`. The `pr-title` workflow checks it.
- Labels: the same `type:` and `priority:` labels as the issue.
- Body: fill in `.github/pull_request_template.md`. The first line is
  `Closes #<issue>`. Write the summary in STE.

## Merge approval

The user is the only approver.

- In an interactive session, do not merge a PR unless the user approves that PR in the
  current conversation. The approval of one PR does not apply to a different PR.
- Do not use `--admin`.
- Do not push to `main` and do not force-push. `.claude/settings.json` stops these
  commands.
- In an interactive session, the `ask-before-merge.sh` hook asks the user before each
  `gh pr merge` command.
- The headless issue loop (`/next-issue`) uses `gh pr merge --auto --squash`. GitHub
  merges the PR only after the required checks pass.
- After the merge: `git switch main && git pull --ff-only`.

## Release

The release is automatic. Do not bump the version or make tags by hand.

1. A merge to `main` starts `.github/workflows/bump.yaml`. It runs `cz bump`, which
   sets the version from the commit types and updates `CHANGELOG.md` and `uv.lock`.
2. The workflow opens a `chore/version-bump-<version>` PR (`bump: <version>`) and
   enables auto-merge.
3. When that PR merges, `tag-on-merge.yaml` tags the merge commit `v<version>`.
4. The tag starts `publish.yaml`, which builds the package and publishes it to PyPI.

A `fix` commit gives a patch release. A `feat` commit gives a minor release. A breaking
change gives a major release.
