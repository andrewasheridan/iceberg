# Case 15

Case 15: A package that adds to `__all__` in a `try` / `except ImportError`
block. Packages usually do this for optional speed-ups.

- `__init__.py` sets `__all__ = ["slow"]`.
- In `try:`, it imports `fast` from `_speedups` and calls `__all__.append("fast")`.
- `except ImportError:` does nothing.

## CLI Output
```console
$ iceberg cases/case_15
package case_15
├── def fast(data: list[int]) -> int
└── def slow(data: list[int]) -> int
```
- iceberg applies the changes to `__all__` in module-level `if` and `try` blocks.
- iceberg does not run the code, so it cannot know which branch runs. Thus,
  `__all__` keeps each name that a branch adds. Here, `slow` and `fast` are both
  public.
