# 0008. Curated Agent Roster

Date: 2026-03-21
Status: Accepted

## Context

Claude Code supports sub-agents that can be invoked by an orchestrator session to perform specialized tasks. Without a policy, agents could be generated ad hoc to fill gaps, leading to inconsistent behavior, duplicated conventions, and agents that conflict with each other or with project standards.

## Decision

Agents are curated, not generated on the fly. All agents live in `.claude/agents/`. When the orchestrator encounters a task that requires an agent not present in that directory, it stops and raises a clear error describing what agent is needed and why — it does not improvise or create a new agent to proceed.

Agent system prompts describe only role-specific behavior. Project-wide conventions (language, types, formatting, testing, tooling) are inherited automatically from `CLAUDE.md` and must not be restated in agent prompts.

New agents are added deliberately, reviewed as part of the codebase, and documented in the agent roster in `CLAUDE.md`.

## Consequences

- The agent roster is explicit and version-controlled. Every agent's scope and purpose is visible in `CLAUDE.md`.
- Agent system prompts stay focused and non-redundant. Conventions are defined once in `CLAUDE.md`.
- Missing-agent errors are loud and actionable rather than silently papered over by improvised agents.
- Adding a new capability requires a deliberate decision rather than an implicit one, keeping the roster coherent over time.
