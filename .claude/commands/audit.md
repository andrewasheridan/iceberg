---
description: Audit a proposed new dependency via the dependency-auditor agent
allowed-tools: Agent
---

Audit the package named in $ARGUMENTS using the dependency-auditor agent.

## Steps

1. **Get package name** — Use `$ARGUMENTS` as the package name to audit. If `$ARGUMENTS` is empty, ask: "Which package would you like to audit?"

2. **Delegate to dependency-auditor** — Invoke the `dependency-auditor` agent with this context:
   - Package to audit: the name from `$ARGUMENTS`
   - Project type: Python, using `uv` for dependency management
   - Config file: `/home/user/iceberg/pyproject.toml`
   - Strong stdlib preference — external dependencies only if stdlib alternative is significantly more complex

3. **Report the verdict** — Present the agent's APPROVED or REJECTED decision, its one-paragraph justification, and any suggested alternative if rejected.
