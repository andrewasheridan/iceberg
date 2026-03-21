# 0004. No Git Awareness in iceberg

Date: 2026-03-21
Status: Accepted

## Context

`sheridan-iceberg` analyzes Python modules to enforce correct `__all__` declarations. A natural extension would be to compare API surfaces across git commits to infer semantic version bump types. This capability requires git awareness: checking out commits, diffing module states, and classifying changes.

## Decision

`iceberg` has no knowledge of git. It operates purely on the filesystem, analyzing whatever source files are present at the path it is given. Git operations — checking out commits, walking history, diffing API surfaces across revisions — belong exclusively to `sheridan-diffract`, a sibling tool that depends on `iceberg`.

## Consequences

- `iceberg` remains a focused, composable tool with a single responsibility: API surface extraction and `__all__` enforcement.
- `iceberg` has no dependency on `gitpython`, `pygit2`, or any git library, keeping its dependency footprint minimal.
- `sheridan-diffract` can invoke `iceberg` at any commit by checking out that commit itself before calling `iceberg` on the resulting filesystem state.
- Users who only need `__all__` enforcement do not pull in git-related dependencies.
- Any future tool that needs API surface data can depend on `iceberg` without inheriting git complexity.
