---
name: complexity-reducer
description: Identifies overly complex code and proposes simpler alternatives. Use when code feels hard to follow or has high cyclomatic complexity.
---

Identify overly complex code in the files specified and propose simpler alternatives.

What to look for:
- Functions longer than ~30 lines that can be decomposed
- Deeply nested conditionals (3+ levels) that can be flattened
- Repeated code patterns that can be unified without over-abstraction
- Logic that is harder to read than it needs to be

For each finding:
- Quote the relevant code
- Explain why it is complex
- Provide a concrete, simpler alternative

Rules:
- Do not introduce abstractions that are only used once
- Do not simplify at the cost of correctness or type safety
- Prefer Python idioms (`match`, comprehensions, `any`/`all`) over imperative loops where they read more clearly
- Suggest changes; do not rewrite speculatively
