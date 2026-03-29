# plugin/ — subpackage fixture

Static Python code used as an analysis target for `iceberg` functional tests.
This package is never imported or run — it is read purely as source by iceberg's AST walker.

## Structure

```
plugin/
├── __init__.py         no __all__; re-exports from core and formats
├── core/
│   └── __init__.py     __all__ = ["Plugin", "Registry"]; defines both classes
└── formats/
    ├── __init__.py     no __all__; re-exports from submodules
    ├── base.py         __all__ = ["BaseFormat"]
    └── json_fmt.py     __all__ = ["JsonFormat"]
```

## Key behaviors demonstrated

- **`core/__init__.py` has `__all__`** — iceberg treats it as authoritative for the entire
  `core/` subtree. No submodules of `core/` are reported separately (there are none here,
  but the suppression logic applies).
- **`formats/__init__.py` has no `__all__`** — iceberg does not suppress `formats/base.py`
  or `formats/json_fmt.py`. Each submodule is reported individually using its own `__all__`.
- **`plugin/__init__.py` has no `__all__`** — public names are AST-inferred from the
  `import X as X` re-export statements: `BaseFormat`, `JsonFormat`, `Plugin`, `Registry`.

## Expected `iceberg` output

Running `iceberg tests/examples/plugin/` produces:

```
plugin/
  __init__
    BaseFormat
    JsonFormat
    Plugin
    Registry
  core/
    __init__
      Plugin
        name: str
        version: str
        load(self) → bool
        unload(self) → None
      Registry
        register(self, plugin: Plugin) → None
        get(self, name: str) → Plugin | None
        all_plugins(self) → list[Plugin]
  formats/
    __init__
      BaseFormat
      JsonFormat
    base
      BaseFormat
        name: str
        serialize(self, data: object) → str
        deserialize(self, text: str) → object
    json_fmt
      JsonFormat
        indent: int
        serialize(self, data: object) → str
        deserialize(self, text: str) → object
```
