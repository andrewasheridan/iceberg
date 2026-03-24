# tests/examples

Static Python code used as analysis targets by `iceberg` functional tests.
None of these packages are installed or imported at test time — they are read
purely as source files by iceberg's AST walker.

## Examples

| Example | Kind | Typing | Key behaviour demonstrated |
|---|---|---|---|
| [`standalone.py`](standalone.py) | Single module | Full | Every member kind `iceberg` can report |
| [`geometry/`](geometry/) | Package with `__all__` in `__init__.py` | Full | `__init__.__all__` suppresses submodule reporting |
| [`warehouse/`](warehouse/) | Package without `__all__` in `__init__.py` | Partial | All submodules reported individually; mix of typed and untyped members |
| [`todo.py`](todo.py) | Single module | None | Zero annotations — bare names only in output |
| [`plugin/`](plugin/) | Nested subpackages | Full | Nested subpackages; mix of `__all__`-controlled and AST-inferred modules |

## How golden files relate to these examples

Expected outputs live in `tests/expected/show/`. Each golden file corresponds
to one `iceberg` invocation against one of these examples:

```
standalone_tree.txt          iceberg tests/examples/standalone.py
standalone_json.json         iceberg tests/examples/standalone.py --format json
geometry_tree.txt            iceberg tests/examples/geometry/
geometry_json.json           iceberg tests/examples/geometry/ --format json
geometry_use_ast_tree.txt    iceberg tests/examples/geometry/ --use-ast
geometry_use_ast_json.json   iceberg tests/examples/geometry/ --use-ast --format json
warehouse_tree.txt           iceberg tests/examples/warehouse/
warehouse_json.json          iceberg tests/examples/warehouse/ --format json
todo_tree.txt                iceberg tests/examples/todo.py
todo_json.json               iceberg tests/examples/todo.py --format json
```

To update a golden file after intentionally changing a fixture, run the
relevant `iceberg` command from the project root and redirect its output
to the corresponding file in `tests/expected/show/`.
