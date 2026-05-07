# Case 06

Case 06: Passing a single module directly to iceberg:
- the module contains a class with class-level assignments (class variables)
- the class has both public and private (`_`-prefixed) members

```shell
$ cd cases/case_06
$ iceberg foo.py
```

or

```shell
$ iceberg /Users/andrew/Projects/iceberg/cases/case_06/foo.py
```

## CLI Output
```text
module foo
├── class Widget
│   ├── MAX_SIZE: int
│   ├── DEFAULT_NAME
│   ├── count: int
│   ├── def __init__(self, name: str = 'widget', size: int = 10) -> None
│   ├── def resize(self, new_size: int) -> None
│   └── def describe(self) -> str
└── def create_widget(name: str, size: int = 10) -> 'Widget'
```
- class-level assignments appear before methods in the rendered class body
  (formatter order: nested classes → assignments → methods)
- `_registry` and `_validate` are underscore-prefixed and are **filtered out**
  by the visitor — `_build_class` calls `.is_public` on every collected member
  before appending it, so any name starting with `_` (that is not a dunder) is
  excluded from the rendered output
- `__init__` is a dunder and is treated as public by `is_public`, so it is
  retained
- module-level privacy filtering works the same way: a top-level `_helper()`
  function would be absent, but there is none here
- `create_widget` has a forward-reference return annotation (`'Widget'`);
  `ast.unparse` renders string annotations with single quotes
