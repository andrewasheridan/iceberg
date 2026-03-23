# 0024. `show` Reports Function Signatures and Class Member Surfaces

Date: 2026-03-23
Status: Accepted

## Context

`show` was originally a name-only reporter: it listed the public top-level names of each module without describing what those names actually are. For `sheridan-diffract` to detect breaking changes correctly, a list of names is insufficient. Diffract needs to know whether a function's parameter names, types, or order changed; whether a required parameter was added or removed; whether a return type changed; and whether a class gained or lost public attributes or methods. Without this information, diffract could only detect additions and removals of top-level names, missing the large majority of real breaking changes.

## Decision

We decided to extend `show` to include rich structural information for public top-level functions and classes, derived entirely from static AST analysis with no importing of user code.

`ModuleInfo` gains two new fields: `function_signatures: dict[str, FunctionSignature]` keyed by function name, and `class_info: dict[str, ClassInfo]` keyed by class name. Both are populated during `walk_module`.

`FunctionSignature` captures, for each parameter: name, annotation, whether a default is present, and parameter kind (positional-only, positional-or-keyword, `*args`, keyword-only, `**kwargs`). It also captures the return annotation.

`ClassInfo` captures four member surfaces:

- **Class variables** — `ast.Assign` and `ast.AnnAssign` nodes at class body level whose names do not start with `_`.
- **Instance attributes** — `self.attr = ...` and `self.attr: T = ...` assignments in `__init__` whose names do not start with `_`.
- **Methods** — all `FunctionDef` and `AsyncFunctionDef` nodes at class body level not starting with `_`, excluding `__init__` itself, each with its full `FunctionSignature`.
- **Properties** — methods decorated with `@property`, capturing only the getter's return annotation. Setters and deleters (`@x.setter`, `@x.deleter`) are intentionally omitted: they are implementation detail of mutability and their presence or absence does not alter the getter's API contract.

Output is extended in both formats: tree format renders functions as `name(params) → return` and classes with an indented member list; JSON format adds a `detail` key mapping each public name that carries rich information to its structured representation. Names with no rich information (plain module-level variables) are absent from `detail`.

## Consequences

**Positive:**
- `sheridan-diffract` can drive granular breaking-change detection directly from `show --format json` output, with no need to duplicate AST walking logic.
- Parameter-level changes (added required param, renamed param, changed type annotation, changed return type) are now detectable without importing user code.
- Class-level changes (added or removed public attribute, method, or property) are similarly detectable.
- Setters and deleters are excluded, avoiding duplicate entries for the same property name and keeping the output focused on the API contract rather than implementation detail.

**Negative:**
- `ModuleInfo` is now a richer structure; consumers that previously iterated `public_api` by name only must handle the new fields.
- AST annotations are strings or `None` — they are not evaluated, so generic aliases and forward references appear as their literal source text. Diffract must treat annotation comparison as string equality.
- `show` output will grow in verbosity for modules with many public classes; tree format in particular becomes significantly longer.
