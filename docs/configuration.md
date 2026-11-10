# Configuration

iceberg works without configuration. Use a configuration file to skip more files or
to parse with more than one process.

## Configuration keys

| Key | Type | Default | Description |
|---|---|---|---|
| `test_module_pattern` | string (regex) | `(^\|/)tests?(/\|$)\|(^\|/)test_[^/]*\.py$\|_test\.py$` | iceberg searches for this regex in the path of each file. It skips the files that match. |
| `max_workers` | integer | `1` | The number of worker processes that parse modules. |
| `exclude` | list of strings (globs) | `[]` | iceberg skips the directories and files that match one of these globs. |

iceberg does not accept unknown keys. If a key is unknown or a value has an
incorrect type, iceberg stops with exit code `1`.

### `test_module_pattern`

iceberg searches for the regex in the POSIX path of each file. The path is relative
to the parent of the analyzed directory, for example `pkg/sub/mod.py`. The default
value matches `test/` and `tests/` directories, `test_*.py` files and `*_test.py`
files.

### `max_workers`

With the default value `1`, iceberg parses all modules in the same process. This is
the fastest for usual packages. Values above `1` help only for very large trees.

!!! warning
    If `max_workers` is more than `1`, guard a script that calls `get_public_api`
    with `if __name__ == "__main__":`. The worker processes import the script again.

### `exclude`

Each value is a glob. iceberg compares it with the POSIX path of each directory and
file, relative to the analyzed directory, for example `sub/mod.py`. `**` matches
zero or more directories. iceberg does not go into a directory that matches.

iceberg always skips some paths, also without `exclude`:

- Hidden directories and `__pycache__`.
- `build`, `dist`, `venv`, `env`, `node_modules`, `site-packages` and `*.egg-info`.
- A directory or `.py` file with a name that is not a Python identifier, or that is
  a keyword. Examples are `my-dir/` and `my-script.py`.

## Configuration files

Put the keys in an `.iceberg.toml` file, or in the `[tool.iceberg]` table of
`pyproject.toml`:

```toml
[tool.iceberg]
test_module_pattern = '(^|/)tests?(/|$)|(^|/)test_[^/]*\.py$|_test\.py$'
max_workers = 1
exclude = ["legacy", "**/*_pb2.py"]
```

In an `.iceberg.toml` file, put the keys at the top level, without a table header.

## How iceberg finds the configuration

iceberg starts at the analyzed path and goes up through the parent directories. It
examines each directory, the nearest one first:

1. If the directory has an `.iceberg.toml` file, iceberg uses it. In one directory,
   `.iceberg.toml` has priority over `pyproject.toml`.
2. If the directory has a `pyproject.toml` file, this directory is the project root.
   iceberg uses the `[tool.iceberg]` table of the file and stops the search. If
   there is no table, iceberg uses the default values.
3. If iceberg finds no file, it uses the default values.

iceberg never uses configuration above the project root. Examples are a
`~/.iceberg.toml` file and the `pyproject.toml` of a parent project.

## Command-line options

These options change the configuration for one run. Values from the command line
always have priority over the file.

| Option | Effect |
|---|---|
| `--config PATH` | Read only `PATH` and do not search. If the name of the file is `pyproject.toml`, iceberg reads its `[tool.iceberg]` table. |
| `--no-config` | Ignore all configuration files and use the default values. You cannot use it with `--config`. |
| `--max-workers N` | Replace `max_workers`. |
| `--exclude GLOB` | Add `GLOB` to `exclude`. iceberg compares `GLOB` with paths relative to the analyzed directory. You can give this option more than one time. |

```bash
iceberg src/mypkg --config ci/iceberg.toml --max-workers 4
iceberg src/mypkg --exclude legacy --exclude '**/*_pb2.py'
iceberg src/mypkg --no-config
```

## Configuration in Python

To use a configuration without a file, give a `Config` to `get_public_api`:

```python
import re
from pathlib import Path

from sheridan.iceberg import Config, get_public_api

config = Config(test_module_pattern=re.compile(r"_test\.py$"), exclude=("legacy",))
api = get_public_api(Path("src/mypkg"), config=config)
```
