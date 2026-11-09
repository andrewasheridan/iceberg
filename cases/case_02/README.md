# Case 02

Case 02: You give a package path directly to iceberg.

- The init module is empty, or almost empty.
- The package has one other module. This module is private.

## CLI Output
```console
$ iceberg cases/case_02
package case_02
```
- There are no assignments, functions or classes under `package case_02`, because
  its init module is empty.
- There are no modules, because the only other module, `case_02.__foo`, is private.
