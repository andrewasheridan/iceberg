# Case 15

Case 15: A package that adds to `__all__` inside a `try` / `except ImportError`
block, the usual pattern for optional speed-ups:
- `__init__.py` sets `__all__ = ["slow"]`
- inside `try:` it imports `fast` from `_speedups` and calls `__all__.append("fast")`
- `except ImportError:` does nothing

## CLI Output
```console
$ iceberg cases/case_15
package case_15
├── def fast(data: list[int]) -> int
└── def slow(data: list[int]) -> int
```
- changes to `__all__` inside module-level `if` / `try` blocks are applied
- which branch runs is unknown statically, so `__all__` keeps every name that
  any branch adds; here both `slow` and `fast` are public
