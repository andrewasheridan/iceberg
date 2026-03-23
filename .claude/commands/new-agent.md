---
description: Scaffold a new agent file following project conventions
allowed-tools: Read, Glob, Write
---

Scaffold a new agent file in `.claude/agents/` following the project's conventions.

Arguments: $ARGUMENTS (format: `<agent-name> <role description>`)

## Steps

1. **Parse arguments** — Extract agent name (first word) and role description (remaining words) from `$ARGUMENTS`. If either is missing, ask the user:
   - "What should the agent be named?" (kebab-case, e.g. `security-scanner`)
   - "What is its role in one sentence?"

2. **Read existing agents** — Scan `/home/user/iceberg/.claude/agents/` to understand the existing roster and naming patterns. Read 1–2 similar agents for formatting reference.

3. **Determine model tier** — Choose based on task complexity:
   - **Haiku**: Simple, mechanical tasks — formatting, annotation adding, drafting structured records (like `docstring-writer`, `type-annotator`, `adr-writer`, `changelog-writer`)
   - **Sonnet**: Complex reasoning — code writing, test design, holistic review, multi-step analysis, research (like `code-writer`, `test-writer`, `reviewer`, `dependency-auditor`)
   - If unsure, ask the user.

4. **Determine tools** — Infer from the role which tools the agent needs. Common patterns:
   - Read-only analysis agents: `Read, Glob, Grep`
   - Writing agents: `Read, Glob, Grep, Write, Edit, Bash`
   - Research agents: `Read, Glob, Grep, WebSearch, WebFetch`
   - Orchestrating agents: `Agent` + others as needed
   - If ambiguous, ask the user.

5. **Scaffold the agent file** — Write `/home/user/iceberg/.claude/agents/<agent-name>.md` using this structure:

   ```markdown
   ---
   name: <agent-name>
   description: <one-line description>
   model: <haiku|sonnet>
   tools: <comma-separated tool list>
   ---

   <Role description — one paragraph explaining what this agent does and does NOT do.>

   ## Process

   1. **Step one** — ...
   2. **Step two** — ...
   3. **Verify** — Run `<verification command>` and fix any issues before reporting done.

   ## Rules

   - <Rule 1>
   - <Rule 2>

   ## Output

   <Description of what the agent reports back — format, level of detail, what it does/doesn't apply.>
   ```

6. **Remind the user** — After creating the file, display this reminder:

   > ⚠️  Two manual steps required:
   > 1. Add `<agent-name>` to the agent roster table in `CLAUDE.md`
   > 2. Add `<agent-name>` to the agent roster table in `.claude/agents/orchestrator.md`
   >
   > Do NOT skip these — the orchestrator will not know the agent exists until both are updated.
