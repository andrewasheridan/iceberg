# Case 03

Case 01: Passing a package path directly to iceberg:
- the init module is effectively empty
- a subpackage `foo` exists
  - It's init module is effectively empty

```shell
$ cd cases
$ iceberg case_03
```

or

```shell
$ iceberg /Users/andrew/Projects/iceberg/cases/case_03
```

## CLI Output
```text
package case_03
└── package case_03.foo
```
- no assignment/function/class content under `package case_03` because its init module is empty
- no assignment/function/class content under `package case_03.foo` because its init module is empty
