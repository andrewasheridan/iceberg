# Case 08

Case 08: Passing a package path directly to iceberg:
- the package contains a public subpackage (`pub/`) and a private subpackage (`_priv/`)
- the private subpackage should be absent from the output

```shell
$ cd cases
$ iceberg case_08
```

or

```shell
$ iceberg /Users/andrew/Projects/iceberg/cases/case_08
```

## CLI Output
```text
package case_08
├── module case_08.helper
└── package case_08.pub
```
- `_priv/` is a valid Python package (it has `__init__.py`) but its name
  starts with `_`, so `Package.is_public` returns `False` and it is excluded
  from `Package.subpackages` during trie assembly
- this is the package-level analogue of case_02 (private *module* filtering)
- `helper.py` is a public module and appears in source-order alongside the
  subpackage; the formatter renders modules before subpackages within a package
- no content nodes appear anywhere because all init files and `helper.py` are empty
