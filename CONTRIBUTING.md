# Contributing to sheridan-iceberg

## Setup

```bash
git clone https://github.com/sheridan/sheridan-iceberg
cd sheridan-iceberg
task install
pre-commit install
```

### CI pipeline (Dagger)

The CI pipeline runs inside containers via [Dagger](https://dagger.io). You need:

- [Dagger CLI](https://docs.dagger.io/install)
- [Podman](https://podman.io/get-started) (default) **or** Docker

After cloning, initialize the Dagger module once:

```bash
# macOS — start the Podman machine first
podman machine start

task ci-init   # generates ci/sdk/ (gitignored)
```

Then run the full pipeline locally at any time:

```bash
task ci

# Prefer Docker?
CONTAINER_RUNTIME=docker task ci
```

## Workflow

1. Create a branch: `git checkout -b feat/your-feature`
2. Write code following [code conventions](CLAUDE.md#code-conventions)
3. Write tests (90% coverage minimum)
4. Run `task check` — all gates must pass
5. Commit using conventional commits: `feat:`, `fix:`, `chore:`, etc.
6. Open a PR

## Issue loop and triage

`scripts/issue-loop.sh` works the issue backlog with headless Claude Code sessions:
`/next-issue` turns one issue into an auto-merging PR. Run
`scripts/issue-loop.sh --help` for the options.

The loop also runs **sweeps** (`/sweep`): a session that reviews the code and files
new issues, but changes no code. A sweep runs after every `SWEEP_EVERY` merged issues
(default 5) and once when the backlog is empty. `--sweep` runs only a sweep;
`--no-sweep` turns sweeps off. One sweep files at most `SWEEP_MAX_ISSUES` issues
(default 3).

Every issue a sweep files has the `needs triage` label and the line "Found by an
automated sweep." The loop never works on an issue with `needs triage`. To let the
loop take one:

1. Read it, and close it as "not planned" if it is wrong or not worth doing.
2. Check its `type:` and `priority:` labels.
3. Remove `needs triage`.

## Commit format

This repo uses [Commitizen](https://commitizen-tools.github.io/commitizen/) to
enforce conventional commits. Run `cz commit` instead of `git commit` for
interactive prompting.

```
feat: add JSON output format
fix: handle modules with no top-level names
chore: bump ruff to 0.5
docs: add pre-commit hook example
```

## Running checks

```bash
task lint:check   # ruff check (read-only)
task lint         # ruff check --fix (autofix)
task format:check # ruff format --check (read-only)
task format       # ruff format (write)
task typecheck    # mypy --strict
task test         # pytest --cov
task iceberg      # iceberg src/ (dogfood — show public API)
task check        # all gates (read-only: lint:check, format:check, …)
```

## Adding dependencies

Per the project conventions, **propose the dependency first**. The
`dependency-auditor` agent reviews all new dependencies before they are added.
Do not open PRs that add unapproved dependencies.
