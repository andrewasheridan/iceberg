# Contributing to sheridan-iceberg

## Setup

```bash
git clone https://github.com/andrewasheridan/iceberg
cd iceberg
task install
uv run prek install
```

`uv run prek install` sets up the Git hooks from `.pre-commit-config.yaml`:

- **pre-commit**: file hygiene checks, `detect-private-key`, a block on committing to
  `main`, ruff (check and format), pyrefly on `src/` and `tests/`, and `no-banner-comments`.
- **commit-msg**: `cz check`, so commit messages follow Conventional Commits.
- **pre-push**: the test suite (`pytest`).

ruff, pyrefly, commitizen and pytest run through `uv run --frozen`, so the hooks use the
versions pinned in `uv.lock`. Run every pre-commit hook by hand with
`uv run prek run --all-files`.

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
2. Write code that follows the [docstring](#docstrings) and [comment](#comments) rules
3. Write tests (90% coverage minimum, set in `[tool.coverage.report]` in `pyproject.toml`)
4. Run `task check` — all gates must pass
5. Commit using conventional commits: `feat:`, `fix:`, `chore:`, etc.
6. Open a PR

## Issue loop and triage

`/sweep` reviews the code and files new issues, but changes no code. The maintainer
works the backlog with a local issue loop that is not tracked in this repo.

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

## Docstrings

Docstrings follow the Google convention, and the first line uses the imperative
mood. A docstring never starts with "Return" or "Returns": every function that
returns a value does that. Use a verb that says how the value is made, such as
*build*, *compute*, *find*, *collect*, *list*, *check*, *parse*, *render*,
*resolve*, *convert*, *load* or *get*.

```python
def snapshot(path: Path) -> Package:
    """Snapshot the public API rooted at path."""  # not "Return a snapshot of ..."
```

`tests/unit/test_docstring_style.py` enforces this in `src/` and `tests/`.

## Comments

Write a comment only when it says something the code can't: a reason, a constraint or
a non-obvious consequence. Don't use banner or section-divider comments (a line made
only of `#` and ten or more `-` or `=`, usually around a section title). To group code,
use a test class, a separate module or a docstring.
`tests/unit/test_comment_style.py` enforces this across the repo, and the
`no-banner-comments` prek hook catches it before you commit.

## Readability

Code is read far more often than it is written. When two ways work, pick the one that
is easier to read. Ruff decides the layout of each line, but not where a blank line
helps or when a comprehension is too clever; that is up to you.

The Zen of Python (`python -c "import this"`) is the guide. These lines matter most:

- Readability counts.
- Explicit is better than implicit.
- Simple is better than complex.
- Flat is better than nested.
- Sparse is better than dense.
- If the implementation is hard to explain, it's a bad idea.

Whitespace is your friend. Use blank lines to split a function into its logical steps
(setup, work, result) and to set off `if`, `for`, `with` and `try` blocks from the code
around them. Flatten deep nesting with early returns or guard clauses, and replace a
dense one-liner with a plain loop or a named intermediate value.

Before:

```python
def load(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    text = path.read_text()
    pairs = {k.strip(): v.strip() for k, _, v in (l.partition("=") for l in text.splitlines() if l and not l.startswith("#"))}
    for key in pairs:
        if not key.isidentifier():
            raise ValueError(key)
    return pairs
```

After:

```python
def load(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    pairs: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue

        key, _, value = line.partition("=")
        pairs[key.strip()] = value.strip()

    for key in pairs:
        if not key.isidentifier():
            raise ValueError(key)

    return pairs
```

This is guidance, not a lint rule; reviewers apply it.

## Running checks

```bash
task lint:check   # ruff check (read-only)
task lint         # ruff check --fix (autofix)
task format:check # ruff format --check (read-only)
task format       # ruff format (write)
task typecheck    # pyrefly check (src/ and tests/)
task test         # pytest (with coverage)
task iceberg      # iceberg src/ (dogfood — show public API)
task api:check    # fail if the public API differs from api.txt
task api:update   # rewrite api.txt from src/sheridan/
task sdist:check  # fail if the sdist ships files outside its include list
task check        # all gates (read-only: lint:check, format:check, …)
```

## Public API snapshot

`api.txt` is iceberg's own tree output for `src/sheridan/`. CI (the `iceberg` gate in
`task ci`) and `task check` fail when the current public API differs from it, and print
the diff. If the change is intended, run `task api:update` and commit `api.txt` with
your change, so that every API change shows up in review.

## Source distribution

The sdist ships only `src/`, `tests/`, `README.md`, `LICENSE`, `CHANGELOG.md` and
`pyproject.toml` (the `include` list in `[tool.hatch.build.targets.sdist]`); Hatch adds
`PKG-INFO` and `.gitignore`. CI (the `sdist` gate in `task ci`) and `task check` build
the sdist and fail when it has any other top-level entry. If you add a file that users
need in the sdist, add it to the `include` list and to both checks.

## Adding dependencies

**Propose the dependency first** in an issue, and wait for the maintainer to approve
it. Do not open PRs that add unapproved dependencies. After you change dependencies,
run `uv lock` and commit `uv.lock`.
