# Getting started

This page shows how to install iceberg, look at the public API of a package and
keep a snapshot of that API in your repository.

## Install iceberg

iceberg needs Python 3.14 or later. It has no runtime dependencies.

```bash
pip install sheridan-iceberg
```

iceberg does not support Python 3.13 or earlier, and there is no plan to add this
support. If your project uses an earlier Python, run iceberg as a tool in a separate
environment:

```bash
uvx --from sheridan-iceberg iceberg src/mypkg
```

iceberg does not import your code. Thus, it can analyze a package that runs on an
earlier Python.

iceberg reads source with the `ast` module of the Python that runs it. It can read
only the syntax that this Python knows. For example, to analyze code that uses lazy
imports (`lazy import`, new in Python 3.15), run iceberg on Python 3.15 or later. On
Python 3.14, iceberg gives an `invalid syntax` error for this code.

## Look at the public API

Give iceberg the path of a package directory, a source root such as `src/`, or one
`.py` file:

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

iceberg reads the source with the Python `ast` module. It does not import or run
your code. Thus, you can use it on a package that has missing dependencies.

## Keep a snapshot of the API

A snapshot is a file in your repository that holds the output of iceberg. When a
change adds, removes or changes a public name, the snapshot changes too. Thus, the
change is easy to see in a code review.

1. Write the snapshot:

    ```bash
    iceberg src/mypkg -o api.txt
    ```

2. Commit `api.txt`.
3. In CI, write the output again and compare it with the committed file:

    ```bash
    iceberg src/mypkg | diff -u api.txt -
    ```

4. If the API changed and the change is correct, write the snapshot again and
   commit it.

The tree output is easy to read in a diff. If a program must read the snapshot, use
`--json`. For more information, see [Output formats](output-formats.md).

## Use iceberg from Python

`get_public_api` gives the same data as the CLI, as frozen dataclasses:

```python
from pathlib import Path

from sheridan.iceberg import get_public_api

api = get_public_api(Path("src/mypkg"))
for function in api.functions:
    print(function.name)
```

For all the functions and models, see the [API reference](api/api.md).

## Next steps

- To change which files iceberg reads, see [Configuration](configuration.md).
- To see how iceberg shows each package layout and edge case, see
  [Cases](cases/index.md).
