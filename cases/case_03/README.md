# Case 03

Case 01: Passing a package path directly to iceberg:
- the init module is effectively empty
- a subpackage `foo` exists
  - It's init module is effectively empty

## CLI Output
```console
$ iceberg cases/case_03
package case_03
└── package case_03.foo
```
- no assignment/function/class content under `package case_03` because its init module is empty
- no assignment/function/class content under `package case_03.foo` because its init module is empty
