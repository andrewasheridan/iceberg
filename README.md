# iceberg

[![CI](https://github.com/andrewasheridan/iceberg/actions/workflows/ci.yaml/badge.svg)](https://github.com/andrewasheridan/iceberg/actions/workflows/ci.yaml)
[![PyPI](https://img.shields.io/pypi/v/sheridan-iceberg)](https://pypi.org/project/sheridan-iceberg/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)

> The public API is the tip of the iceberg. `iceberg` marks the waterline.

`iceberg` inspects and snapshots the public API surface of a Python package.
It reads source with Python's `ast` module and never imports or executes your
code, and it has no runtime dependencies.

## Features

- Reports every public module, class, function, and assignment, with full
  signatures (parameter names, annotations, defaults) and class members.
- Uses `__all__` as the source of truth when present and falls back to
  underscore-prefix inference when it is absent.
- Resolves re-exports through `__init__.py`, including relative imports,
  absolute imports, namespace packages, and imports inside `try` / `if` blocks.
- Never drops a public name silently: anything it cannot resolve to a
  definition (e.g. `from math import sqrt` listed in `__all__`) is reported as
  a reference.
- Human-readable tree output and deterministic JSON output.

## Installation

```bash
pip install sheridan-iceberg
```

## CLI

```bash
iceberg src/mypkg            # tree output
iceberg src/mypkg --json     # machine-readable output
python -m sheridan.iceberg src/mypkg
```

The path may be a package directory, a directory containing packages (such as
`src/` or a namespace package), or a single `.py` file. iceberg names packages
after the path it is given: `iceberg src/sheridan` reports `sheridan.iceberg`,
while `iceberg src/sheridan/iceberg` reports `iceberg`.

Exit codes: `0` on success, `1` for iceberg errors (missing path, invalid
config, unparseable source), `2` for unexpected errors.

### Example output

```console
$ iceberg cases/case_11
package case_11
├── def area(radius: float) -> float
├── from collections import OrderedDict as Ordered
├── import json
├── lazy_thing (unresolved)
└── from math import sqrt
```

Definitions come first. Public names that iceberg could not resolve to a
definition follow, shown as the import that binds them. A name with no binding
import at all (here, one served by a module-level `__getattr__`) is marked
`(unresolved)`.

When a package's `__init__.py` defines `__all__`, its exports are hoisted to
the package level and private submodules are hidden. Without `__all__`, every
public module is listed:

```console
$ iceberg cases/case_09
package case_09
├── module case_09.alpha
│   ├── def add(x: int, y: int) -> int
│   └── def subtract(x: int, y: int) -> int
├── module case_09.beta
│   └── class Counter
│       ├── def __init__(self, start: int = 0) -> None
│       ├── def increment(self) -> None
│       └── def value(self) -> int
└── module case_09.gamma
    ├── VERSION: str
    └── MAX_RETRIES: int
```

The [`cases/`](cases) directory documents each supported layout and edge case
alongside its expected output.

## Programmatic use

```python
from pathlib import Path

from sheridan.iceberg import get_public_api

api = get_public_api(Path("src/mypkg"))
for function in api.functions:
    print(function.name)
```

`get_public_api` returns a `Package` (or a `Module` when given a single file).
A `Package` is a trie of `modules` and `subpackages`; its `assignments`,
`classes`, `functions`, and `references` properties expose the package-level
(`__init__.py`) surface. All models are frozen dataclasses: `Package`,
`Module`, `Class`, `Function`, `Parameter`, `Assignment`, and `Reference`.

`sheridan.iceberg.utilities` provides helpers for building the same models from
smaller inputs: `get_function`, `get_class`, `get_assignment`, `get_module`, and
`get_package` accept source strings, AST nodes, paths, or live objects.

## Configuration

iceberg walks up from the analyzed path looking for `.iceberg.toml` or a
`[tool.iceberg]` table in `pyproject.toml`. Unknown keys are rejected.

```toml
[tool.iceberg]
# Regex matched against each file's POSIX path; matches are skipped.
test_module_pattern = '(^|/)tests?(/|$)|(^|/)test_[^/]*\.py$|_test\.py$'
# Worker processes used to parse modules (default: 1, in-process). Only very
# large trees benefit; values above 1 require scripts calling get_public_api
# to be guarded by `if __name__ == "__main__":`.
max_workers = 1
```

To bypass file discovery, pass a `Config` directly:

```python
import re
from pathlib import Path

from sheridan.iceberg import Config, get_public_api

api = get_public_api(Path("src/mypkg"), config=Config(test_module_pattern=re.compile(r"_test\.py$")))
```

## Development

```bash
task install   # set up the environment
task ci        # lint, format check, type check, tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.
