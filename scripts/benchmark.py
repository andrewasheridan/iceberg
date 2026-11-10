"""Measure the time that iceberg needs to analyze a large source tree.

By default, the script analyzes the standard library of the Python that runs it.
With `--generate N`, the script makes a package with about N small modules in a
temporary directory and analyzes it. A large tree shows a step with a quadratic
cost more clearly than the standard library does.

Usage:

    uv run python scripts/benchmark.py [PATH] [--generate N] [--repeat N]

The script prints the number of modules, and the best and the median time of
the runs. Use the best time to compare two versions of iceberg.
"""

import argparse
import statistics
import sysconfig
import tempfile
import time
import warnings
from pathlib import Path

from sheridan.iceberg._config import Config
from sheridan.iceberg._discovery import discover
from sheridan.iceberg._orchestrator import build_package

MODULES_PER_SUBPACKAGE = 50
"""The number of modules in each subpackage of a generated package."""


def generate_package(parent: Path, module_count: int) -> Path:
    """Make a package with about *module_count* modules below *parent*.

    Each subpackage has ``MODULES_PER_SUBPACKAGE`` modules with one function.
    The ``__init__.py`` of each subpackage imports all these functions again.

    Args:
        parent: The directory that gets the package.
        module_count: The approximate number of modules to make.

    Returns:
        The root directory of the package.
    """
    root = parent / "generated"
    root.mkdir()
    (root / "__init__.py").write_text("")

    module_names = [f"mod{index}" for index in range(MODULES_PER_SUBPACKAGE)]
    init_source = "".join(f"from .{name} import {name}_function\n" for name in module_names)

    for subpackage_index in range(max(1, module_count // MODULES_PER_SUBPACKAGE)):
        subpackage = root / f"sub{subpackage_index}"
        subpackage.mkdir()
        (subpackage / "__init__.py").write_text(init_source)

        for name in module_names:
            (subpackage / f"{name}.py").write_text(f"def {name}_function():\n    pass\n")

    return root


def measure(path: Path, repeat: int) -> None:
    """Analyze *path* *repeat* times and print the times.

    Args:
        path: The package directory to analyze.
        repeat: The number of runs.
    """
    config = Config()
    module_count = len(discover(path, config))

    timings: list[float] = []
    for _ in range(repeat):
        start = time.perf_counter()
        build_package(path, config, errors=[])
        timings.append(time.perf_counter() - start)

    print(f"path:    {path}")
    print(f"modules: {module_count}")
    print(f"best:    {min(timings):.3f} s")
    print(f"median:  {statistics.median(timings):.3f} s")


def main() -> None:
    """Read the arguments and measure the selected tree."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", nargs="?", type=Path, default=Path(sysconfig.get_paths()["stdlib"]))
    parser.add_argument("--generate", type=int, metavar="N", help="analyze a generated package with about N modules")
    parser.add_argument("--repeat", type=int, default=3, help="the number of runs (default: 3)")
    args = parser.parse_args()

    # The standard library has some `__all__` values that iceberg cannot evaluate.
    # The warnings about them are not part of the measurement.
    warnings.simplefilter("ignore")

    if args.generate is None:
        measure(args.path, args.repeat)
        return

    with tempfile.TemporaryDirectory() as directory:
        measure(generate_package(Path(directory), args.generate), args.repeat)


if __name__ == "__main__":
    main()
