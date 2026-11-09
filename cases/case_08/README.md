# Case 08

Case 08: You give a package path directly to iceberg.

- The package has a public subpackage (`pub/`) and a private subpackage (`_priv/`).
- The output must not show the private subpackage.

## CLI Output
```console
$ iceberg cases/case_08
package case_08
├── module case_08.helper
└── package case_08.pub
```
- `_priv/` is a valid Python package (it has `__init__.py`). But its name starts
  with `_`. Thus, `Package.is_public` returns `False`, and iceberg does not put
  it in `Package.subpackages` when it assembles the trie.
- This case is the package-level version of case_02, which removes a private
  *module*.
- `helper.py` is a public module. The output shows it together with the
  subpackage. In a package, the formatter shows modules before subpackages.
- The output has no content nodes, because all the init files and `helper.py`
  are empty.
