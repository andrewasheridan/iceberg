# Case 13

Case 13: You give iceberg a package in a namespace package. The package
re-exports names through absolute imports that include the full namespace.

- `acme/` is a namespace package (it has no `__init__.py`).
- `acme/widgets/__init__.py` contains `from acme.widgets._core import make_widget`.

## CLI Output
```console
$ iceberg cases/case_13/src/acme/widgets
package widgets
└── def make_widget(name: str) -> str
```
- iceberg uses the path that you give it. Thus, the name of the root package is
  `widgets`.
- The import starts with `acme.widgets._core`. `acme` is the same as the name of
  the directory directly above the root. Thus, iceberg removes this prefix and
  resolves the import as `widgets._core`.

If you give iceberg the namespace package, the output shows the same symbols
under `package acme.widgets`:

```console
$ iceberg cases/case_13/src/acme
package acme.widgets
└── def make_widget(name: str) -> str
```
