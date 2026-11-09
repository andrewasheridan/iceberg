# Case 04

Case 04: You give one module directly to iceberg.

- The module has content.

## CLI Output
```console
$ iceberg cases/case_04/foo.py
module foo
├── corge
├── grault: TypeAlias
├── garply: TypeAlias
├── class Waldo
│   ├── class Fred
│   │   └── async def foo(self) -> None
│   ├── def __init__(self) -> None
│   ├── staticmethod def foo() -> None
│   ├── classmethod def bar(cls)
│   └── property baz: int
├── def foo()
├── async def bar() -> None
├── def baz() -> None
├── def qux(snap, crackle: int, pop = 'popped', **kwargs) -> None
└── def quux(*, crackle: int, pop: str = 'popped', snap: float, **kwargs: Any) -> None
```
- There is no `package` level, because you gave iceberg one module.
- The output includes each applicable line.
- iceberg puts the kind before properties, classmethods and staticmethods. The
  setter of `baz` does not add a line.
