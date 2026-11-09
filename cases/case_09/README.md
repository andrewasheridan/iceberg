# Case 09

Case 09: You give a package path directly to iceberg.

- The package has three public modules that are not empty. Each module adds
  different content nodes to the tree.

## CLI Output
```console
$ iceberg cases/case_09
package case_09
├── module case_09.alpha
│   ├── def add(x: int, y: int) -> int
│   └── def subtract(x: int, y: int) -> int
├── module case_09.beta
│   └── class Counter
│       ├── def __init__(self, start: int = 0) -> None
│       ├── def increment(self) -> None
│       └── def value(self) -> int
└── module case_09.gamma
    ├── VERSION: str
    └── MAX_RETRIES: int
```
- The three modules have three different types of content: functions (`alpha`),
  a class with methods (`beta`) and assignments (`gamma`).
- In the package, iceberg sorts the modules by dotted name (`alpha`, then `beta`,
  then `gamma`).
- In a module, the formatter shows assignments, then classes, then functions. In
  a class, it shows nested classes, then assignments, then methods.
- The `__init__.py` is empty and has no `__all__`. Thus, the orchestrator uses
  the branch for packages without `__all__`. The output shows all the public
  regular modules. It does not show the init module separately.
