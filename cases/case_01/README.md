# Case 01

Case 01: Passing a package path directly to iceberg:
- the init module is effectively empty
- the only non-init module is effectively empty

```shell
$ cd cases
$ iceberg case_01
```

or

```shell
$ iceberg /Users/andrew/Projects/iceberg/cases/case_01
```

## CLI Output
```text
package case_01
└── module case_01.foo
```
- no assignment/function/class content under `package case_01` because its init module is empty
- no content under `case_01.foo` because foo.py is empty
