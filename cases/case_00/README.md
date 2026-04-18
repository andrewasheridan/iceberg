# Case 00

Case 00: Passing a single module directly to iceberg:
- the module is effectively empty

```shell
$ cd cases/case_00
$ iceberg foo.py
```

or

```shell
$ iceberg /Users/andrew/Projects/iceberg/cases/case_00/foo.py
```

## CLI Output
```text
module empty_module
```
- no `package` level because iceberg was passed a single module
- no content because foo.py is empty
