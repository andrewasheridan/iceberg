# Case 00

Case 00: Passing a single module directly to iceberg:
- the module is effectively empty

## CLI Output
```console
$ iceberg cases/case_00/foo.py
module foo
```
- no `package` level because iceberg was passed a single module
- no content because foo.py is empty
