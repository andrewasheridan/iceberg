---
description: Full quality sweep — complexity, dead code, and code review
allowed-tools: Agent, Glob, Read
---

Run a quality sweep on the codebase using three analysis agents in sequence: complexity-reducer, dead-code-detector, and reviewer.

## Steps

1. **Identify scope** — Default target is `src/` at `/home/user/iceberg/src/`. If `$ARGUMENTS` specifies a path, use that instead.

2. **Complexity analysis** — Invoke the `complexity-reducer` agent on the target files with full context about the project structure. Collect its report.

3. **Dead code detection** — Invoke the `dead-code-detector` agent on the target files and tests directory. Collect its report.

4. **Code review** — Invoke the `reviewer` agent on the target files. Collect its report.

5. **Consolidated summary** — Present findings in three labelled sections:

   ### Complexity
   (findings from complexity-reducer)

   ### Dead Code
   (findings from dead-code-detector)

   ### Review Findings
   (findings from reviewer)

6. **Actionable checklist** — End with a prioritised checklist of the top issues to address, numbered by severity (correctness/security first, then quality, then style).

Note: These agents report only — they do not apply changes. Use `/new-feature` or ask directly to address specific findings.
