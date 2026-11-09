# Case 01

Case 01: You give a package path directly to iceberg.

- The init module is empty, or almost empty.
- The package has one other module. This module is also empty, or almost empty.

## CLI Output
```console
$ iceberg cases/case_01
package case_01
└── module case_01.foo
```
- There are no assignments, functions or classes under `package case_01`, because
  its init module is empty.
- There is no content under `case_01.foo`, because `foo.py` is empty.
