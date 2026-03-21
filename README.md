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

- Walks a Python project's modules via AST (safe, no imports)
- Uses `__all__` as the authoritative public API surface when present
- Falls back to inferring non-underscore top-level names when absent
- Reports missing, incorrect, or unsorted `__all__` declarations
- Optionally auto-fixes `__all__` in place
- Machine-readable JSON output and human-readable text output
- Works as a pre-commit hook, CLI tool, or GitHub Action

## Installation

```bash
pip install sheridan-iceberg
```

## Usage

```bash
# Check a project
iceberg check src/

# Auto-fix __all__ declarations
iceberg fix src/

# JSON output
iceberg check src/ --format json

# Ignore modules that are missing __all__ entirely
iceberg check src/ --ignore-missing

# Preview what fix would change without writing
iceberg fix src/ --dry-run
```

### Example output

```
src/mypackage/utils.py: IB001 missing __all__ (expected ['helper', 'parse'])
src/mypackage/models.py: IB002 incorrect __all__ (declared ['User'], expected ['Role', 'User'])
src/mypackage/core.py: IB003 __all__ is not sorted (expected ['Alpha', 'Beta', 'Gamma'])
```

Exit codes: `0` — no issues, `1` — issues found, `2` — path does not exist.

### JSON output

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

# Run all checks
task check

# Run tests
task test

# Build docs
task docs-serve
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.
