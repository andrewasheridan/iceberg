"""Command-line interface for iceberg."""

__all__ = ["main"]

import argparse
import dataclasses
import sys
from collections.abc import Sequence
from pathlib import Path

from sheridan.iceberg._api import get_public_api
from sheridan.iceberg._config import load_config
from sheridan.iceberg._exceptions import IcebergError
from sheridan.iceberg._formatter import format_json, format_tree


def main(argv: Sequence[str] | None = None) -> int:
    """Run the iceberg CLI.

    Parses *argv* (or ``sys.argv[1:]`` when *argv* is ``None``), resolves the
    public API of the given path, and writes the result to stdout.

    Args:
        argv: Argument list to parse.  Defaults to ``sys.argv[1:]``.

    Returns:
        An integer exit code: ``0`` on success, ``1`` on a known
        ``IcebergError``, ``2`` on any unexpected exception.
    """
    parser = argparse.ArgumentParser(
        prog="iceberg",
        description="Report the public API surface of a Python package or module.",
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Path to a Python package directory or module file.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit output as JSON instead of the default tree format.",
    )
    parser.add_argument(
        "--show-overload-implementations",
        action="store_true",
        default=False,
        help=(
            "In the tree output, also show the implementation signature of each "
            "overloaded function after its @overload signatures."
        ),
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help=(
            "Skip directories and files whose path relative to PATH matches GLOB. "
            "Repeatable; extends the 'exclude' list from the configuration file."
        ),
    )

    args = parser.parse_args(argv)

    try:
        config = load_config(args.path)
        if args.exclude:
            config = dataclasses.replace(config, exclude=(*config.exclude, *args.exclude))
        package = get_public_api(args.path, config=config)
    except IcebergError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if args.json:
        output = format_json(package)
    else:
        output = format_tree(package, show_overload_implementation=args.show_overload_implementations)
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
