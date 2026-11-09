"""Dagger CI pipeline for sheridan-iceberg.

Each gate runs in its own container. All gates run in parallel via asyncio.gather.

Usage:
    dagger call check              # run all gates
    dagger call lint               # run a single gate
    dagger call check --source=.   # explicit source path
"""

__all__ = [
    "SheridanIcebergCi",
]

import asyncio
import difflib
from collections.abc import Coroutine
from typing import Annotated, Any

import dagger
from dagger import DefaultPath, dag, function, object_type

_PYTHON_IMAGE = "python:3.14-slim"
_API_SNAPSHOT = "api.txt"
_API_PATH = "src/sheridan/"


def _uv(source: dagger.Directory) -> dagger.Container:
    return (
        dag.container()
        .from_(_PYTHON_IMAGE)
        .with_exec(["pip", "install", "--quiet", "uv"])
        .with_mounted_cache("/root/.cache/uv", dag.cache_volume("uv-cache"))
        .with_directory("/src", source)
        .with_workdir("/src")
    )


def _base(source: dagger.Directory) -> dagger.Container:
    return _uv(source).with_exec(["uv", "sync", "--locked"])


async def _api_check(source: dagger.Directory) -> str:
    """Compare iceberg's output for the package with the committed snapshot.

    Raises:
        RuntimeError: The output differs from the snapshot, with the diff and the
            command that updates the snapshot.
    """
    current = await _base(source).with_exec(["uv", "run", "iceberg", _API_PATH]).stdout()
    expected = await source.file(_API_SNAPSHOT).contents()
    if current == expected:
        return current
    diff = "".join(
        difflib.unified_diff(
            expected.splitlines(keepends=True),
            current.splitlines(keepends=True),
            fromfile=_API_SNAPSHOT,
            tofile=f"iceberg {_API_PATH}",
        )
    )
    raise RuntimeError(
        f"The public API differs from {_API_SNAPSHOT}. If that is intended, run "
        f"`task api:update` and commit {_API_SNAPSHOT}.\n\n{diff}"
    )


@object_type
class SheridanIcebergCi:
    """CI pipeline for sheridan-iceberg."""

    @function
    async def lock(
        self,
        source: Annotated[dagger.Directory, DefaultPath(".")],
    ) -> str:
        """Fail if uv.lock is out of date with pyproject.toml."""
        return await _uv(source).with_exec(["uv", "lock", "--check"]).stdout()

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
        """Run pyrefly type checking."""
        return await _base(source).with_exec(["uv", "run", "pyrefly", "check"]).stdout()

    @function
    async def test(
        self,
        source: Annotated[dagger.Directory, DefaultPath(".")],
    ) -> str:
        """Run pytest with coverage."""
        return await _base(source).with_exec(["uv", "run", "pytest"]).stdout()

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
        """Fail if iceberg's report of its own public API differs from api.txt."""
        return await _api_check(source)

    @function
    async def check(
        self,
        source: Annotated[dagger.Directory, DefaultPath(".")],
    ) -> str:
        """Run all CI gates in parallel.

        Returns a pass/fail summary. Raises on any failure, showing all results.
        """
        base = _base(source)
        containers: list[tuple[str, dagger.Container]] = [
            ("lock", _uv(source).with_exec(["uv", "lock", "--check"])),
            ("lint", base.with_exec(["uv", "run", "ruff", "check", "."])),
            ("format-check", base.with_exec(["uv", "run", "ruff", "format", "--check", "."])),
            ("typecheck", base.with_exec(["uv", "run", "pyrefly", "check"])),
            ("test", base.with_exec(["uv", "run", "pytest"])),
            ("security", base.with_exec(["uv", "run", "bandit", "-r", "src/"])),
            ("docs", base.with_exec(["uv", "run", "zensical", "build"])),
        ]
        gates: list[tuple[str, Coroutine[Any, Any, str]]] = [
            *((name, container.stdout()) for name, container in containers),
            ("iceberg", _api_check(source)),
        ]

        results: list[str | BaseException] = list(
            await asyncio.gather(
                *[gate for _, gate in gates],
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
