# Case 00

Case 00: Passing a single module directly to iceberg:
- the module has content

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
- no `package` level because iceberg was passed a single module
- include each of the pertinent lines
- properties, classmethods and staticmethods are labeled with their kind; the `baz` setter adds no extra line
-
