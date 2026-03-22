# sheridan-iceberg

## What this is
`sheridan-iceberg` is a Python developer tool that analyzes Python modules and
enforces the presence and correctness of `__all__`. It is the foundation of the
`sheridan.*` developer toolchain.

## The iceberg metaphor
The public API is the tip of the iceberg — the small visible surface above the
waterline. Everything below is private implementation detail. `iceberg` guards
that waterline by making `__all__` explicit and correct in every module.

## What it does
1. Walk a Python project's modules using the `ast` module (no importing user code)
2. For each module, determine the public API surface:
   - Use `__all__` if present (authoritative)
   - Fall back to inferring non-underscore top-level names if absent
3. Report missing, incorrect, or unsorted `__all__` declarations
4. Optionally auto-fix by writing the correct `__all__` to each module

## Relationship to sheridan-diffract
`iceberg` is a dependency of `sheridan-diffract`, a sibling tool that diffs the
public API surface across git commits to infer semantic version bump types
(`fix`, `feat`, `feat!`). Build `iceberg` first — `diffract` builds on top of
its API surface extraction logic.

## The sheridan.* namespace
This package lives under the `sheridan` namespace package. Other tools in this
family follow the same conventions:
- Whimsical but meaningful names
- Clean CLIs
- Designed to compose with pre-commit, GitHub Actions, and CI pipelines
- Consistent tooling across all repos (see Tooling Conventions below)

## Design principles
- Use Python's `ast` module for static analysis — no importing user code
- `__all__` is the authoritative source of public API when present
- Fall back to AST inference (non-underscore top-level names) when absent
- Output should be machine-readable (JSON) and human-readable (text)
- Must work as a pre-commit hook, a CLI tool, and optionally a GitHub Action
- **CLI is a thin shell**: `cli.py` handles argument parsing, output formatting,
  and exit codes only. All reusable logic lives in library modules and is
  accessible programmatically. This applies to all `sheridan.*` tools. (ADR 0011)
- **`__all__` at the top**: `__all__` is declared immediately after the module
  docstring (and any shebang/comments), before all imports. It is the first
  executable statement in every module. iceberg does not enforce this position —
  it is a project style convention. (ADR 0012)

## Code conventions
These apply to all code written in this repo. Agents inherit these via CLAUDE.md
and should not restate them in their own system prompts.

- **Language**: Python 3.14+
- **Types**: All code must pass `mypy --strict`. No untyped functions.
- **Formatting/linting**: `ruff`. Never suggest changes that would fail ruff.
- **Docstrings**: Google style. All public functions, classes, and methods.
- **Tests**: `pytest`. Written after implementation. 90% coverage minimum.
- **Imports**: Absolute imports only. No relative imports.
- **Dependencies**: Propose before adding. Run past `dependency-auditor` agent.

## Tooling conventions
These apply across all `sheridan.*` repos. Do not deviate without good reason.

| Tool | Purpose |
|---|---|
| `uv` | Dependency management and Python version management |
| `pyproject.toml` | Single config file for all tools — ruff, mypy, pytest, coverage, commitizen |
| `ruff` | Lint and formatting |
| `mypy --strict` | Type checking |
| `pytest` + `pytest-cov` | Tests, 90% coverage minimum |
| `pre-commit` | Local hooks: ruff, mypy, iceberg before push |
| `commitizen` | Enforces conventional commits (`feat:`, `fix:`, `chore:`) |
| `Taskfile.yaml` | Task runner. Never use `make`. Use `task <name>` |
| `MkDocs` + Material + MkDocstrings | Documentation site |
| `CLAUDE.md` | Repo-specific context for Claude Code sessions |
| Devcontainer config | One-command dev environment |
| ADRs in `/docs/decisions/` | Architecture Decision Records — document the *why* |
| `CONTRIBUTING.md` + MIT LICENSE | Standard open source hygiene |
| README badge wall | CI status, coverage %, mutation score, license |

## Mutation testing strategy
Mutation testing is currently deferred — see ADR 0017. Both mutmut 2.x and 3.x
are incompatible with Python 3.14. Revisit when mutmut ships a fix for
https://github.com/boxed/mutmut/issues/466.

