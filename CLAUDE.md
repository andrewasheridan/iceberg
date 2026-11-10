# CLAUDE.md

iceberg (`sheridan-iceberg` on PyPI) shows the public API of a Python package. It reads
the source with `ast`. It does not import the package.

## Check command

Run `task check` before you say that a change is done. It runs these gates:
`lock:check`, `lint:check`, `format:check`, `typecheck` (pyrefly), `test`, `api:check`
and `sdist:check`. All gates must pass. `CONTRIBUTING.md` lists the other tasks.

If you change the public API on purpose, run `task api:update` and commit `api.txt`.

## Architecture

The code is in `src/sheridan/iceberg/`. The analysis is a pipeline of four steps:

1. Discover: `_discovery.py` walks the package directory. It makes one
   `DiscoveredModule` for each module to visit, and removes the test modules.
2. Visit: `_visitor.py` reads the AST of each module and makes a `Module` snapshot.
   `_builders.py` makes the models for each definition.
3. Resolve: `_init_resolver.py` resolves the re-exports in each `__init__.py`, for
   example `from .sibling import X`.
4. Trie: `_orchestrator.py` connects the steps. It puts all the modules into a
   `Package` trie.

Other modules:

- `_models.py`: the dataclass models (`Package`, `Module`, `Class`, `Function`,
  `Assignment`, `Diagnostic`).
- `_api.py`: the public entry points, `get_public_api` and `get_public_api_report`.
- `_formatter.py` and `_loader.py`: write the models as a tree or as JSON, and read the
  JSON again.
- `_cli.py`: the command-line interface.

The `cases/` directory has example packages. Each case has a `README.md` that shows the
expected output. If you change the output that users see, update the case READMEs and
the golden tests.

## Code conventions

- Write all prose (docs, READMEs, docstrings, comments, CLI messages, issue, commit and
  PR bodies) in ASD-STE100 Simplified Technical English. Load the `ste100` skill before
  you write or edit prose. See the Writing style section of CONTRIBUTING.md.

- No banner or section-divider comments: no lines made only of `#` and a run of `-` or
  `=`, and no title comments wrapped in them. To group code, use a test class, a
  separate module or a docstring. `tests/unit/test_comment_style.py` and the
  `no-banner-comments` prek hook enforce this; see the Comments section of CONTRIBUTING.md.
- Write a comment only when it says something the code can't: a reason, a constraint
  or a non-obvious consequence. Don't label sections or restate what the code does.
- Readability matters: code is read far more often than it is written. When two ways
  work, pick the one that is easier to read. Follow the Zen of Python
  (`python -c "import this"`), above all: readability counts; explicit is better than
  implicit; simple is better than complex; flat is better than nested; sparse is
  better than dense; if the implementation is hard to explain, it's a bad idea.
- Whitespace is your friend. Use blank lines to split a function into its logical steps
  (setup, work, result) and to set off `if`/`for`/`with`/`try` blocks from the code
  around them. Flatten nesting with early returns, and prefer a plain loop or a named
  intermediate value to a clever one-liner. See the Readability section of
  CONTRIBUTING.md.

The `python-dev` skill has the tools and the Python rules. The `git-workflow` skill has
the branch, commit, PR and release rules.

## Claude Code files

Commit new skills, agents and settings in `.claude/`. A file stays local only if
`.gitignore` lists it, for example the issue loop (`.claude/skills/next-issue/`).
`.claude/settings.local.json` is for your own settings and is not tracked.

`.claude/settings.json` stops pushes to `main` and force-pushes. In an interactive
session, the `.claude/hooks/ask-before-merge.sh` hook asks you before each merge
command. Headless sessions (`claude -p`) skip this question, so that the issue loop can
enable auto-merge.
