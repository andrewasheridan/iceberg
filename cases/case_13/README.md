# Case 13

Case 13: Pointing iceberg at a package inside a namespace package, where the
package re-exports through absolute imports that spell the full namespace:
- `acme/` is a namespace package (no `__init__.py`)
- `acme/widgets/__init__.py` does `from acme.widgets._core import make_widget`

```shell
$ iceberg cases/case_13/src/acme/widgets
```

## CLI Output
```text
package widgets
└── def make_widget(name: str) -> str
```
- iceberg trusts the path it is given, so the root package is named `widgets`
- the import says `acme.widgets._core`; because `acme` matches the directory
  directly above the root, iceberg strips that prefix and resolves the import
  against `widgets._core`
- running `iceberg cases/case_13/src/acme` instead produces the same symbols
  under `package acme.widgets`
