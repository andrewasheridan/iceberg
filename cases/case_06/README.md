# Case 06

Case 06: You give one module directly to iceberg.

- The module has a class with class-level assignments (class variables).
- The class has public members and private members (with a `_` prefix).

## CLI Output
```console
$ iceberg cases/case_06/foo.py
module foo
├── class Widget
│   ├── MAX_SIZE: int
│   ├── DEFAULT_NAME
│   ├── count: int
│   ├── def __init__(self, name: str = 'widget', size: int = 10) -> None
│   ├── def resize(self, new_size: int) -> None
│   └── def describe(self) -> str
└── def create_widget(name: str, size: int = 10) -> Widget
```
- The class body shows class-level assignments before methods. The formatter uses
  this order: nested classes, then assignments, then methods.
- The names `_registry` and `_validate` start with an underscore. The visitor
  **removes** them. `_build_class` calls `.is_public` on each member before it
  adds the member. Thus, the output does not show a name that starts with `_`,
  unless the name is a dunder.
- `__init__` is a dunder, and `is_public` makes it public. Thus, the output keeps
  it. The output also keeps all other dunder members (`__call__`, `__eq__`,
  `__slots__` and others). It removes name-mangled members such as `__secret`.
- iceberg uses the same rule for single-underscore names at module level. For
  example, the output does not show a top-level function `_helper()`. This case
  has no such function.
- A module-level dunder such as `__version__` is public only if `__all__` lists it.
- `create_widget` returns `Widget`. The formatter uses `ast.unparse` for
  annotations. Thus, the annotations are the same as in the source.
