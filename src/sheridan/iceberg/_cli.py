"""Command-line interface for iceberg."""

__all__ = ["main"]

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from sheridan.iceberg._api import get_public_api
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

    args = parser.parse_args(argv)

    try:
        package = get_public_api(args.path)
    except IcebergError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    output = format_json(package) if args.json else format_tree(package)
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
