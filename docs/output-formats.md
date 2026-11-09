# Output formats

iceberg has two output formats:

- The tree format is the default. It is for people, and it is easy to read in a
  diff.
- The JSON format (`--json`) is for programs. Its output is deterministic.

Both formats go to stdout as UTF-8. To write the output to a file, give
`-o/--output PATH`.

## Tree format

The first line is the analyzed package or module. Below it, each line is one
public item. The lines use Unicode box-drawing characters to show the structure.

```console
$ iceberg cases/case_04/foo.py
module foo
├── corge
├── grault: TypeAlias
├── garply: TypeAlias
├── class Waldo
│   ├── class Fred
│   │   └── async def foo(self) -> None
│   ├── def __init__(self) -> None
│   ├── staticmethod def foo() -> None
│   ├── classmethod def bar(cls)
│   └── property baz: int
├── def foo()
├── async def bar() -> None
├── def baz() -> None
├── def qux(snap, crackle: int, pop = 'popped', **kwargs) -> None
└── def quux(*, crackle: int, pop: str = 'popped', snap: float, **kwargs: Any) -> None
```

In each module, the assignments come first. Then come the classes, the functions
and the references.

| Item | Line |
|---|---|
| Package | `package name` |
| Module | `module name` |
| Assignment | `name: annotation`, or `name` if there is no annotation |
| Class | `class Name`, or `class Name(bases, keywords)` |
| Function | `def name(parameters) -> returns`, or `async def ...` |
| Class method and static method | `classmethod def ...` and `staticmethod def ...` |
| Property | `property name: type` |
| Reference | The import that binds the name, for example `from math import sqrt` |
| Unresolved reference | `name (unresolved)` |

More rules:

- The tree shows keyword-only parameters in alphabetical order.
- The tree does not show property setters and deleters.
- A function with `typing.overload` signatures has one line for each overload.
  To show the implementation too, give `--show-overload-implementations`.
- If the `__init__.py` of a package defines `__all__`, iceberg moves the exported
  names up to the package. It does not show the private submodules.

## JSON format

`--json` prints one object for the analyzed package or module. The first key is
`schema_version`. This integer changes when a change to the format can break the
programs that read it. The current `schema_version` is 2.

```bash
iceberg src/mypkg --json -o api.json
```

Each object has a `node_type` field. This table shows the other fields of each
node type:

| `node_type` | Fields |
|---|---|
| `package` | `name`, `path`, `modules`, `subpackages` |
| `module` | `name`, `assignments`, `classes`, `functions`, `references` |
| `class` | `name`, `bases`, `keywords`, `assignments`, `methods`, `nested_classes` |
| `function` | `name`, `positional_parameters`, `keyword_parameters`, `var_positional`, `var_keyword`, `returns`, `is_async`, `kind`, `decorators`, `overloads` |
| `assignment` | `name`, `annotation` |
| `reference` | `name`, `module`, `attribute` |

The value of `kind` is `function`, `method`, `classmethod`, `staticmethod` or
`property`. A parameter is an object with the fields `name`, `annotation` and
`default`. If a value is not in the source, for example a missing annotation, the
value is `null`.

The `path` of a package is relative to the analyzed directory. Thus, the output is
the same on all computers.

With `--keep-going`, the output also has a top-level `diagnostics` list. For more
information, see the "Continue after bad files" section on the [home page](index.md).

This is a part of the output for `cases/case_11`:

```json
{
  "schema_version": 2,
  "node_type": "package",
  "name": "case_11",
  "path": ".",
  "modules": [
    {
      "node_type": "module",
      "name": "case_11",
      "assignments": [],
      "classes": [],
      "functions": [
        {
          "node_type": "function",
          "name": "area",
          "positional_parameters": [
            {
              "name": "radius",
              "annotation": "float",
              "default": null
            }
          ],
          "keyword_parameters": [],
          "var_positional": null,
          "var_keyword": null,
          "returns": "float",
          "is_async": false,
          "kind": "function",
          "decorators": [],
          "overloads": []
        }
      ],
      "references": [
        {
          "node_type": "reference",
          "name": "sqrt",
          "module": "math",
          "attribute": "sqrt"
        }
      ]
    }
  ],
  "subpackages": []
}
```

### Validate the JSON

The [JSON Schema](json-schema.md) page has a JSON Schema for this format. Use it to
validate a snapshot, or to make types for a program in a different language.

### Read the JSON in Python

`load_json` reads the JSON back into a `Package` or a `Module`:

```python
from pathlib import Path

from sheridan.iceberg import load_json

api = load_json(Path("api.json").read_text(encoding="utf-8"))
```
