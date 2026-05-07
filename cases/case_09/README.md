# Case 09

Case 09: Passing a package path directly to iceberg:
- the package has three non-empty public modules, each contributing different
  content nodes to the rendered tree

```shell
$ cd cases
$ iceberg case_09
```

or

```shell
$ iceberg /Users/andrew/Projects/iceberg/cases/case_09
```

## CLI Output
```text
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
- three distinct content types across three modules: functions (`alpha`),
  a class with methods (`beta`), and assignments (`gamma`)
- modules are sorted by dotted name (`alpha` < `beta` < `gamma`) within
  the package
- each module's content renders in source order (assignments → classes →
  functions within a module; nested classes → assignments → methods within
  a class)
- the `__init__.py` is empty (no `__all__`) so the orchestrator uses the
  no-`__all__` branch: all public regular modules appear, init module is
  not listed separately
