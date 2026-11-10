# How to contribute to sheridan-iceberg

## Setup

```bash
git clone https://github.com/andrewasheridan/iceberg
cd iceberg
task install
uv run prek install
```

`uv run prek install` installs the Git hooks from `.pre-commit-config.yaml`:

- **pre-commit**: file hygiene checks, `detect-private-key`, a block on commits to
  `main`, ruff (check and format), pyrefly on `src/` and `tests/`, and
  `no-banner-comments`.
- **commit-msg**: `cz check`. This hook makes sure that commit messages obey
  Conventional Commits.
- **pre-push**: the test suite (`pytest`).

The hooks run ruff, pyrefly, commitizen and pytest through `uv run --frozen`. Thus,
the hooks use the versions in `uv.lock`. To run all the pre-commit hooks manually,
run `uv run prek run --all-files`.

### CI pipeline (Dagger)

The CI pipeline runs in containers through [Dagger](https://dagger.io). You must
have these tools:

- [Dagger CLI](https://docs.dagger.io/install)
- [Podman](https://podman.io/get-started) (default) **or** Docker

After you clone the repo, initialize the Dagger module one time:

```bash
# macOS — start the Podman machine first
podman machine start

task ci-init   # generates ci/sdk/ (gitignored)
```

Then you can run the full pipeline locally at any time:

```bash
task ci

# Prefer Docker?
CONTAINER_RUNTIME=docker task ci
```

## Workflow

1. Create a branch: `git checkout -b feat/your-feature`
2. Write code that obeys the [docstring](#docstrings) and [comment](#comments) rules.
3. Write tests. The minimum coverage is 90%. `[tool.coverage.report]` in
   `pyproject.toml` sets this value.
4. Run `task check`. All the gates must pass.
5. Commit with a Conventional Commit message: `feat:`, `fix:`, `chore:` and so on.
6. Open a PR.

## Issue loop and triage

`/sweep` reviews the code and opens new issues. It does not change code. The
maintainer works through the backlog with a local issue loop. This repo does not
track the issue loop.

Each issue that a sweep opens has the `needs triage` label and the line "Found by an
automated sweep." The loop never works on an issue that has `needs triage`. To let
the loop work on an issue, do these steps:

1. Read the issue. If it is wrong or not worth the work, close it as "not planned".
2. Examine its `type:` and `priority:` labels.
3. Remove `needs triage`.

`scripts/sync-labels.sh` defines the labels: `type:`, `priority:`, `epic`,
`needs triage`, `blocked`, `breaking change` and `automated`. It also deletes the
GitHub default labels that these labels replace. To change a label, do these steps:

1. Edit the script.
2. Run the script.

## Commit format

This repo uses [Commitizen](https://commitizen-tools.github.io/commitizen/) to make
sure that commits obey Conventional Commits. To get interactive prompts, run
`cz commit` instead of `git commit`.

```
feat: add JSON output format
fix: handle modules with no top-level names
chore: bump ruff to 0.5
docs: add pre-commit hook example
```

## Writing style

Write all prose in ASD-STE100 Simplified Technical English (STE). STE is a controlled
language: it uses common words, short sentences and the active voice. Text in STE has
only one possible meaning.

The rule applies to:

- `README.md`, `CONTRIBUTING.md`, the files in `docs/` (ADRs too) and the case READMEs
- docstrings and code comments
- CLI help text, error and log messages
- issue, commit and PR bodies

It does not apply to code identifiers, quoted output from other tools, the Conventional
Commits header syntax or `CHANGELOG.md`.

The `ste100` Claude Code skill (`.claude/skills/ste100/SKILL.md`) summarizes the rules.
The full rules and the dictionary of approved words are in the ASD-STE100 specification
at [asd-ste100.org](https://www.asd-ste100.org/). The maintainer chose STE in
[#92](https://github.com/andrewasheridan/iceberg/issues/92). Old text that is not in STE
yet will change in a separate PR.

## Docstrings

Docstrings obey the Google convention. The first line uses the imperative mood. A
docstring never starts with "Return" or "Returns", because each function that
returns a value does that. Use a verb that tells how the function makes the value,
such as *build*, *compute*, *find*, *collect*, *list*, *check*, *parse*, *render*,
*resolve*, *convert*, *load* or *get*.

```python
def snapshot(path: Path) -> Package:
    """Snapshot the public API rooted at path."""  # not "Return a snapshot of ..."
```

`tests/unit/test_docstring_style.py` applies this rule to `src/` and `tests/`.

## Comments

Write a comment only when it tells a thing that the code cannot tell: a reason, a
constraint or a consequence that is not clear. Do not use banner or section-divider
comments. A banner comment is a line made only of `#` and ten or more `-` or `=`,
usually around a section title. To group code, use a test class, a separate module or
a docstring.

`tests/unit/test_comment_style.py` applies this rule to the full repo. The
`no-banner-comments` prek hook finds banner comments before you commit.

## Readability

People read code much more frequently than they write it. When two ways work, use
the way that is easier to read. Ruff sets the layout of each line. But Ruff does not
decide where a blank line helps, or when a comprehension is too clever. You decide
these things.

The Zen of Python (`python -c "import this"`) is the guide. These lines are the most
important:

- Readability counts.
- Explicit is better than implicit.
- Simple is better than complex.
- Flat is better than nested.
- Sparse is better than dense.
- If the implementation is hard to explain, it's a bad idea.

Whitespace is your friend. Use blank lines for these purposes:

- To divide a function into its logical steps (setup, work, result).
- To put `if`, `for`, `with` and `try` blocks apart from the code around them.

To make deep nesting flat, use early returns or guard clauses. Replace a dense
one-liner with a plain loop or a named intermediate value.

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

This is guidance, not a lint rule. Reviewers apply it.

## Checks

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
task bench        # measure the analysis time of the standard library
```

To measure the time on a large tree, run `task bench -- --generate 30000`. This
command makes a package with about 30000 modules and analyzes it. Run it before
and after a change that can make the analysis slower. Compare the best times.

## Mutation testing

Line coverage shows which lines the tests run. It does not show if the tests check the
result of those lines. [mutmut](https://github.com/boxed/mutmut) finds this gap. It
changes the code in small ways, and each change is a "mutant". Then it runs the tests
that call the changed function. If all of these tests pass, the mutant "survived".

mutmut is for local runs only. CI does not run it. It is in the `mutation` dependency
group, thus `uv sync` does not install it. The `task mutate` commands install it.

```bash
task mutate                                     # test all the mutants that have no result
task mutate -- "sheridan.iceberg._formatter.*"  # test only the selected mutants
task mutate:results                             # list the mutants that survived
task mutate:browse                              # examine the mutants in a terminal UI
task mutate:clean                               # delete the results (mutants/)
```

mutmut keeps its results in `mutants/`. Thus, `task mutate` with no pattern tests only
the mutants that have no result, for example the mutants in a function that changed.
A pattern selects mutants by name, for example
`"sheridan.iceberg._builders.x_build_class*"`. mutmut always tests the selected
mutants again, also if they have a result.

A new or changed test does not reset a result. Thus, after you add tests for the
mutants that survived, give a pattern for each function to test them again.

A full run takes a long time. To start, select one module with a pattern.

### Read the results

`task mutate` shows a count for each status:

- 🎉 killed: a test failed. This is the correct result.
- 🙁 survived: all the tests passed. The tests do not check this change.
- 🧙 caught by type check: pyrefly found a type error in the mutant. mutmut does not
  run the tests for it.
- 🫥 no tests: no test calls the function.
- ⏰ timeout: the tests ran for too long.

To see the change in a mutant, run `uv run --group mutation mutmut show <name>`, or
use `task mutate:browse`. For each mutant that survived, decide which of these it is:

- A test gap: a change to the behavior that no test finds. Write a test that fails
  with the mutant.
- An equivalent mutant: the change does not change the behavior. An example is a
  `case _: return None` arm at the end of a function, because the function then
  returns `None` anyway.

Use `# pragma: no mutate` only for an equivalent mutant. Write the reason in the same
comment, after a comma:

```python
return path.name or "."  # pragma: no mutate, Path.name is empty only for "/"
```

Put the comma before the reason. If the reason starts with `block`, `start` or `end`
and has no comma, mutmut reads that word as a different pragma.

### Limits

- mutmut changes only code in functions. It does not change constants or tables at
  module level.
- mutmut must have `fork`, thus it does not run on Windows. Use WSL.
- mutmut sets the mutant in an environment variable, and the process-pool workers
  get a copy of it. Thus, a test that uses `max_workers > 1` can kill a mutant in a
  worker. But mutmut finds the tests for a function only from the calls in the main
  process. It does not run a test for a function that the test calls only in a
  worker. Each function that a worker runs also runs in-process when
  `max_workers = 1`, thus other tests check it.
- If you change `only_mutate` or `do_not_mutate` in `[tool.mutmut]`, run
  `task mutate:clean` first. If you do not, mutmut can keep a plain copy of a file
  in `mutants/` and show errors for its mutants.
- If most of the mutants show 🫥 no tests, run `task mutate:clean`, then run
  `task mutate` again. mutmut mutates a file again only if the source file is newer
  than its copy in `mutants/`. Thus, a plain copy of a file can stay in `mutants/`
  after a run that stopped or failed. The tests then call no mutated function in
  that file.

## Public API snapshot

`api.txt` is the tree output of iceberg for `src/sheridan/`. CI (the `iceberg` gate in
`task ci`) and `task check` fail if the current public API is different from
`api.txt`. They also print the diff. If you changed the API intentionally, do these
steps:

1. Run `task api:update`.
2. Commit `api.txt` together with your change.

Thus, each change to the API is visible in the review.

## Source distribution

The sdist contains only `src/`, `tests/`, `README.md`, `LICENSE`, `CHANGELOG.md` and
`pyproject.toml`. The `include` list in `[tool.hatch.build.targets.sdist]` sets these
files. Hatch adds `PKG-INFO` and `.gitignore`. CI (the `sdist` gate in `task ci`) and
`task check` build the sdist. They fail if it has a different top-level item. If you
add a file that users must have in the sdist, add it to the `include` list and to the
two checks.

## Dependencies

**Propose the dependency in an issue first**, and wait until the maintainer approves
it. Do not open PRs that add dependencies that the maintainer did not approve. After
you change dependencies, do these steps:

1. Run `uv lock`.
2. Commit `uv.lock`.
