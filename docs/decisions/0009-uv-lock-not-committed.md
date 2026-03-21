# 0009. uv.lock Is Not Committed

Date: 2026-03-21
Status: Accepted

## Context

`uv.lock` was initially committed to the repository. The question was whether it should stay. `sheridan-iceberg` is a library published to PyPI, not a deployed application.

## Decision

We decided not to commit `uv.lock`. Library consumers resolve their own dependency graph against the constraints in `pyproject.toml`. A committed lockfile would not benefit downstream users and could cause confusion about which versions are required versus pinned for development convenience. `uv.lock` is listed in `.gitignore`.

## Consequences

- CI re-resolves dependencies on each run. With `uv` this is fast enough to be a non-issue.
- Dev environments may pick up newer compatible versions of dev dependencies over time.
- Reproducibility of the development environment is slightly reduced compared to an application with a committed lockfile. This tradeoff is accepted — library dev environments are less sensitive to this than deployed applications.
