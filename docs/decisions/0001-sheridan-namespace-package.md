# 0001. Sheridan Namespace Package

Date: 2026-03-21
Status: Accepted

## Context

The `sheridan` toolchain is a family of related developer tools (`iceberg`, `diffract`, and others). Each tool is distributed as a separate PyPI package but shares a common `sheridan` namespace. A decision was needed on how to structure the Python namespace so that tools are independently installable yet addressable under a unified top-level name.

PEP 420 implicit namespace packages allow multiple separately-installed distributions to contribute to the same top-level Python package without a shared `__init__.py`. This is the standard mechanism for namespace packages in modern Python.

## Decision

All tools in the `sheridan` family use an implicit namespace package rooted at `sheridan`. Concretely:

- There is no `src/sheridan/__init__.py`. The namespace is implicit (PEP 420).
- This package is distributed on PyPI as `sheridan-iceberg` and imported as `sheridan.iceberg`.
- Sibling tools (e.g. `sheridan-diffract`) follow the same convention, contributing to the `sheridan` namespace from their own distributions.
- The `src/` layout is used; the namespace root is `src/sheridan/`.

## Consequences

- Any number of `sheridan.*` tools can be installed independently or together without namespace conflicts.
- There must be no `src/sheridan/__init__.py` in any distribution in the family. Adding one would break the implicit namespace for all co-installed siblings.
- `pyproject.toml` must declare the package using `packages = [{include = "sheridan", from = "src"}]` or equivalent, and packaging tooling must be configured to avoid generating a top-level `__init__.py` for the namespace root.
- Users import tools as `sheridan.iceberg`, `sheridan.diffract`, etc., which communicates family membership clearly.
