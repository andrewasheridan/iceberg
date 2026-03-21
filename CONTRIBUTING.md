# Contributing to sheridan-iceberg

## Setup

```bash
git clone https://github.com/sheridan/sheridan-iceberg
cd sheridan-iceberg
task install
pre-commit install
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
task lint        # ruff check
task format      # ruff format
task typecheck   # mypy --strict
task test        # pytest --cov
task check       # all of the above
```

## Adding dependencies

Per the project conventions, **propose the dependency first**. The
`dependency-auditor` agent reviews all new dependencies before they are added.
Do not open PRs that add unapproved dependencies.

## Architecture Decision Records

Significant decisions are recorded as ADRs in `docs/decisions/`. Use the
`adr-writer` agent or follow the template in that directory.
