# Case 11

Case 11: A package with an `__all__` that exports names that the analyzed source
does not define.

- The package re-exports `sqrt` and `Ordered` from the standard library.
- `json` is a re-exported module.
- A module-level `__getattr__` supplies `lazy_thing` at runtime.
- The package re-exports `area` from a private module in the same package.
  iceberg resolves `area` in the usual way.

## CLI Output
```console
$ iceberg cases/case_11
package case_11
├── def area(radius: float) -> float
├── from collections import OrderedDict as Ordered
├── import json
├── lazy_thing (unresolved)
└── from math import sqrt
```
- iceberg shows a name that it cannot connect to a definition as a `Reference`.
  It does not remove the name. Thus, the public API never becomes smaller
  silently.
- The output shows a reference as the import statement that binds it. If no
  import binds the name, the output shows `name (unresolved)`.
- `__getattr__` is private (its name starts with an underscore). The output does
  not show it.
- The output shows references after definitions, sorted by name.
