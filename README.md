# sheridan-iceberg

[![CI](https://github.com/sheridan/sheridan-iceberg/actions/workflows/ci.yml/badge.svg)](https://github.com/sheridan/sheridan-iceberg/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-90%25-brightgreen)](https://github.com/sheridan/sheridan-iceberg)
[![Mutation Score](https://img.shields.io/badge/mutation-tracked-blue)](https://github.com/sheridan/sheridan-iceberg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)

> The public API is the tip of the iceberg. `iceberg` guards the waterline.

`sheridan-iceberg` analyzes Python modules and enforces the presence and
correctness of `__all__`. It uses Python's `ast` module for static analysis —
no importing of user code.

## Features

- Walks a Python project's modules via AST (safe, no imports)
- Uses `__all__` as the authoritative public API surface when present
- Falls back to inferring non-underscore top-level names when absent
- Reports missing, incorrect, or unsorted `__all__` declarations
- Optionally auto-fixes `__all__` in place
- Machine-readable JSON output and human-readable text output
- Works as a pre-commit hook, CLI tool, or GitHub Action

## Installation

```bash
pip install sheridan-iceberg
```

## Usage

```bash
# Check a project
iceberg check src/

# Auto-fix __all__ declarations
iceberg fix src/

# JSON output
iceberg check src/ --format json
```

## As a pre-commit hook

```yaml
repos:
  - repo: https://github.com/sheridan/sheridan-iceberg
    rev: v0.1.0
    hooks:
      - id: iceberg
```

## Development

```bash
# Install dependencies
task install

# Run all checks
task check

# Run tests
task test

# Build docs
task docs-serve
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.
