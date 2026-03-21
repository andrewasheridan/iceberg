---
name: adr-writer
description: Writes Architecture Decision Records to /docs/decisions/. Use whenever a significant architectural decision is made.
---

Write an ADR (Architecture Decision Record) to `docs/decisions/` based on the decision described.

File naming: `docs/decisions/NNNN-short-title.md` where `NNNN` is the next sequential number. Check the directory for the current highest number.

ADR format:

```markdown
# NNNN. Title

Date: YYYY-MM-DD
Status: Accepted

## Context

What situation or problem prompted this decision?

## Decision

What was decided?

## Consequences

What are the positive and negative consequences of this decision?
```

Rules:
- Be concise — ADRs should be scannable in 2 minutes
- Focus on *why*, not *what* (the code explains the what)
- Use past tense for the decision ("We decided to...", "We chose...")
- Do not pad with filler. If context is obvious, keep it brief.
