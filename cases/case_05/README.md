# Case 05

Case 05: Passing a package path directly to iceberg:
- the init module re-exports names from a private sibling module (`_impl.py`)
- `__all__` is defined explicitly

```shell
$ cd cases
$ iceberg case_05
```

or

```shell
$ iceberg /Users/andrew/Projects/iceberg/cases/case_05
```

## CLI Output
```text
package case_05
├── class Foo
│   ├── def __init__(self, value: int) -> None
│   └── def greet(self) -> str
└── def bar_func(x: int, y: int = 0) -> int
```
- `_impl.py` is private (underscore prefix) and is suppressed from the tree
- because `__all__` is defined, the orchestrator hoists all resolved symbols
  into `package case_05` entry instead of listing submodules
- the init resolver looks up `Foo` and `bar_func` in `_impl.py`'s parsed
  `Module` and attaches them directly to the init module
- public names resolved from `__all__` are sorted alphabetically by the
  resolver (`Foo` before `bar_func`); the formatter then renders classes
  before functions within the module
