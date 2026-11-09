# Case 03

Case 03: You give a package path directly to iceberg.

- The init module is empty, or almost empty.
- The package has a subpackage `foo`.
  - The init module of `foo` is empty, or almost empty.

## CLI Output
```console
$ iceberg cases/case_03
package case_03
└── package case_03.foo
```
- There are no assignments, functions or classes under `package case_03`, because
  its init module is empty.
- There are no assignments, functions or classes under `package case_03.foo`,
  because its init module is empty.
