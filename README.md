# sheridan-iceberg

[![CI](https://github.com/sheridan/sheridan-iceberg/actions/workflows/ci.yml/badge.svg)](https://github.com/sheridan/sheridan-iceberg/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-90%25-brightgreen)](https://github.com/sheridan/sheridan-iceberg)
[![Mutation Score](https://img.shields.io/badge/mutation-tracked-blue)](https://github.com/sheridan/sheridan-iceberg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)

> The public API is the tip of the iceberg. `iceberg` guards the waterline.

`sheridan-iceberg` analyzes Python modules and enforces the presence and
correctness of `__all__`. It uses Python's `ast` module for static analysis —
no importing of user code.

## Features

- **`show`** — inspect and report the effective public API of any module or project; uses `__all__` when present, falls back to AST inference; `--use-ast` forces AST-only regardless of `__all__`
- **`check`** — enforce `__all__` correctness; IB002 is one-directional (names that appear public in the AST but are absent from `__all__`), so deliberate re-exports are never flagged as phantom names
- **`fix`** — auto-repair `__all__` in place; uses full bidirectional comparison, removing phantom exports as well as adding missing ones
- Walks a Python project's modules via AST (safe, no imports)
- Uses `__all__` as the authoritative public API surface when present; falls back to inferring non-underscore top-level names when absent
- Machine-readable JSON output and human-readable text/tree output
- Works as a pre-commit hook, CLI tool, or GitHub Action

## Installation

```bash
pip install sheridan-iceberg
```

## Usage

```bash
# Report the public API of a project
iceberg show src/

# Show as JSON (machine-readable)
iceberg show src/ --format json

# Ignore __all__ entirely — always use AST inference
iceberg show src/ --use-ast

# Check __all__ declarations against the AST
iceberg check src/

# Suppress IB001 (missing __all__) — only report IB002 and IB003
iceberg check src/ --ignore-missing

# Check with JSON output
iceberg check src/ --format json

# Auto-fix __all__ declarations (bidirectional — also removes phantom exports)
iceberg fix src/

# Preview what fix would change without writing
iceberg fix src/ --dry-run
```

### Example output

`iceberg show` produces an indented tree by default:

```
# iceberg show src/mypackage/

mypackage/
  __init__
    Role
    User
    helper
  core
    Alpha
    Beta
    Gamma
  utils
    helper
    parse
```

`iceberg check` reports violations:

```
src/mypackage/utils.py: IB001 missing __all__ (expected ['helper', 'parse'])
src/mypackage/models.py: IB002 names appear public but missing from __all__: ['Role']
src/mypackage/core.py: IB003 __all__ is not sorted (expected ['Alpha', 'Beta', 'Gamma'])
```

Exit codes:
- `show`: `0` always (path existence aside)
- `check`: `0` no issues, `1` issues found, `2` path not found
- `fix`: `0` success, `2` path not found

### JSON output

`iceberg show --format json`:

```json
[
  {
    "module": "mypackage.utils",
    "path": "src/mypackage/utils.py",
    "source": "ast",
    "names": ["helper", "parse"]
  },
  {
    "module": "mypackage.models",
    "path": "src/mypackage/models.py",
    "source": "__all__",
    "names": ["Role", "User"]
  }
]
```

The `source` field is `"__all__"` when the module has an `__all__` (and `--use-ast` is not set), `"ast"` otherwise.

`iceberg check --format json`:

```json
[
  {
    "code": "IB001",
    "path": "src/mypackage/utils.py",
    "kind": "missing",
    "declared": null,
    "expected": ["helper", "parse"]
  }
]
```

## How inference works

For regular modules, iceberg infers the public API from top-level definitions —
functions, classes, and assignments whose names do not start with `_`.

For `__init__.py` files, names re-exported via `from x import y` are also
counted, since this is the standard Python pattern for building a package's
public surface.

```python
# foo/__init__.py
from foo.snap import Widget   # Widget is inferred as public
from foo._bar import _helper  # _helper is excluded (underscore)
```

**Submodules are not automatically included.** The existence of `foo/snap.py`
on disk does not add `snap` to `foo.__all__` — the `__init__.py` is the
explicit gatekeeper. To expose a submodule, import it explicitly:

```python
# foo/__init__.py
from foo import snap  # now snap is part of the inferred public API
```

Test files (`test_*.py`, `*_test.py`, `conftest.py`) are always skipped.

## As a pre-commit hook

```yaml
repos:
  - repo: https://github.com/sheridan/sheridan-iceberg
    rev: v0.1.0
    hooks:
      - id: iceberg
```

## Development

```bash
# Install dependencies
task install

# Run all checks (lint, format, typecheck, test, iceberg)
task check

# Run individual checks
task lint:check   # ruff — read-only
task lint         # ruff — autofix
task format:check # formatter — read-only
task format       # formatter — write
task typecheck    # mypy --strict
task test         # pytest --cov
task iceberg      # dogfood: run iceberg on itself

# Run tests
task test

# Build docs
task docs-serve
```

### CI pipeline (Dagger)

The full CI pipeline runs each gate in its own container via [Dagger](https://dagger.io).
Podman is the default runtime; Docker is supported via `CONTAINER_RUNTIME=docker`.

```bash
# First-time setup (generates ci/sdk/ — run once after clone)
podman machine start   # macOS only
task ci-init

# Run the full CI pipeline locally
task ci

# Use Docker instead
CONTAINER_RUNTIME=docker task ci
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.
