# Type Info and Signatures for `__all__` Members

**Date:** 2026-03-28
**Status:** Approved

## Problem

When a module declares `__all__`, iceberg reports the listed names but without
type annotations or function signatures. Two gaps cause this:

1. **Variables** (e.g., `__version__: str`) have no extraction path. The walker
   collects function signatures and class info but ignores variable type
   annotations entirely.

2. **Re-exported names** (e.g., `from .api import get_public_api` in
   `__init__.py`) are not defined in the importing module's AST, so the walker
   has no local definition to extract a signature from.

The result is bare names in the output where rich type information could appear.

## Decisions

- Extract variable type annotations from `ast.AnnAssign`. Unannotated variables
  are flagged `(untyped)` in tree output.
- Resolve re-exports using Option A: a library-level post-processing pass after
  all modules are parsed. Direct intra-package imports only; no transitive
  chains, no wildcards, no external dependencies.
- The new pass slots between `load_modules` and `resolve_show_modules` in the
  pipeline.

## Design

### Model Changes

`ModuleInfo` gains one field:

```python
variable_types: dict[str, str | None]
```

Maps variable name to annotation string (from `ast.AnnAssign`) or `None`
(bare `ast.Assign`, no annotation). Only populated for names not already in
`function_signatures` or `class_info`.

### Variable Extraction in `walk_module`

After the existing function/class extraction loop, a second pass over top-level
nodes builds `variable_types`:

- `ast.AnnAssign(target=Name(id=name))` with annotation present:
  `variable_types[name] = ast.unparse(annotation)`
- `ast.Assign(targets=[Name(id=name)])` (single-target only):
  `variable_types[name] = None`
- Skip names already in `function_signatures` or `class_info`.
- Skip `__all__` itself.
- No underscore filter: extract all top-level variables. The consumer decides
  what to display via `effective_all`. This ensures `__version__` (which starts
  with `_`) is captured.

### Re-export Resolution Pass

New function in `ast_walker.py`:

```python
def resolve_reexports(modules: list[ModuleInfo]) -> list[ModuleInfo]
```

Called from `get_public_api` after `load_modules`, before
`resolve_show_modules`.

For each `__init__.py` module:

1. Re-parse its AST (source available via `info.path`) to find `from X import Y`
   statements.
2. Build a mapping: `{local_name: (source_module_path, original_name)}`.
3. For each name in `effective_all` that has no entry in `function_signatures`,
   `class_info`, or `variable_types`: look up the source module in the parsed
   set and copy its `FunctionSignature`, `ClassInfo`, or variable type entry.
4. Mutate in place and return.

**Scope limits:**

- Only `from X import Y` (not `import X`).
- Only explicit names (not `from X import *`).
- Only intra-package (source module must be in the parsed set).
- No transitive resolution.
- Handles `as` aliases: `from X import Y as Z` maps local name `Z` to source
  name `Y`.

### CLI Rendering Changes

**Tree output (`_format_tree`):**

The name rendering loop gains a new branch between `class_info` and the bare
fallback:

```
if name in function_signatures   -> render with signature (existing)
elif name in class_info           -> render with members (existing)
elif name in variable_types:
    if annotation is not None     -> "name: annotation"
    else                          -> "name (untyped)"
else                              -> bare name (fallback)
```

**JSON output (`_build_detail`):**

Variables are added to the detail map:

```json
{
  "__version__": {"kind": "variable", "annotation": "str"},
  "FOO": {"kind": "variable", "annotation": null}
}
```

### Pipeline

```
load_modules(path)
    |
resolve_reexports(modules)      <- NEW
    |
resolve_show_modules(modules, use_ast)
    |
build module_id dict -> return
```

## Expected Output

Before:

```
iceberg
  __init__
    __version__
    get_public_api
```

After:

```
iceberg
  __init__
    __version__: str
    get_public_api(path: Path | str, *, use_ast: bool = ...) → dict[str, ModuleInfo]
```

## Files Changed

| File | Change |
|------|--------|
| `src/sheridan/iceberg/models.py` | Add `variable_types` field to `ModuleInfo` |
| `src/sheridan/iceberg/ast_walker.py` | Extract variable types in `walk_module`; add `resolve_reexports` |
| `src/sheridan/iceberg/api.py` | Call `resolve_reexports` in pipeline |
| `src/sheridan/iceberg/cli.py` | Add variable rendering in `_format_tree` and `_build_detail` |
| `tests/` | Update golden files; add unit tests for new behavior |

No new files created. No new dependencies.
