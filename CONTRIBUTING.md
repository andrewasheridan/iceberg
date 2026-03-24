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

After cloning, initialise the Dagger module once:

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

## Architecture Decision Records

Significant decisions are recorded as ADRs in `docs/decisions/`. Use the
`adr-writer` agent or follow the template in that directory.
