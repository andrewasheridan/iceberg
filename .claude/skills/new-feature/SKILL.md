---
description: Full new-feature pipeline — implement, document, type-check, test, and review
allowed-tools: Agent, Read, Edit, Write
---

Implement a new feature end-to-end using the full agent pipeline.

Feature description: $ARGUMENTS

## Steps

If `$ARGUMENTS` is empty, ask: "What feature would you like to implement?"

Run the following agents **in order** — each must complete before the next starts:

1. **code-writer** — Implement the feature described in `$ARGUMENTS`. Provide full context: project root is `/home/user/iceberg/`, source is in `src/sheridan/iceberg/`, the project uses Python 3.14+, mypy --strict, ruff, and pytest. Pass the feature description and any relevant existing file paths.

2. **docstring-writer** — Add or fix Google-style docstrings on all new and modified files from step 1. Pass the list of files that were created or modified.

3. **type-annotator** — Ensure all new code has complete mypy --strict type annotations. Pass the same file list. (Skip if code-writer already confirmed full annotation coverage.)

4. **test-writer** — Write pytest tests for the implementation. Target 90%+ branch coverage. Pass the implementation files and their paths.

5. **reviewer** — Advisory review of all files written across steps 1–4. Pass the complete list of new/modified files and their contents.

## After the pipeline

Check the reviewer's mandatory follow-up checklist:
- **ADR needed?** If a significant architectural decision was made (new pattern, technology choice, structural trade-off), invoke `adr-writer`.
- **CLAUDE.md update needed?** If the public API, CLI flags, commands, agent roster, or conventions changed, update `/home/user/iceberg/CLAUDE.md` directly.
- **README.md update needed?** If user-facing behaviour, install steps, or CLI usage changed, update `/home/user/iceberg/README.md` directly.

## Final report

Summarise:
- Files created
- Files modified
- Test coverage achieved
- Any follow-up actions taken (ADR created, CLAUDE.md updated, etc.)
