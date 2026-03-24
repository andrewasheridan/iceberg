# geometry — package with `__all__` in `__init__.py`

## Purpose

Demonstrates how `iceberg` behaves when a package's `__init__.py`
declares `__all__`. Because `__all__` is authoritative for the whole package,
running `iceberg geometry/` reports **only the `__init__` module** — the
four submodules are suppressed.

Running with `--use-ast` bypasses this: all four modules are reported
individually with full member detail.

This package is the **full typing** fixture: every parameter, return type,
and attribute carries an annotation. `iceberg` output includes `: type`
on all attributes and `→ return` on every callable.

## Structure

```
geometry/
├── __init__.py   # declares __all__ = ["Circle", "Point", "Rectangle", "distance"]
│                 # re-exports from submodules; no class/function definitions
├── point.py      # Point class — x/y instance attrs, translate(), distance_to()
├── shapes.py     # Circle and Rectangle — properties, classmethod, staticmethod
│                 # private _Shape base excluded from __all__ by leading underscore
└── utils.py      # distance() — public; _euclidean() — private helper, not in __all__
```

## What each file exercises

| File | Demonstrates |
|---|---|
| `__init__.py` | Re-export pattern; `__all__` suppressing submodule reporting |
| `point.py` | Simple class with typed instance attrs and instance methods |
| `shapes.py` | Class var, properties (`area`, `perimeter`), `@classmethod`, `@staticmethod`, private base class |
| `utils.py` | Module-level function; private helper excluded from public surface |

## iceberg output

**Without `--use-ast`** — only `__init__` shown, names have no detail (imports, not defs):
```
geometry/
  __init__
    Circle
    Point
    Rectangle
    distance
```

**With `--use-ast`** — all submodules shown with full signatures and member lists.
See `tests/expected/show/geometry_use_ast_tree.txt` for the full output.
