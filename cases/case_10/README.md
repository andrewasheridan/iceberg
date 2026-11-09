# Case 10

Case 10: You give iceberg a source root that contains a namespace package.

- `acme/` is a namespace package (PEP 420). It has **no** `__init__.py`.
- `acme/widgets/` is a regular package. It has an empty `__init__.py`.
- `acme/widgets/core.py` has one public function.

## CLI Output
```console
$ iceberg cases/case_10/src/acme
package acme.widgets
└── module acme.widgets.core
    └── def make_widget(name: str) -> str
```

- `cases/case_10/src` has no `__init__.py`. Thus, iceberg uses it as the root
  directory, not as a package, and starts the discovery there.
- `acme/` also has no `__init__.py`, so it is a namespace package. iceberg
  accepts it as a package component because its name is a valid Python
  identifier. iceberg does not look for an `__init__.py`.
- iceberg goes up from `core.py` and collects `['acme', 'widgets']` as path parts.
  Then it makes the dotted name `acme.widgets`.
- Because `acme/` has no `__init__.py`, it has no init module. The tree does not
  show it as a separate node. The tree shows only the innermost regular package,
  `acme.widgets`.
- `make_widget` is public (its name does not start with an underscore). The tree
  shows it under its module.
