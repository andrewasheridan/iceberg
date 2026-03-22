# 0018. Dagger as CI Pipeline Engine with Podman Default

Date: 2026-03-21
Status: Accepted

## Context

The project's CI gates (lint, format-check, typecheck, test+coverage, security, docs, iceberg self-check) were specified in CLAUDE.md but had no implementation. Each gate was intended to run in its own container. Without a solution that runs identically locally and in CI, "works on my machine" failures are inevitable.

## Decision

We chose Dagger (dagger.io) as the CI pipeline engine, using the Dagger Python SDK with the `@object_type` / `@function` module pattern.

- Each CI gate is a separate `@function` returning `str` (stdout from the container).
- A top-level `check` function runs all gates in parallel via `asyncio.gather` with `return_exceptions=True` — all gates run even when one fails, so developers see the full picture.
- The Dagger module lives in `ci/src/main/__init__.py`; configuration is in `dagger.json` at the repo root.
- `ci/sdk/` (Dagger-generated) is gitignored; `dagger develop` must be run once after clone.
- Podman is the default local runtime, configured via the `DOCKER_HOST` env var pointing at the Podman socket.
- Docker is supported as a drop-in alternative (default `DOCKER_HOST`).
- GitHub Actions uses Docker via `dagger/dagger-action@v3`, which is the runner default.

We chose Dagger over native GitHub Actions workflows because the pipeline runs identically locally and in CI — developers run `dagger call check` before pushing and see exactly what CI will see. Dagger's DAG engine also provides automatic parallelism and layer caching without extra configuration.

We chose Podman as the default local runtime because it is rootless by default (no daemon running as root) and OCI-native. Docker remains fully supported.

## Consequences

**Positive:**
- Pipeline parity between local dev and CI eliminates environment-specific failures.
- Developers can reproduce any CI failure locally without pushing.
- Parallel gate execution with `asyncio.gather` keeps total CI time low.
- Podman default improves local security posture (rootless).
- Switching between Podman and Docker requires only changing `DOCKER_HOST`.

**Negative:**
- Contributors must install Dagger CLI and either Podman or Docker; this adds onboarding steps.
- `dagger develop` must be run once after clone to regenerate `ci/sdk/`; forgetting this breaks the pipeline locally.
- Dagger is an additional dependency and abstraction layer that contributors unfamiliar with it must learn.
