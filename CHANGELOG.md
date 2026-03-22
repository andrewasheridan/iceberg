# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-03-22

### Added

- First stable release. The `sheridan.iceberg` public API is considered stable
  and ready for production use. Downstream tools (including `sheridan-diffract`)
  can now take a stable dependency on this package.

### Fixed

- Dagger engine image is now cached between CI runs, eliminating redundant
  image pulls and unblocking the full automated release pipeline. The
  tag-on-merge and publish-to-PyPI chain now operates end-to-end without manual
  intervention.

## [0.3.0] - 2026-03-22

### Fixed

- Resolved a race condition in the docs workflow that caused duplicate
  `github-pages` artifacts to be uploaded when multiple jobs completed at the
  same time.

## [0.2.0] - 2026-03-22

### Added

- Package is now published to PyPI. `pyproject.toml` was hardened with
  classifiers, project URLs, and a `[project.scripts]` entry point. The build
  backend was switched to Hatchling and a Trusted Publishing configuration was
  added so releases are signed and published from CI without stored secrets.
- CI pipeline now enforces branch protection and uses auto-merge for version
  bump PRs. Documentation is automatically built and deployed to GitHub Pages on
  every merge to `main`.

### Changed

- `sheridan.iceberg` public API surface was refined: modules, classes, and
  functions exported from the package were reviewed and aligned with the
  intended programmatic interface documented in the API reference.

### Fixed

- `mkdocstrings[python]` is now explicitly installed in the docs workflow,
  resolving a build failure that prevented the documentation site from being
  generated in CI.

## [0.1.0] - 2026-03-22

### Added

- `show` command (primary): reports the effective public API surface of each
  module — using `__all__` when present, falling back to AST inference of
  non-underscore top-level names. Supports `--json` for machine-readable output.
- `check` command: enforces `__all__` correctness. Reports three violation
  classes — IB001 (missing `__all__`), IB002 (public name absent from
  `__all__`), IB003 (`__all__` is not sorted). IB002 is one-directional:
  names the AST considers public but that are absent from `__all__` are
  flagged; phantom exports (present in `__all__` but absent from AST) are not
  flagged by `check`.
- `fix` command: repairs `__all__` in place, fully synchronising it with the
  AST in both directions — adding missing names and removing phantom exports.
- Named IB error codes on all `check` output, making violations easy to
  reference, suppress, and search.
- `--use-ast` flag: bypasses `__all__` and always derives the public surface
  from AST inference.
- JSON output mode (`--json`) on all commands for integration with other tools
  and scripts.
- Zero runtime dependencies — static analysis is performed with Python's
  built-in `ast` module; no user code is imported or executed.
- Pre-commit hook configuration (`.pre-commit-hooks.yaml`) so `iceberg check`
  can be added to any project's pre-commit setup in one line.
- GitHub Actions workflow running the full CI pipeline via Dagger.
- Dagger-based CI pipeline running lint, format check, type checking, tests
  with coverage, security lint, doc generation, and self-check (`iceberg check
  src/`) in parallel inside containers. Podman is the default local runtime;
  Docker is supported via `CONTAINER_RUNTIME=docker`.
- Zensical documentation site with API reference and Architecture Decision
  Records (ADRs 0009–0020).
- `Taskfile.yaml` with standard tasks: `install`, `lint`, `lint:check`,
  `format`, `format:check`, `typecheck`, `test`, `iceberg`, `check`, `ci`,
  `docs`, `docs-serve`.

### Changed

- Refactored CLI into a thin shell: all reusable logic was moved from `cli.py`
  into library modules (`ast_walker`, `reporter`, `fixer`) so that the public
  API is fully accessible programmatically without going through the CLI.
- `fix_modules()` extracted from the CLI fix handler into a standalone library
  function.
- Replaced `typer` with `argparse` to eliminate the only runtime dependency,
  keeping the tool dependency-free.
- Replaced MkDocs with Zensical for documentation generation, aligning with
  the `sheridan.*` toolchain standard.

### Fixed

- Pinned Dagger to v0.20.3 and corrected the `cmds` input in the GitHub
  Actions workflow to ensure reliable CI runs.
- Resolved all `ruff`, `mypy`, and coverage issues to bring the project to a
  clean passing state on all checks.

[Unreleased]: https://github.com/andrewasheridan/iceberg/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/andrewasheridan/iceberg/compare/v0.3.0...v1.0.0
[0.3.0]: https://github.com/andrewasheridan/iceberg/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/andrewasheridan/iceberg/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/andrewasheridan/iceberg/releases/tag/v0.1.0
