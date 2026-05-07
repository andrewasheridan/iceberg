# Case 02

Case 01: Passing a package path directly to iceberg:
- the init module is effectively empty
- the only non-init module is private

```shell
$ cd cases
$ iceberg case_02
```

or

```shell
$ iceberg /Users/andrew/Projects/iceberg/cases/case_02
```

## CLI Output
```text
package case_02
```
- no assignment/function/class content under `package case_02` because its init module is empty
- no modules because the only non-init module `case_02.__foo` is private
