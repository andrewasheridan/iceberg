# Case 12

Case 12: A package that binds its re-exports inside `try` / `except` blocks,
a common pattern for optional accelerators and generated version files.

```shell
$ iceberg cases/case_12
```

## CLI Output
```text
package case_12
├── version: str
└── def parse(text: str) -> list[str]
```
- imports nested in module-level `if` / `try` blocks are still module globals,
  so the init resolver follows them
- when a name is bound in several branches, the first binding in source order
  wins: `parse` resolves to `_fast.parse`, not the `_slow` fallback
