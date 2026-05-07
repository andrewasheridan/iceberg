# iceberg

Iceberg inspects and snapshots the public API surface of a Python package.

## Usage

### Programmatic use

```python
from pathlib import Path
from sheridan.iceberg import get_public_api

package = get_public_api(Path("src/mypkg"))
```

`get_public_api` returns a `Package` model describing every public module,
class, function, and assignment reachable from `src/mypkg`. An optional
`config` keyword argument accepts an explicit `Config`; when omitted, iceberg
walks up from the given path looking for `.iceberg.toml` or `pyproject.toml`.

### CLI

```
iceberg src/mypkg
iceberg src/mypkg --json
python -m sheridan.iceberg src/mypkg
```

Pass `--json` to receive machine-readable output. The default output is a
human-readable tree printed to stdout.
