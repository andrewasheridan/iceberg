# Case 11

Case 11: A package whose `__all__` exports names that are not defined in the
analyzed source:
- `sqrt` and `Ordered` are re-exported from the standard library
- `json` is a re-exported module
- `lazy_thing` is provided at runtime by a module-level `__getattr__`
- `area` is re-exported from a private sibling module (resolved normally)

```shell
$ iceberg cases/case_11
```

## CLI Output
```text
package case_11
├── def area(radius: float) -> float
├── from collections import OrderedDict as Ordered
├── import json
├── lazy_thing (unresolved)
└── from math import sqrt
```
- names iceberg cannot resolve to a definition are reported as `Reference`
  entries instead of being dropped, so the public surface never silently
  shrinks
- a reference is rendered as the import statement that binds it; when no
  import binds the name it is shown as `name (unresolved)`
- `__getattr__` is private (underscore prefix) and is not reported
- references are listed after definitions, sorted by name
