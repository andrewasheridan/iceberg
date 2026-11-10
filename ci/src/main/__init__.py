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
# The newest Python that iceberg supports. uv installs it in the 3.14 image, and only the
# "test" dependency group is synced, because some dev tools have no wheels for it yet.
_NEXT_PYTHON = "3.15"
_API_SNAPSHOT = "api.txt"
_API_PATH = "src/sheridan/"
_SDIST_DIR = "/dist"
# Hatch adds PKG-INFO and .gitignore to every sdist; the rest is the include list in
# pyproject.toml.
_SDIST_ALLOWED = frozenset(
    {
        ".gitignore",
        "CHANGELOG.md",
        "LICENSE",
        "PKG-INFO",
        "README.md",
        "pyproject.toml",
        "src",
        "tests",
    }
)


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


def _test_next_python(source: dagger.Directory) -> dagger.Container:
    """Run pytest on the newest supported Python with only the test dependencies."""
    return (
        _uv(source)
        .with_mounted_cache("/root/.local/share/uv/python", dag.cache_volume("uv-python"))
        .with_exec(["uv", "sync", "--locked", "--python", _NEXT_PYTHON, "--no-default-groups", "--group", "test"])
        .with_exec(["uv", "run", "--no-sync", "pytest"])
    )


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


async def _sdist_check(source: dagger.Directory) -> str:
    """Build the sdist and check its top-level entries.

    Raises:
        RuntimeError: The sdist has a top-level entry that is not in the allowed set.
    """
    listing = await (
        _uv(source)
        .with_exec(["uv", "build", "--sdist", "--out-dir", _SDIST_DIR])
        .with_exec(["sh", "-c", f"tar -tzf {_SDIST_DIR}/*.tar.gz"])
        .stdout()
    )
    top_level = {parts[1] for line in listing.splitlines() if len(parts := line.split("/")) > 1 and parts[1]}
    unexpected = sorted(top_level - _SDIST_ALLOWED)
    if unexpected:
        raise RuntimeError(
            f"The sdist has unexpected top-level entries: {', '.join(unexpected)}. "
            "Check [tool.hatch.build.targets.sdist] in pyproject.toml."
        )
    return listing


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
    async def test_next_python(
        self,
        source: Annotated[dagger.Directory, DefaultPath(".")],
    ) -> str:
        """Run pytest with coverage on the newest supported Python."""
        return await _test_next_python(source).stdout()

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
    async def sdist_check(
        self,
        source: Annotated[dagger.Directory, DefaultPath(".")],
    ) -> str:
        """Fail if the sdist has a top-level entry outside the allowed set."""
        return await _sdist_check(source)

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
            (f"test-{_NEXT_PYTHON}", _test_next_python(source)),
            ("security", base.with_exec(["uv", "run", "bandit", "-r", "src/"])),
            ("docs", base.with_exec(["uv", "run", "zensical", "build"])),
        ]
        gates: list[tuple[str, Coroutine[Any, Any, str]]] = [
            *((name, container.stdout()) for name, container in containers),
            ("iceberg", _api_check(source)),
            ("sdist", _sdist_check(source)),
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
