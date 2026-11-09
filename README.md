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
  Definitions inside `if` / `try` blocks at module level or in a class body
  (`if TYPE_CHECKING:`, version checks, `except ImportError:` fallbacks)
  count; when a name is defined more than once, the first definition is kept.
- Uses `__all__` as the source of truth when present and falls back to
  underscore-prefix inference when it is absent. `__all__` is evaluated
  statically: literal lists and tuples, `+` concatenation, `+=`, `.extend()`,
  `.append()`, `.insert()`, `.remove()`, `.sort()`, `.reverse()`, and `sub.__all__` for modules inside the analyzed tree. When it
  cannot be evaluated, iceberg emits a warning naming the file and line, then
  falls back to inference. Dunder class members such as
  `__call__` and `__eq__` are public; `_x` and name-mangled `__x` are private.
- Resolves re-exports through `__init__.py`, including relative imports,
  absolute imports, namespace packages, and imports inside `try` / `if` blocks.
  A star import (`from ._core import *`) from a module in the analyzed tree
  binds that module's `__all__`, or its public names when it has none.
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
iceberg src/mypkg --show-overload-implementations  # also show @overload implementations
python -m sheridan.iceberg src/mypkg
```

The path may be a package directory, a directory containing packages (such as
`src/` or a namespace package), or a single `.py` file. iceberg names packages
after the path it is given: `iceberg src/sheridan` reports `sheridan.iceberg`,
while `iceberg src/sheridan/iceberg` reports `iceberg`.

Exit codes: `0` on success, `1` for iceberg errors (missing path, invalid
config, unreadable or unparseable source), `2` for unexpected errors. Source files
are decoded the way Python decodes them: UTF-8 unless a PEP 263 encoding
declaration such as `# -*- coding: latin-1 -*-` says otherwise.

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

### JSON output

`--json` prints one object for the analyzed package or module. Its first key is
`schema_version`, an integer that changes when the JSON format changes in a way
that can break consumers. Every package, module, class, function, assignment
and reference object has a `node_type` field (`package`, `module`, `class`,
`function`, `assignment` or `reference`). Function objects also have a `kind`
field (`function`, `method`, `classmethod`, `staticmethod` or `property`).

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
`Function.kind` tells a module-level `"function"` apart from a class's
`"method"`, `"classmethod"`, `"staticmethod"` and `"property"`, and
`Function.decorators` lists its decorators as source strings. The tree shows a
property as the attribute callers read (`property p: int`) and prefixes
classmethods and staticmethods with their kind. Property setters and deleters
are not listed separately. A function with `typing.overload` signatures is one
`Function` whose `overloads` tuple holds those signatures. The tree shows one
line per overload and hides the implementation signature unless you pass
`--show-overload-implementations`.

`sheridan.iceberg.utilities` provides helpers for building the same models from
smaller inputs: `get_function`, `get_class`, `get_assignment`, `get_module`, and
`get_package` accept source strings, AST nodes, paths, or live objects.
With a path, `get_function` and `get_class` look up `name` among module-level
definitions first. Use a dotted name such as `"MyClass.method"` to select a
nested definition.

When it walks a directory, iceberg skips hidden directories, `__pycache__`,
common non-source directories (`build`, `dist`, `venv`, `env`, `node_modules`,
`site-packages` and `*.egg-info`), and any directory or `.py` file whose name
cannot be imported because it is not a Python identifier or is a keyword (for
example `my-dir/` or `my-script.py`). The directory you pass is always
analyzed, even if its own name is not an identifier.

To skip more paths, pass `--exclude` one or more times, or set `exclude` in the
configuration (see below). Each value is a glob matched against the path of a
directory or file relative to the directory you pass. `**` matches any number
of directories:

```bash
iceberg src/mypkg --exclude legacy --exclude '**/*_pb2.py'
```

`--exclude` adds to the `exclude` list from the configuration file.

## Configuration

iceberg walks up from the analyzed path and checks each directory, nearest
first:

- If the directory has an `.iceberg.toml`, iceberg uses it. In one directory,
  `.iceberg.toml` has priority over `pyproject.toml`.
- Otherwise, if the directory has a `pyproject.toml`, it is the project root and
  the search stops there. iceberg uses its `[tool.iceberg]` table, or the
  defaults if it has none. Configuration above the project root (for example a
  `~/.iceberg.toml` or a parent project's `pyproject.toml`) never applies.
- If no file is found, iceberg uses the defaults.

Unknown keys are rejected.

```toml
[tool.iceberg]
# Regex searched in each file's POSIX path relative to the analyzed directory's
# parent (for example `pkg/sub/mod.py`); matching files are skipped.
test_module_pattern = '(^|/)tests?(/|$)|(^|/)test_[^/]*\.py$|_test\.py$'
# Worker processes used to parse modules (default: 1, in-process). Only very
# large trees benefit; values above 1 require scripts calling get_public_api
# to be guarded by `if __name__ == "__main__":`.
max_workers = 1
# Globs matched against each directory's and file's path relative to the
# analyzed directory; matches are skipped. `**` matches any number of
# directories. The --exclude CLI option adds to this list.
exclude = ["legacy", "**/*_pb2.py"]
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
