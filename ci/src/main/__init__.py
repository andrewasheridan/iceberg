"""Dagger CI pipeline for sheridan-iceberg.

Each gate runs in its own container. All gates run in parallel via asyncio.gather.

Usage:
    dagger call check              # run all gates
    dagger call lint               # run a single gate
    dagger call check --source=.   # explicit source path
"""

__all__ = [
    "SheridanIcebergCiCi",
]

import asyncio
from typing import Annotated

import dagger
from dagger import DefaultPath, dag, function, object_type

_PYTHON_IMAGE = "python:3.14-slim"


def _base(source: dagger.Directory) -> dagger.Container:
    return (
        dag.container()
        .from_(_PYTHON_IMAGE)
        .with_exec(["pip", "install", "--quiet", "uv"])
        .with_mounted_cache("/root/.cache/uv", dag.cache_volume("uv-cache"))
        .with_directory("/src", source)
        .with_workdir("/src")
        .with_exec(["uv", "sync", "--all-extras", "--dev"])
    )


@object_type
class SheridanIcebergCi:
    """CI pipeline for sheridan-iceberg."""

    @function
    async def lint(
        self,
        source: Annotated[dagger.Directory, DefaultPath(".")],
    ) -> str:
        """Run ruff linter."""
        return await _base(source).with_exec(["uv", "run", "ruff", "check", "."]).stdout()

    @function
    async def format_check(
        self,
        source: Annotated[dagger.Directory, DefaultPath(".")],
    ) -> str:
        """Check formatting without writing."""
        return await _base(source).with_exec(["uv", "run", "ruff", "format", "--check", "."]).stdout()

    @function
    async def typecheck(
        self,
        source: Annotated[dagger.Directory, DefaultPath(".")],
    ) -> str:
        """Run mypy strict type checking."""
        return await _base(source).with_exec(["uv", "run", "mypy", "--strict", "src/"]).stdout()

    @function
    async def test(
        self,
        source: Annotated[dagger.Directory, DefaultPath(".")],
    ) -> str:
        """Run pytest with coverage."""
        return await _base(source).with_exec(["uv", "run", "pytest", "--cov"]).stdout()

    @function
    async def security(
        self,
        source: Annotated[dagger.Directory, DefaultPath(".")],
    ) -> str:
        """Run bandit security linter."""
        return await _base(source).with_exec(["uv", "run", "bandit", "-r", "src/"]).stdout()

    @function
    async def docs(
        self,
        source: Annotated[dagger.Directory, DefaultPath(".")],
    ) -> str:
        """Build Zensical documentation."""
        return await _base(source).with_exec(["uv", "run", "zensical", "build"]).stdout()

    @function
    async def iceberg_check(
        self,
        source: Annotated[dagger.Directory, DefaultPath(".")],
    ) -> str:
        """Run iceberg on itself (dogfooding)."""
        return await _base(source).with_exec(["uv", "run", "iceberg", "check", "src/"]).stdout()

    @function
    async def check(
        self,
        source: Annotated[dagger.Directory, DefaultPath(".")],
    ) -> str:
        """Run all CI gates in parallel.

        Returns a pass/fail summary. Raises on any failure, showing all results.
        """
        base = _base(source)
        gates: list[tuple[str, dagger.Container]] = [
            ("lint", base.with_exec(["uv", "run", "ruff", "check", "."])),
            ("format-check", base.with_exec(["uv", "run", "ruff", "format", "--check", "."])),
            ("typecheck", base.with_exec(["uv", "run", "mypy", "--strict", "src/"])),
            ("test", base.with_exec(["uv", "run", "pytest", "--cov"])),
            ("security", base.with_exec(["uv", "run", "bandit", "-r", "src/"])),
            ("docs", base.with_exec(["uv", "run", "zensical", "build"])),
            ("iceberg", base.with_exec(["uv", "run", "iceberg", "check", "src/"])),
        ]

        results: list[str | BaseException] = list(
            await asyncio.gather(
                *[container.stdout() for _, container in gates],
                return_exceptions=True,
            )
        )

        lines: list[str] = []
        failed: list[str] = []
        for (name, _), result in zip(gates, results, strict=True):
            if isinstance(result, BaseException):
                lines.append(f"[FAIL] {name}: {result}")
                failed.append(name)
            else:
                lines.append(f"[PASS] {name}")

        summary = "\n".join(lines)
        if failed:
            raise RuntimeError(f"CI failed — gates: {', '.join(failed)}\n\n{summary}")
        return summary
