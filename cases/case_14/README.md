# Case 14

Case 14: Functions and methods with `typing.overload` signatures:
- `area` and `Canvas.draw` each have two `@overload` signatures and an implementation

## CLI Output
```console
$ iceberg cases/case_14/shapes.py
module shapes
├── class Canvas
│   ├── def draw(self, shape: str) -> None
│   └── def draw(self, shape: str, color: str) -> None
├── def area(side: int) -> int
└── def area(width: float, height: float) -> float
```
- each overload signature gets one line; the implementation signature is hidden
- in JSON output the overloads are in the `overloads` list of one function

`--show-overload-implementations` adds the implementation signature after the overloads:

```console
$ iceberg cases/case_14/shapes.py --show-overload-implementations
module shapes
├── class Canvas
│   ├── def draw(self, shape: str) -> None
│   ├── def draw(self, shape: str, color: str) -> None
│   └── def draw(self, shape: str, color: str = 'black') -> None
├── def area(side: int) -> int
├── def area(width: float, height: float) -> float
└── def area(*args: float) -> float
```
