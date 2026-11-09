# Case 12

Case 12: A package that binds its re-exports in `try` / `except` blocks. Packages
frequently do this for optional accelerators and for generated version files.

## CLI Output
```console
$ iceberg cases/case_12
package case_12
├── version: str
└── def parse(text: str) -> list[str]
```
- Imports in module-level `if` and `try` blocks also make module globals. Thus,
  the init resolver follows them.
- If more than one branch binds a name, iceberg uses the first binding in the
  source. Thus, `parse` resolves to `_fast.parse`, not to the `_slow` fallback.
