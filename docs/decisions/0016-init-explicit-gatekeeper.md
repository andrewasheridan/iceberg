# 0016. `__init__.py` is the explicit gatekeeper for package public API

Date: 2026-03-21
Status: Accepted

## Context

The question arose whether iceberg should include submodule names in the inferred `__all__` of `foo/__init__.py` simply because they exist as sibling `.py` files with a public (non-underscore) name.

Two options were considered:

- **Option A (filesystem-aware):** scan sibling `.py` files and automatically include public-named submodules in the inferred `__all__` of `__init__.py`
- **Option B (explicit gatekeeper):** only count submodules that the author has explicitly imported into `__init__.py`

## Decision

We chose Option B. `__init__.py` is the explicit gatekeeper for a package's public API. A submodule or subpackage (e.g. `foo/snap.py`) is only included in the inferred `__all__` of `foo/__init__.py` if it is explicitly imported there — for example, `from foo import snap` or `from foo.snap import SomeClass`. This is already handled by ADR-0013's from-import inference.

## Consequences

**Positive:**

- The absence of a leading underscore on a module filename does not imply intent to publish. Many packages have internal helpers that happen to be un-prefixed. Requiring an explicit import prevents false positives.
- Keeps AST analysis decoupled from filesystem structure. The walker does not need to correlate sibling files with the module under analysis.
- Authors retain full control: adding `from foo import snap` to `__init__.py` is both the signal to iceberg and the correct Python idiom for re-exporting a submodule.

**Negative:**

- A package author who forgets to import a genuinely public submodule in `__init__.py` will not be warned by iceberg — it is not iceberg's job to infer intent from filenames alone.
