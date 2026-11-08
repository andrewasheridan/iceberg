---
name: next-issue
description: Take one backlog issue from GitHub to an auto-merging PR — branch, implement, check, commit, open the PR, enable auto-merge. Use when asked to "work on the next issue" or "/next-issue [N]".
argument-hint: "[issue number]"
---

# /next-issue — one issue, one PR

Do exactly one issue and open exactly one PR. This skill also runs headless from
`scripts/issue-loop.sh`, so never stop to ask a question: if you cannot continue,
end with a `BLOCKED:` line (see "Final line").

## 1. Choose the issue

- If an issue number was given (`$ARGUMENTS`), use it.
- Otherwise run `scripts/next-issue.sh` and use the number it prints. If it prints
  nothing, end with `BLOCKED: no eligible issues left`.

Read the issue and its comments: `gh issue view N --comments`. If it is an epic, needs
a decision from the maintainer, or depends on an open issue that is not done yet, end
with `BLOCKED: <reason>`.

## 2. Branch

The working tree must be clean. If it is not, end with `BLOCKED: working tree is dirty`.

```bash
git switch main && git pull --ff-only
git switch -c <type>/<N>-<short-slug>
```

`<type>` is the Conventional Commit type that matches the issue's `type:` label
(`fix` for `type: bug`, `feat` for `type: feature`, otherwise the same word: `docs`,
`refactor`, `test`, `build`, `perf`, `chore`, `ci`).

## 3. Implement

- Do only what the issue asks. Meet every item in its acceptance checklist.
- For a bug, first write a test that reproduces it and fails, then fix it.
- Update the docs, the case READMEs and the golden tests when behavior that users can
  see changes.
- Do not edit `CHANGELOG.md`. The release process generates it.
- Run mypy on `src/` only (`task typecheck`) until #95 is done.
- After you change dependencies, run `uv lock`.

## 4. Check

Run `task check`. It must pass. Fix the failures. If you cannot make it pass in a
reasonable number of tries, end with `BLOCKED: task check fails: <summary>` and do not
push.

## 5. Commit and open the PR

- Make one commit with a Conventional Commit message: `<type>: <summary>` (add `!` and
  a `BREAKING CHANGE:` footer when the issue has the `breaking change` label). The
  body explains why. End the body with `Closes #N`, then the co-author trailer from
  your instructions.
- `git push -u origin HEAD`
- Open the PR. The title is the same as the commit subject (CI lints it). The body
  starts with `Closes #N`, then a short summary and how you tested it. Copy the
  issue's `type:`, `priority:` and `breaking change` labels:

  ```bash
  gh pr create --title "<subject>" --body-file <file> --label "type: ..." --label "priority: ..."
  ```

- Enable auto-merge: `gh pr merge <PR> --auto --squash`. It merges only after the
  required checks pass.

## Final line

The last line of your reply must be exactly one of these:

```
PR: <pr url>
BLOCKED: <one-line reason>
```

`scripts/issue-loop.sh` reads this line to decide what to do next.
