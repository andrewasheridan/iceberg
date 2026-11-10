---
name: python-dev
description: Python conventions for iceberg - uv for environments and dependencies, Taskfile tasks, ruff for lint and format, pyrefly for type checks, pytest for tests, prek hooks. Use when you write, change, test, or add dependencies to Python code in this repo.
---

# Python development

## Tools

| Job | Tool | Command |
|---|---|---|
| Environment, dependencies, running | uv | `uv sync`, `uv run` |
| Format | ruff | `task format` (`task format:check` to only check) |
| Lint | ruff | `task lint` (`task lint:check` to only check) |
| Type check | pyrefly | `task typecheck` |
| Test | pytest | `task test` (give pytest arguments after `--`) |
| Public API snapshot | iceberg | `task api:check`, `task api:update` |
| All gates | Taskfile | `task check` |

`Taskfile.yaml` defines the tasks. The configuration for ruff, pyrefly, pytest,
coverage and commitizen is in `pyproject.toml`. Do not add separate configuration files
(`ruff.toml`, `pytest.ini`, `pyrefly.toml`, `setup.cfg`).

The project uses pyrefly, not mypy. Do not run mypy.

## Rules

- Always use `uv`. Do not use `pip` or `python -m venv`, and do not activate a venv.
  Run code with `uv run ...`.
- Propose a new dependency in an issue first. Add it only after the maintainer approves
  it. Then run `uv lock` and commit `uv.lock`.
- The package code is in `src/sheridan/iceberg/`. The tests are in `tests/unit/` and
  `tests/functional/`. The name of a unit test file is `test_<module>.py`, for example
  `test__formatter.py`.
- Target Python 3.14. Use modern syntax: `X | None`, built-in generics (`list[int]`),
  `type` aliases, and `match` when it is easier to read.
- The maximum line length is 120 characters. Ruff enforces it.
- Add type annotations to all function signatures, in tests too. Do not use `Any` or
  `# type: ignore` if you can use a different solution. If you must use them, add a
  comment that tells why.
- Write a test for each change in behavior. When you fix a bug, write a test that fails
  before you write the fix.
- The minimum test coverage is 90%.
- If you change the public API on purpose, run `task api:update` and commit `api.txt`.
- If you change the output that users see, update the case READMEs in `cases/` and the
  golden tests.

## Docstrings

- Use the Google convention. Ruff enforces it (the `D` rules).
- Each public module, class, function and method in `src/` must have a docstring.
- Write the text in STE (see the `ste100` skill).
- The summary line is one imperative sentence that ends with a period.
- Do not start a docstring with "Return" or "Returns". Use a verb that tells how the
  function makes the value, such as *build*, *find*, *parse* or *resolve*.
  `tests/unit/test_docstring_style.py` enforces this rule.
- Do not write the types in the docstring. The type annotations give the types.

```python
def parse(text: str, *, strict: bool = False) -> list[Record]:
    """Parse the records in a CSV text.

    Args:
        text: The CSV text. The first line must be the header.
        strict: If true, stop at the first record that is not valid.

    Returns:
        The records, in the same order as in the text.

    Raises:
        ParseError: If `strict` is true and a record is not valid.
    """
```

## Before you say that the work is done

Run `task check` and make sure that it passes.

The prek hooks run ruff, pyrefly and the `no-banner-comments` check on each commit.
They run pytest on each push. To install the hooks, run `uv run prek install` once for
each clone.

If a check fails, fix the cause. Do not disable a rule, skip a test or suppress a type
error to make a check pass, unless the user agrees.
