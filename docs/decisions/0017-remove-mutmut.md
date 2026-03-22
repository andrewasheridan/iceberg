# 0017. Remove mutmut — Python 3.14 incompatibility

Date: 2026-03-21
Status: Superseded

## Context

mutmut was part of the project toolchain for mutation testing. Python 3.14 broke it in two distinct ways, one per major version:

**mutmut 2.x** uses pony ORM internally. On Python 3.14, pony ORM raises `TypeError: cannot pickle 'itertools.count' object` and fails to run.

**mutmut 3.x** calls `multiprocessing.set_start_method('fork')` at module level in `mutmut/__main__.py`. When mutmut's trampoline imports `mutmut.__main__` inside a pytest subprocess, the start method is already set, causing `RuntimeError: context has already been set`. mutmut misreports this as a segfault across every mutant — all 450 mutants appeared to survive. The underlying bug is tracked at https://github.com/boxed/mutmut/issues/466, acknowledged by maintainers, with a fix proposed but not yet released.

We evaluated **cosmic-ray** as an alternative. The dependency-auditor rejected it: its transitive dependency set includes gitpython and sqlalchemy, both Python 3.14-incompatible, plus an excessive overall footprint inconsistent with this project's lean dependency policy.

No workaround for mutmut 3.x is viable without forking or patching the library. Carrying a patched fork adds maintenance burden with no clear end state.

## Decision

We decided to remove mutmut entirely from the project for now. All references — `pyproject.toml` configuration, `Taskfile.yaml` tasks, CI pipeline entries, and `CLAUDE.md` tooling tables — will be removed until a compatible tool is available.

The decision to revisit is tied to a concrete signal: a released fix for https://github.com/boxed/mutmut/issues/466, or a mutation testing tool with clean Python 3.14 support and an acceptable dependency footprint.

## Consequences

**Positive:**

- Eliminates a broken tool that produced misleading results (false 100% mutant survival).
- Removes a dependency and its configuration overhead.
- CI pipeline no longer carries a task that cannot run.

**Negative:**

- Mutation coverage lapses until a replacement is adopted.
- The gap is accepted as a known limitation given Python 3.14's recency and the upstream fix timeline.
