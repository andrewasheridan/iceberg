# iceberg

[![CI](https://github.com/andrewasheridan/iceberg/actions/workflows/ci.yaml/badge.svg)](https://github.com/andrewasheridan/iceberg/actions/workflows/ci.yaml)
[![PyPI](https://img.shields.io/pypi/v/sheridan-iceberg)](https://pypi.org/project/sheridan-iceberg/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)

> The public API is the tip of the iceberg. `iceberg` marks the waterline.

`iceberg` inspects the public API of a Python package and makes a snapshot of it.
It reads the source with the Python `ast` module. It never imports or runs your
code, and it has no runtime dependencies.

## Features

- It shows each public module, class, function and assignment. It shows full
  signatures (parameter names, annotations and default values), the bases and
  keyword arguments of a class (`class Error(Base, metaclass=Meta)`), and the
  members of a class.
- It includes definitions in `if` and `try` blocks at module level or in a class
  body. Examples are `if TYPE_CHECKING:`, version checks and `except ImportError:`
  fallbacks. If a name has more than one definition, iceberg keeps the first one.
- If a module has `__all__`, iceberg uses it as the list of public names. If the
  module has no `__all__`, a name is public when it does not start with an
  underscore.
- iceberg reads `__all__`, but it does not run the code. It understands these forms:
  literal lists and tuples, `+` concatenation, `+=`, `.extend()`, `.append()`,
  `.insert()`, `.remove()`, `.sort()` and `.reverse()`. It also understands
  `sub.__all__` and `from .sub import __all__` for modules in the analyzed tree.
- iceberg applies the changes to `__all__` in module-level `if` and `try` blocks.
  `__all__` keeps each name that a branch adds.
- If iceberg cannot read `__all__`, it shows a warning with the file and the line.
  Then it uses the underscore rule.
- Dunder class members such as `__call__` and `__eq__` are public. Members with
  the names `_x` and `__x` (name-mangled) are private.
- iceberg follows re-exports through `__init__.py`. It understands relative
  imports, absolute imports, namespace packages, and imports in `try` and `if`
  blocks. A lazy import (`lazy from ._core import thing`) resolves the same as an
  eager import, and the output does not show `lazy`.
- A star import (`from ._core import *`) from a module in the analyzed tree
  gives the `__all__` of that module. If that module has no `__all__`, it gives
  the public names of the module.
- iceberg never removes a public name silently. Sometimes iceberg cannot find
  the definition of a public name, for example `from math import sqrt` in
  `__all__`. Then iceberg shows the name as a reference.
- iceberg gives a tree output for people and a deterministic JSON output.

## Installation

```bash
pip install sheridan-iceberg
```

iceberg reads source with the `ast` module of the Python that runs it. It can read
only the syntax that this Python knows. For example, to analyze code that uses lazy
imports (`lazy import`, new in Python 3.15), run iceberg on Python 3.15 or later. On
Python 3.14, iceberg gives an `invalid syntax` error for this code.

## CLI

```bash
iceberg src/mypkg            # tree output
iceberg src/mypkg --json     # machine-readable output
iceberg src/mypkg --json -o api.json  # write UTF-8 to a file instead of stdout
iceberg src/mypkg --show-overload-implementations  # also show @overload implementations
iceberg src/mypkg --keep-going  # skip files that cannot be read or parsed
iceberg src/mypkg --traceback  # print the full traceback of an unexpected error
iceberg --version            # print the installed version
python -m sheridan.iceberg src/mypkg
```

The path can be a package directory, a directory that contains packages (such as
`src/` or a namespace package), or one `.py` file. iceberg gives names to packages
from the path that you give it. For example, `iceberg src/sheridan` shows
`sheridan.iceberg`, and `iceberg src/sheridan/iceberg` shows `iceberg`.

The exit codes are:

- `0`: The command was successful.
- `1`: An iceberg error occurred. Examples are a path that does not exist, an incorrect
  configuration, a source file that iceberg cannot read or parse, and an
  `--output` file that iceberg cannot write.
- `2`: An unexpected error occurred.

An unexpected error is a bug in iceberg. To report it, do these steps:

1. Run the command again with `--traceback` (or set `ICEBERG_DEBUG=1`).
2. Copy the full traceback.
3. Put the traceback in your [bug report](https://github.com/andrewasheridan/iceberg/issues).

iceberg decodes source files in the same way as Python. The encoding is UTF-8,
unless a PEP 263 encoding declaration such as `# -*- coding: latin-1 -*-` gives
a different encoding.

iceberg writes the report to stdout as UTF-8. The encoding of the console or the
pipe has no effect. Thus, the tree connectors do not cause an error on Windows.

`-o/--output PATH` writes the report to PATH as UTF-8 with a final newline. The
encoding of the console has no effect. iceberg writes to a temporary file first.
When the report is complete, iceberg moves the file into PATH. Thus, an error
never leaves a partial file and never overwrites the old file.

- If PATH is a symlink, iceberg writes the report to the target file of the link.
  The link does not change.
- If the file exists, it keeps its permission bits. After iceberg writes the file, the
  user who ran iceberg owns it.
- If PATH names an open file descriptor (for example `/dev/stdout` or
  `/dev/fd/1`), iceberg writes to that descriptor. Thus the report goes where the
  shell sent the descriptor. With `-o /dev/stdout >> log.txt`, iceberg adds the
  report to the end of `log.txt`.
- If PATH is not a regular file (for example a named pipe), iceberg writes to it
  directly, without a temporary file.

### Continue after bad files

By default, if iceberg cannot read or parse a file, the run stops. An example is
a vendored Python 2 module. With `--keep-going`, iceberg does these steps:

1. It skips the bad module.
2. It prints the API of all the other modules.
3. It writes one diagnostic on each line to stderr. First, it writes an `error`
   for each module that it skipped. Then it writes a `warning` for each exported
   name that no import binds. The tree marks these names `(unresolved)`.

```text
/src/mypkg/vendored.py:2: error: Missing parentheses in call to 'print'. Did you mean print(...)?
/src/mypkg/__init__.py: warning: 'lazy_thing' is exported but never bound
```

If iceberg skipped a module, the exit code is `1`. If there are only warnings, the
exit code is `0`. With `--json`, the output also has a top-level `diagnostics`
list. The paths in this list are relative to the analyzed directory. If you give
one `.py` file and iceberg cannot parse it, iceberg shows an error. There is
nothing else to show.

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

The definitions come first. Then come the public names that iceberg cannot
connect to a definition. iceberg shows the import that binds each of these names.
If no import binds a name, iceberg marks it `(unresolved)`. In this example, a
module-level `__getattr__` supplies the name.

If the `__init__.py` of a package defines `__all__`, iceberg moves the exported
names up to the package level. It does not show the private submodules. If there
is no `__all__`, iceberg shows each public module:

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
`schema_version`. This integer changes when a change to the JSON format can
break the programs that read it.

Each package, module, class, function, assignment and reference object has a
`node_type` field. Its value is `package`, `module`, `class`, `function`,
`assignment` or `reference`. Function objects also have a `kind` field. Its value
is `function`, `method`, `classmethod`, `staticmethod` or `property`.

[`docs/schema/iceberg.schema.json`](docs/schema/iceberg.schema.json) is a JSON
Schema (draft 2020-12) for this output. The tests validate the output of each
case against this schema.

The [`cases/`](cases) directory shows each supported layout and edge case, with
its expected output.

## Programmatic use

```python
from pathlib import Path

from sheridan.iceberg import get_public_api

api = get_public_api(Path("src/mypkg"))
for function in api.functions:
    print(function.name)
```

`get_public_api` returns a `Package`. If you give it one file, it returns a
`Module`. A `Package` is a trie of `modules` and `subpackages`. Its
`assignments`, `classes`, `functions` and `references` properties give the
package-level (`__init__.py`) API.

All models are frozen dataclasses: `Package`, `Module`, `Class`, `Function`,
`Parameter`, `Assignment` and `Reference`.

- `Function.kind` tells the difference between a module-level `"function"` and
  a `"method"`, `"classmethod"`, `"staticmethod"` or `"property"` of a class.
- `Function.decorators` lists the decorators of a function as source strings.
- `Class.bases` and `Class.keywords` list the bases and the keyword arguments of
  a class as source strings. An example of a keyword argument is
  `metaclass=ABCMeta`.

The tree shows a property as the attribute that callers read
(`property p: int`). It puts the kind before the names of classmethods and
staticmethods. It does not show property setters and deleters as separate items.

A function with `typing.overload` signatures is one `Function`. Its `overloads`
tuple holds those signatures. The tree shows one line for each overload. It does
not show the signature of the implementation, unless you give
`--show-overload-implementations`.

`get_public_api_report(path, keep_going=True)` does the same work as
`--keep-going` in Python code. It returns a `Report` with these attributes:

- `api`: the `Package` or the `Module`.
- `diagnostics`: a tuple of `Diagnostic` objects. Each object has a `severity`,
  a `module`, a `path`, a `message` and a `lineno`.
- `has_errors`: `True` if iceberg skipped a module.

Without `keep_going`, the function raises an exception at the first bad file,
the same as `get_public_api`. But it still lists the warnings for unresolved
names.

`load_json` reads the output of `iceberg --json` back into a `Package` or
`Module`. The JSON keeps package paths relative to the analyzed directory. Thus,
the paths that `load_json` gives are also relative, unless you give `root=`.
`load_json` raises `SnapshotError` (an `IcebergError`) for these problems:

- The JSON is not valid.
- There is no `schema_version`, or iceberg does not support it.
- A node has an incorrect structure.

```python
from pathlib import Path

from sheridan.iceberg import load_json

old = load_json(Path("api.json").read_text(encoding="utf-8"))
```

`sheridan.iceberg.utilities` has functions that make the same models from
smaller inputs: `get_function`, `get_class`, `get_assignment`, `get_module` and
`get_package`. These functions accept source strings, AST nodes, paths or live
objects. If you give a path, `get_function` and `get_class` look for `name` in
the module-level definitions first. To select a nested definition, use a dotted
name such as `"MyClass.method"`.

When iceberg walks through a directory, it skips these directories and files:

- Hidden directories and `__pycache__`.
- Usual directories that do not contain source: `build`, `dist`, `venv`, `env`,
  `node_modules`, `site-packages` and `*.egg-info`.
- A directory or `.py` file that you cannot import, because its name is not a
  Python identifier or is a keyword. Examples are `my-dir/` and `my-script.py`.

iceberg always analyzes the directory that you give it, even if its name is not
an identifier.

To skip more paths, give `--exclude` one or more times, or set `exclude` in the
configuration (see below). Each value is a glob. iceberg compares it with the
path of each directory and file, relative to the directory that you give.
`**` matches zero or more directories:

```bash
iceberg src/mypkg --exclude legacy --exclude '**/*_pb2.py'
```

`--exclude` adds to the `exclude` list from the configuration file.

## Configuration

iceberg starts at the analyzed path and goes up through the parent directories.
It examines each directory, the nearest one first:

- If the directory has an `.iceberg.toml` file, iceberg uses it. In one
  directory, `.iceberg.toml` has priority over `pyproject.toml`.
- If the directory has no `.iceberg.toml` but has a `pyproject.toml`, this
  directory is the project root. The search stops there. iceberg uses the
  `[tool.iceberg]` table of the file. If there is no table, iceberg uses the
  default values.
- iceberg never uses configuration above the project root. Examples are a
  `~/.iceberg.toml` file or the `pyproject.toml` of a parent project.
- If iceberg finds no file, it uses the default values.

iceberg does not accept unknown keys.

These command-line options change the configuration for one run:

- `--config PATH` reads only `PATH` and does not search. If the name of the file
  is `pyproject.toml`, iceberg reads its `[tool.iceberg]` table. iceberg reads
  all other files in the same way as an `.iceberg.toml` file.
- `--no-config` ignores all configuration files and uses the default values. You
  cannot use it together with `--config`.
- `--max-workers N` replaces `max_workers`, and `--exclude` adds to `exclude`.
  Values from the command line always have priority over the file.

```bash
iceberg src/mypkg --config ci/iceberg.toml --max-workers 4
iceberg src/mypkg --no-config
```

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

To use a configuration without a file, give a `Config` directly:

```python
import re
from pathlib import Path

from sheridan.iceberg import Config, get_public_api

api = get_public_api(Path("src/mypkg"), config=Config(test_module_pattern=re.compile(r"_test\.py$")))
```

## Development

```bash
task install            # set up the environment
uv run prek install     # install the Git hooks
task ci                 # lint, format check, type check, tests
```

For more information, see [CONTRIBUTING.md](CONTRIBUTING.md).
