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
   - Optionally bypass `__all__` and always use the AST (`--use-ast`)
3. **Report** the public API surface per module (`show` command — primary); includes function signatures (parameter names, types, defaults, return type) and class member surfaces (class variables, instance attributes, properties, classmethods, staticmethods, instance methods)
4. **Check** `__all__` against the AST — report names that appear public but are absent from `__all__` (IB002, one-directional), unsorted `__all__` (IB003), and optionally missing `__all__` (IB001) (`check` command — secondary)
5. **Fix** `__all__` in place, fully synchronising it with the AST in both directions (`fix` command — secondary)

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
- **`show` is the primary command**: `iceberg show` reports the effective public API. `check` and `fix` are secondary enforcement and repair tools. (ADR 0019)
- **`show` reports signatures and class members**: function signatures (params, types, defaults, return annotation) and class member surfaces (attributes, properties, methods) are included in `show` output so that `diffract` can detect breaking changes beyond name additions/removals. (ADR 0024)
- **IB002 is one-directional**: IB002 reports names the AST considers public that are absent from `__all__`. Phantom exports (in `__all__` but not in AST) are not flagged by `check` — `fix` removes them. (ADR 0020)
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
- **YAML files**: Always use the `.yaml` extension. Never `.yml`.

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
| `Zensical` + MkDocstrings | Documentation site |
| `CLAUDE.md` | Repo-specific context for Claude Code sessions |
| Devcontainer config | One-command dev environment |
| ADRs in `/docs/decisions/` | Architecture Decision Records — document the *why* |
| `CONTRIBUTING.md` + MIT LICENSE | Standard open source hygiene |
| README badge wall | CI status, coverage %, mutation score, license |
| `.yaml` extension | All YAML files use `.yaml`, never `.yml` (ADR 0021) |

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
| Doc generation | zensical build | Every push |
| Iceberg self-check | iceberg check src/ | Every push |
| Mutation testing | deferred — see ADR 0017 | N/A |
| PR title lint | amannn/action-semantic-pull-request (ADR 0022) | Every PR |
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
| `task docs` | `uv run zensical build` |
| `task docs-serve` | `uv run zensical serve` |

## Agent architecture

### Orchestration rules
- The main Claude Code session is the orchestrator. It analyzes the task,
  selects the appropriate agent, and delegates via the `Agent` tool.
- **Never invoke agents via bash commands.** Always use the `Agent` tool:
  `Agent(subagent_type="agent-name", description="...", prompt="...")`
- If no agent exists for a required task, **stop and raise an error** with a
  clear message describing what agent is needed and why. Do not improvise or
  generate a new agent on the fly. New agents are created deliberately.
- Agents live in `~/.claude/agents/` (global config). They are shared across
  all `sheridan.*` projects and are not checked into this repo.
- Agents inherit project conventions from this CLAUDE.md automatically. Agent
  system prompts should not restate conventions — only describe role-specific
  behavior.

### Agent roster

| Agent | Role |
|---|---|
| `orchestrator` | **Default agent.** Routes tasks to specialist subagents and loops until complete |
| `code-writer` | Writes implementation code from a spec or description |
| `test-writer` | Writes pytest tests for existing implementation |
| `docstring-writer` | Adds or fixes Google-style docstrings |
| `type-annotator` | Adds or fixes mypy-compliant type annotations |
| `reviewer` | Advisory code review — does not block, suggests improvements |
| `complexity-reducer` | Identifies overly complex code and proposes simpler alternatives |
| `dead-code-detector` | Finds unreachable or unused code |
| `adr-writer` | Writes ADRs to `/docs/decisions/` when architectural decisions are made |
| `changelog-writer` | Drafts changelog entries from conventional commits |
| `dependency-auditor` | Reviews proposed new dependencies before they are added |

Agent definitions live in `~/.claude/agents/` and are shared across all `sheridan.*` projects.

### Suggested orchestration flows

**Implementing a new feature:**
1. `code-writer` — implement
2. `docstring-writer` — document
3. `type-annotator` — annotate (if not already done by code-writer)
4. `test-writer` — test
5. `reviewer` — advisory review; produces a mandatory follow-up checklist
6. `adr-writer` — if the reviewer (or your judgment) flags an architectural decision was made
7. Update CLAUDE.md in the main session if API surface, CLI flags, commands, agent roster, or conventions changed
8. Update README.md in the main session if user-facing behaviour, install steps, or CLI usage changed

**Architectural decision:**
1. `adr-writer` — always record significant decisions, even small ones that future maintainers would ask "why?"

**Adding a dependency:**
1. `dependency-auditor` — review first
2. Only proceed if auditor approves

**Releasing:**
1. `changelog-writer` — draft changelog from commits

**After any user-facing change:**
1. `reviewer` — advisory review
2. Apply follow-up checklist: ADR, CLAUDE.md, README.md as needed

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
├── zensical.toml
├── .pre-commit-config.yaml
├── .pre-commit-hooks.yaml
├── .github/
│   └── workflows/
│       ├── ci.yaml
│       ├── bump.yaml
│       ├── publish.yaml
│       └── pr-title.yaml
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
│           ├── models.py
│           ├── enums.py
│           ├── reporter.py
│           ├── fixer.py
│           ├── api.py
│           └── cli.py
└── tests/
```

## Release pipeline
Tags and PyPI releases are fully automated through three chained workflows:

1. **`bump.yaml`** — triggers on every push to `main`. Commitizen determines if there are releasable commits, bumps `pyproject.toml`, opens a `chore/version-bump-X.Y.Z` PR, and auto-merges it (using `RELEASE_TOKEN` as `GH_TOKEN`).
2. **`tag-on-merge.yaml`** — triggers when a `chore/version-bump-*` PR is merged. Creates an annotated tag on the merge commit and pushes it using `RELEASE_TOKEN` (passed as `token:` to `actions/checkout` — see ADR 0023).
3. **`publish.yaml`** — triggers on `push: tags: "v*"`. Builds sdist/wheel and publishes to PyPI via OIDC trusted publishing (no API token needed).

**`RELEASE_TOKEN`** must be a GitHub PAT (classic `repo` scope, or fine-grained with `contents: write` + `pull-requests: write`) stored as a repository secret. An expired or missing PAT causes `tag-on-merge.yaml` to fail loudly at checkout rather than silently falling back to `GITHUB_TOKEN`.

**PAT checkout pattern** — any workflow that pushes a git ref and must trigger a downstream workflow must pass `token: ${{ secrets.RELEASE_TOKEN }}` directly to `actions/checkout`. Never use `git remote set-url` to inject credentials: the credential helper installed by checkout overrides URL-embedded credentials, causing the push to be attributed to `GITHUB_TOKEN`, which suppresses downstream triggers. (ADR 0023)

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
- Agent definitions live in `~/.claude/agents/` (global); not checked into this repo
- Agent conventions come from CLAUDE.md, not from agent system prompts
- `show` is the primary command — API reporting first, enforcement second (ADR 0019)
- IB002 is one-directional: AST→`__all__` only; `fix` uses full bidirectional comparison (ADR 0020)
- PAT-authenticated git pushes must use `token:` in `actions/checkout`, not `git remote set-url` (ADR 0023)
- `show` includes function signatures and class member surfaces to enable `diffract` to detect breaking changes beyond name additions/removals (ADR 0024)
