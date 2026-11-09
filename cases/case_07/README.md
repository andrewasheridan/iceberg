# Case 07

Case 07: You give one module directly to iceberg.

- The module has functions with parameter forms that case_04 does not have:
  positional-only parameters (the `/` separator) and `*args` (var-positional).

## CLI Output
```console
$ iceberg cases/case_07/foo.py
module foo
├── def make_point(x: float, y: float, label: str = '') -> str
├── def join_strings(*parts: str, separator: str = ', ') -> str
├── def format_record(id: int, *fields: str, prefix: str = '', sep: str = '|') -> str
└── def full_spectrum(a: int, b: int, c: int, *args: float, key: str = 'x', **kwargs: bool) -> None
```
- iceberg keeps positional-only parameters (before the `/` separator) in
  `Function.positional_parameters`, together with the usual positional parameters.
- The model and the output do not show the `/` boundary. Thus, `x` and `y` look
  the same as usual positional parameters.
- `*parts` shows as `*parts: str`. If `var_positional` is not None, the formatter
  adds the `*` prefix.
- In each function, iceberg sorts the keyword-only parameters after `*args`
  alphabetically. `separator` is the only keyword-only parameter in
  `join_strings`.
- In `format_record`, `*fields` is the var-positional parameter. `prefix` and
  `sep` are keyword-only, and iceberg sorts them alphabetically (`prefix` before
  `sep`).
- In `full_spectrum`, `a`, `b` and `c` are all positional (the positional-only
  boundary is not visible). `*args` is the var-positional parameter, `key` is
  keyword-only and `**kwargs` is var-keyword.