## CI pipeline
All checks run in parallel inside containers via [Dagger](https://dagger.io) (ADR 0018).
Podman is the default local runtime; Docker is supported via `CONTAINER_RUNTIME=docker`.

```bash
podman machine start  # macOS — start runtime once
task ci-init          # first-time setup: generates ci/sdk/ (run once after clone)
task ci               # run full pipeline locally
CONTAINER_RUNTIME=docker task ci  # use Docker instead
```

GitHub Actions runs the same pipeline via `dagger/dagger-action@v3` (Docker default on runners).

| Check | Tool | Gate |
|---|---|---|
| Lint | ruff check | Every push |
| Format | ruff format --check | Every push |
| Type check | mypy --strict | Every push |
| Tests + coverage | pytest --cov (90% min) | Every push |
| Security lint | bandit | Every push |
| Doc generation | mkdocs build | Every push |
| Iceberg self-check | iceberg check src/ | Every push |
| Mutation testing | deferred — see ADR 0017 | N/A |
| Dependency updates | Renovate | Automated PRs |
| Secret scanning | GitHub native | Always on |

## Standard Taskfile tasks
Every `sheridan.*` repo should expose these tasks.
Tasks that mutate files use bare names (`lint`, `format`).
Read-only / check variants are namespaced with a colon (`lint:check`, `format:check`).

| Task | Command |
|---|---|
| `task install` | `uv sync --all-extras --dev` |
| `task lint` | `uv run ruff check --fix .` |
| `task lint:check` | `uv run ruff check .` (read-only) |
| `task format` | `uv run ruff format .` |
| `task format:check` | `uv run ruff format --check .` (read-only) |
| `task typecheck` | `uv run mypy --strict .` |
| `task test` | `uv run pytest --cov` |
| `task iceberg` | `uv run iceberg check src/` (dogfood self-check) |
| `task check` | `lint:check` + `format:check` + `typecheck` + `test` + `iceberg` |
| `task ci-init` | `dagger develop` (run once after clone) |
| `task ci` | `dagger call check --source=.` |
| `task docs` | `uv run mkdocs build` |
| `task docs-serve` | `uv run mkdocs serve` |

## Agent architecture

### Orchestration rules
- The main Claude Code session is the orchestrator. It analyzes the task,
  selects the appropriate agent, and delegates via the `Agent` tool.
- **Never invoke agents via bash commands.** Always use the `Agent` tool:
  `Agent(subagent_type="agent-name", description="...", prompt="...")`
- If no agent exists for a required task, **stop and raise an error** with a
  clear message describing what agent is needed and why. Do not improvise or
  generate a new agent on the fly. New agents are created deliberately.
- Agents live in `.claude/agents/`. Do not look for them in `.github/agents/`
  or anywhere else.
- Agents inherit project conventions from this CLAUDE.md automatically. Agent
  system prompts should not restate conventions — only describe role-specific
  behavior.

### Agent roster

| Agent | File | Role |
|---|---|---|
| `code-writer` | `.claude/agents/code-writer.md` | Writes implementation code from a spec or description |
| `test-writer` | `.claude/agents/test-writer.md` | Writes pytest tests for existing implementation |
| `docstring-writer` | `.claude/agents/docstring-writer.md` | Adds or fixes Google-style docstrings |
| `type-annotator` | `.claude/agents/type-annotator.md` | Adds or fixes mypy-compliant type annotations |
| `reviewer` | `.claude/agents/reviewer.md` | Advisory code review — does not block, suggests improvements |
| `complexity-reducer` | `.claude/agents/complexity-reducer.md` | Identifies overly complex code and proposes simpler alternatives |
| `dead-code-detector` | `.claude/agents/dead-code-detector.md` | Finds unreachable or unused code |
| `mutation-analyzer` | `.claude/agents/mutation-analyzer.md` | Interprets mutmut results and suggests fixes for surviving mutants |
| `adr-writer` | `.claude/agents/adr-writer.md` | Writes ADRs to `/docs/decisions/` when architectural decisions are made |
| `changelog-writer` | `.claude/agents/changelog-writer.md` | Drafts changelog entries from conventional commits |
| `dependency-auditor` | `.claude/agents/dependency-auditor.md` | Reviews proposed new dependencies before they are added |

### Suggested orchestration flows

**Implementing a new feature:**
1. `code-writer` — implement
2. `docstring-writer` — document
3. `type-annotator` — annotate (if not already done by code-writer)
4. `test-writer` — test
5. `reviewer` — advisory review

**Architectural decision:**
1. Make the decision in the main session
2. `adr-writer` — record it

**Adding a dependency:**
1. `dependency-auditor` — review first
2. Only proceed if auditor approves

**Releasing:**
1. `changelog-writer` — draft changelog from commits

## Project structure (intended)
```
sheridan-iceberg/
├── CLAUDE.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── Taskfile.yaml
├── dagger.json
├── pyproject.toml
├── .pre-commit-config.yaml
├── .pre-commit-hooks.yaml
├── .github/
│   └── workflows/
│       └── ci.yml
├── .claude/
│   └── agents/
│       ├── code-writer.md
│       ├── test-writer.md
│       ├── docstring-writer.md
│       ├── type-annotator.md
│       ├── reviewer.md
│       ├── complexity-reducer.md
│       ├── dead-code-detector.md
│       ├── mutation-analyzer.md
│       ├── adr-writer.md
│       ├── changelog-writer.md
│       └── dependency-auditor.md
├── ci/
│   ├── pyproject.toml
│   └── src/main/
│       └── __init__.py   # Dagger pipeline (SheridanIcebergCi)
├── docs/
│   └── decisions/
├── src/
│   └── sheridan/
│       └── iceberg/
│           ├── __init__.py
│           ├── ast_walker.py
│           ├── reporter.py
│           ├── fixer.py
│           └── cli.py
└── tests/
```

## Key decisions already made
- Namespace: `sheridan`
- Package name: `sheridan-iceberg` (import as `sheridan.iceberg`)
- Static analysis only — no exec or import of user code
- `__all__` is authoritative; AST inference is the fallback
- `iceberg` has no git awareness — that belongs to `diffract`
- Task runner: `task` (Taskfile.yaml) — never `make` or `just`
- Task naming: mutating tasks use bare names (`lint`, `format`); read-only variants use colon namespacing (`lint:check`, `format:check`)
- CI engine: Dagger with Podman default, Docker optional via `CONTAINER_RUNTIME=docker` (ADR 0018)
- Agents are curated, not generated — missing agent = stop with error
- Agent conventions come from CLAUDE.md, not from agent system prompts
