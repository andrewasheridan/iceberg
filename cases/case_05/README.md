# Case 05

Case 05: You give a package path directly to iceberg.

- The init module re-exports names from a private module in the same package
  (`_impl.py`).
- The init module defines `__all__` explicitly.

## CLI Output
```console
$ iceberg cases/case_05
package case_05
├── class Foo
│   ├── def __init__(self, value: int) -> None
│   └── def greet(self) -> str
└── def bar_func(x: int, y: int = 0) -> int
```
- `_impl.py` is private (its name starts with an underscore). The tree does not
  show it.
- Because the package defines `__all__`, the orchestrator moves all the resolved
  symbols up into `package case_05`. It does not list the submodules.
- The init resolver finds `Foo` and `bar_func` in the parsed `Module` of
  `_impl.py`. Then it attaches them directly to the init module.
- The resolver sorts the public names from `__all__` alphabetically (`Foo` before
  `bar_func`). Then the formatter shows the classes of each module before its
  functions.
