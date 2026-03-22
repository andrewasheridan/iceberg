# 0021. Use `.yaml` Extension for All YAML Files

Date: 2026-03-22
Status: Accepted

## Context

YAML files appear throughout the project: `.github/workflows/`, `Taskfile.yaml`, `.pre-commit-config.yaml`, and `.pre-commit-hooks.yaml`. Both `.yml` and `.yaml` are valid and widely accepted. The `.yml` extension is a legacy abbreviation that originated with 8.3 filename limits on FAT filesystems — a constraint that has not been relevant for decades. The YAML specification authors prefer the full `.yaml` extension.

## Decision

We decided to use `.yaml` exclusively across all `sheridan.*` repos. The `.yml` extension is never used. This applies to all YAML files: workflow definitions, pre-commit config, task runners, and any tooling config that uses YAML syntax. Any existing `.yml` files must be renamed, and all references to YAML filenames in comments, badges, CI config, and documentation must reflect `.yaml`.

## Consequences

**Positive:**
- Consistent extension eliminates ambiguity when globbing (`**/*.yaml`), grepping, or configuring tools.
- `.yaml` is the full, unabbreviated form — self-documenting and unambiguous.
- Applied uniformly across all `sheridan.*` repos, reducing cognitive friction when switching between them.

**Negative:**
- Some tools and GitHub Actions UI defaults assume `.yml`; those cases require explicit path configuration or `workflow_call` overrides.
- Renaming existing `.yml` files requires updating all references to those filenames.
