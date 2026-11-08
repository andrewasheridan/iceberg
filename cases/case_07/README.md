# Case 07

Case 07: Passing a single module directly to iceberg:
- the module contains functions that exercise parameter forms not covered by case_04:
  positional-only parameters (the `/` separator) and `*args` (var-positional)

```shell
$ cd cases/case_07
$ iceberg foo.py
```

or

```shell
$ iceberg /Users/andrew/Projects/iceberg/cases/case_07/foo.py
```

## CLI Output
```text
module foo
├── def make_point(x: float, y: float, label: str = '') -> str
├── def join_strings(*parts: str, *, separator: str = ', ') -> str
├── def format_record(id: int, *fields: str, prefix: str = '', sep: str = '|') -> str
└── def full_spectrum(a: int, b: int, c: int, *args: float, *, key: str = 'x', **kwargs: bool) -> None
```
- positional-only parameters (`/` separator) are stored in
  `Function.positional_parameters` alongside regular positional params —
  the `/` boundary is not represented in the model or rendered in the output;
  `x`, `y` look identical to ordinary positional params
- `*parts` renders as `*parts: str` (the `*` prefix is added by the formatter
  when `var_positional` is not None)
- keyword-only params after `*args` sort alphabetically within each function;
  `separator` is the only keyword-only param in `join_strings`
- `format_record` has `*fields` as var-positional; `prefix` and `sep` are
  keyword-only and sort alphabetically (`prefix` before `sep`)
- `full_spectrum`: `a`, `b`, `c` are all positional (positional-only boundary
  invisible); `*args` triggers the var-positional branch; `key` is keyword-only;
  `**kwargs` is var-keyword
