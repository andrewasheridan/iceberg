# Case 10

Case 10: Passing a source root containing a namespace package to iceberg:
- `acme/` is a namespace package (PEP 420) — it has **no** `__init__.py`
- `acme/widgets/` is a regular package — it has an empty `__init__.py`
- `acme/widgets/core.py` contains a single public function

```shell
$ iceberg /Users/andrew/Projects/iceberg/cases/case_10/src/acme
```

## CLI Output
```text
package acme.widgets
└── module acme.widgets.core
    └── def make_widget(name: str) -> str
```

- `cases/case_10/src` itself has no `__init__.py`, so iceberg treats it as the
  root directory rather than a package and begins discovery from there
- `acme/` has no `__init__.py` either, making it a namespace package; iceberg
  identifies it as a valid package component using identifier validation
  (checking that the directory name is a legal Python identifier) rather than
  requiring `__init__.py` presence
- walking up from `core.py`, iceberg collects `['acme', 'widgets']` as path
  parts and assembles the dotted name `acme.widgets`
- because `acme/` has no `__init__.py` it produces no init module of its own
  and does not appear as a standalone node in the tree; only the innermost
  regular package `acme.widgets` is rendered
- `make_widget` is public (no underscore prefix) and appears under its
  containing module
