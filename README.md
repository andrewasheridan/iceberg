# sheridan-iceberg

[![CI](https://github.com/andrewasheridan/iceberg/actions/workflows/ci.yaml/badge.svg)](https://github.com/andrewasheridan/iceberg/actions/workflows/ci.yaml)
[![PyPI](https://img.shields.io/pypi/v/sheridan-iceberg)](https://pypi.org/project/sheridan-iceberg/)
[![Coverage](https://img.shields.io/badge/coverage-90%25-brightgreen)](https://github.com/andrewasheridan/iceberg)
[![Mutation Score](https://img.shields.io/badge/mutation-tracked-blue)](https://github.com/andrewasheridan/iceberg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)

> The public API is the tip of the iceberg. `iceberg` guards the waterline.

`sheridan-iceberg` reports the public API surface of Python modules. It uses
Python's `ast` module for static analysis — no importing of user code.

## Features

- Report the effective public API of any module or project; includes function signatures (parameter names, types, defaults) and class member surfaces (attributes, properties, methods)
- Uses `__all__` as the authoritative public API surface when present; falls back to inferring non-underscore top-level names when absent
- `--use-ast` forces AST-only inference regardless of `__all__`
- Walks an entire Python project's module tree via AST (safe, no imports)
- Machine-readable JSON output and human-readable tree output

## Installation

```bash
pip install sheridan-iceberg
```

## Usage

```bash
# Report the public API of a project
iceberg src/

# Show as JSON (machine-readable)
iceberg src/ --format json

# Ignore __all__ entirely — always use AST inference
iceberg src/ --use-ast
```

Exit codes: `0` always (path existence aside); `2` if path not found.

### Example output

`iceberg` produces an indented tree by default. Functions are shown with their
full signatures; classes are followed by an indented list of their public
members. When `__init__.py` declares `__all__`, it is the source of truth for
the whole package — only that module is shown:

```
# iceberg src/mypackage/

mypackage/
  __init__
    Role
      name: str
      level: int
      permissions (property) → list[str]
      classmethod create(cls, name: str, level: int = ...) → Role
      promote(self) → None
    User
      email: str
      role: Role
      is_active: bool
      save(self) → None
    helper(path: Path) → list[str]
```

Pass `--use-ast` to bypass `__all__` and see every module's inferred names:

```
# iceberg src/mypackage/ --use-ast

mypackage/
  __init__
    Role
      ...
    User
      ...
    helper(path: Path) → list[str]
  core
    Alpha
    Beta
    Gamma
  utils
    helper(path: Path) → list[str]
    parse(text: str, strict: bool = ...) → dict[str, object]
```

### JSON output

`iceberg --format json`:

```json
[
  {
    "module": "mypackage.utils",
    "path": "src/mypackage/utils.py",
    "source": "ast",
    "names": ["helper", "parse"],
    "detail": {
      "helper": {
        "kind": "function",
        "signature": {
          "params": [
            {"name": "path", "annotation": "Path", "has_default": false, "kind": "positional_or_keyword"}
          ],
          "return_annotation": "list[str]",
          "is_async": false
        }
      },
      "parse": {
        "kind": "function",
        "signature": {
          "params": [
            {"name": "text", "annotation": "str", "has_default": false, "kind": "positional_or_keyword"},
            {"name": "strict", "annotation": "bool", "has_default": true, "kind": "positional_or_keyword"}
          ],
          "return_annotation": "dict[str, object]",
          "is_async": false
        }
      }
    }
  }
]
```

The `source` field is `"__all__"` when the module has an `__all__` (and `--use-ast` is not set), `"ast"` otherwise.

The `detail` object maps each public name to its rich info. Functions have `kind: "function"` (or `"async function"`) and a `signature` object. Classes have `kind: "class"`, a `bases` list, and a `members` array. Plain variables (no static type info available) are absent from `detail`.

## Programmatic usage

```python
from sheridan.iceberg import get_public_api

# Get the public API surface — __init__.__all__ is the source of truth
api = get_public_api("src/")
# {"mypackage": ["Role", "User", "helper"]}

# Bypass __all__ and see every module's AST-inferred names
api = get_public_api("src/", use_ast=True)
# {"mypackage": [...], "mypackage.core": [...], "mypackage.utils": [...]}
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
task iceberg      # dogfood: show iceberg's own public API

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
