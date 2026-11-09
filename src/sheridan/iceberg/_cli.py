"""Command-line interface for iceberg."""

__all__ = ["main"]

import argparse
import dataclasses
import io
import os
import stat
import sys
import tempfile
import traceback
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path

from sheridan.iceberg._api import get_public_api_report
from sheridan.iceberg._config import Config, load_config, load_config_file
from sheridan.iceberg._exceptions import IcebergError
from sheridan.iceberg._formatter import format_diagnostic, format_json, format_tree

_ISSUES_URL = "https://github.com/andrewasheridan/iceberg/issues"


def _traceback_requested(args: argparse.Namespace) -> bool:
    """Tell if the user asked for full tracebacks of unexpected errors.

    Args:
        args: The parsed command-line arguments.

    Returns:
        True if the user gave ``--traceback`` or set ``ICEBERG_DEBUG`` to ``1``.
    """
    return args.traceback or os.environ.get("ICEBERG_DEBUG") == "1"


def _report_unexpected_error(exc: Exception, *, show_traceback: bool) -> None:
    """Print an unexpected exception to stderr in a form that users can put in a bug report.

    Args:
        exc: The exception that the analysis did not catch.
        show_traceback: If True, print the full traceback. If False, print a hint
            that tells how to get the full traceback.
    """
    if show_traceback:
        traceback.print_exception(exc, file=sys.stderr)
    else:
        print(f"unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("To see the full traceback, run again with --traceback (or set ICEBERG_DEBUG=1).", file=sys.stderr)

    print(f"This is a bug in iceberg. Report it at {_ISSUES_URL}", file=sys.stderr)


def _positive_int(value: str) -> int:
    """Parse a command-line value as an integer of at least 1.

    Args:
        value: The raw command-line value.

    Returns:
        The parsed integer.

    Raises:
        argparse.ArgumentTypeError: If *value* is not an integer of at least 1.
    """
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"the value must be a positive integer, not {value!r}") from None

    if number < 1:
        raise argparse.ArgumentTypeError(f"the value must be a positive integer, not {value!r}")

    return number


def _new_file_mode() -> int:
    """Compute the permission bits that ``open()`` gives a new file with the current umask.

    ``tempfile.mkstemp`` makes files that only their owner can read. Without this
    function, the report keeps these permission bits after the move into place.
    """
    umask = os.umask(0)
    os.umask(umask)

    return 0o666 & ~umask


def _write_output(path: Path, text: str) -> None:
    """Write *text* to *path* as UTF-8 with a final newline, and replace the file atomically.

    The function follows symlinks. Thus, the link stays and the target of the
    link gets the report.

    For a regular file or a new path, the function first writes the text to a
    temporary file in the directory of the target. Thus, a failed write never
    leaves a partial file and never destroys the old file. An existing file
    keeps its permission bits.

    If the path exists but is not a regular file (for example ``/dev/stdout`` or
    a named pipe), the function writes to it directly. It cannot replace such a
    file.

    Args:
        path: The file to write.
        text: The text of the report, without the final newline.

    Raises:
        OSError: If the function cannot write the file.
    """
    data = f"{text}\n".encode()
    target = path.resolve()

    try:
        existing = target.stat()
    except FileNotFoundError:
        mode = _new_file_mode()
    else:
        if not stat.S_ISREG(existing.st_mode):
            with target.open("wb") as file:
                file.write(data)

            return

        mode = stat.S_IMODE(existing.st_mode)

    fd, temp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")

    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)

        os.chmod(temp_name, mode)
        os.replace(temp_name, target)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def _resolve_config(args: argparse.Namespace) -> Config:
    """Build the configuration for one run from the parsed arguments.

    The base configuration comes from one of these sources:

    - The file from ``--config``.
    - The default values, if the user gave ``--no-config``.
    - The file that the search finds in the analyzed path or its parents.

    Then the values from the command line replace the values in the base
    configuration.

    Args:
        args: The parsed command-line arguments.

    Returns:
        The configuration for the analysis.

    Raises:
        ConfigError: If the function cannot load the configuration file.
    """
    if args.no_config:
        config = Config()
    elif args.config is not None:
        config = load_config_file(args.config)
    else:
        config = load_config(args.path)

    if args.exclude:
        config = dataclasses.replace(config, exclude=(*config.exclude, *args.exclude))

    if args.max_workers is not None:
        config = dataclasses.replace(config, max_workers=args.max_workers)

    return config


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ``iceberg`` command.

    Returns:
        The parser, with all the options that the CLI accepts.
    """
    parser = argparse.ArgumentParser(
        prog="iceberg",
        description="Show the public API of a Python package or module.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version('sheridan-iceberg')}",
    )
    parser.add_argument(
        "path",
        type=Path,
        help="The path to a Python package directory or a module file.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Write the output as JSON, not as the default tree.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        metavar="PATH",
        help=(
            "Write the report to PATH as UTF-8, not to stdout. iceberg replaces the file "
            "only when the report is complete. Thus, an error never leaves a partial file. "
            "iceberg follows symlinks, and an existing file keeps its permissions. iceberg "
            "writes directly to a file that is not regular, such as /dev/stdout."
        ),
    )
    parser.add_argument(
        "--show-overload-implementations",
        action="store_true",
        default=False,
        help=(
            "In the tree output, also show the signature of the implementation of each "
            "overloaded function, after its @overload signatures."
        ),
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help=(
            "Skip the directories and files whose path relative to PATH matches GLOB. "
            "You can give this option more than one time. It adds to the 'exclude' "
            "list from the configuration file."
        ),
    )

    config_source = parser.add_mutually_exclusive_group()
    config_source.add_argument(
        "--config",
        type=Path,
        metavar="PATH",
        help=(
            "Read the configuration from PATH. Do not search the analyzed path and its parents. "
            "If the name of the file is pyproject.toml, iceberg reads its [tool.iceberg] table."
        ),
    )
    config_source.add_argument(
        "--no-config",
        action="store_true",
        default=False,
        help="Ignore the configuration files and use the default values.",
    )
    parser.add_argument(
        "--max-workers",
        type=_positive_int,
        metavar="N",
        help=(
            "The number of worker processes that parse modules. "
            "This value replaces 'max_workers' from the configuration file."
        ),
    )

    parser.add_argument(
        "--keep-going",
        action="store_true",
        default=False,
        help=(
            "If iceberg cannot read or parse a module, skip the module and continue. iceberg "
            "prints the errors and the unresolved names to stderr. If it skipped a module, "
            "the exit code is 1."
        ),
    )
    parser.add_argument(
        "--traceback",
        action="store_true",
        default=False,
        help=(
            "If an unexpected error occurs, print the full traceback for a bug report. "
            "The environment variable ICEBERG_DEBUG=1 has the same effect."
        ),
    )

    return parser


def _print_utf8(text: str) -> None:
    """Print *text* to stdout as UTF-8.

    On Windows, a pipe or a redirect to a file often uses a code page such as
    cp1252. That code page cannot encode the tree connectors. UTF-8 also makes
    stdout agree with the ``--output`` file.

    Args:
        text: The text to print.
    """
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")

    print(text)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the iceberg CLI.

    The function parses *argv* (or ``sys.argv[1:]`` if *argv* is ``None``). It
    resolves the public API of the given path. Then it writes the result to
    stdout (or to the ``--output`` file). With ``--keep-going``, the
    diagnostics go to stderr (and into the JSON output).

    Args:
        argv: The list of arguments to parse. The default is ``sys.argv[1:]``.

    Returns:
        An integer exit code. ``0`` if the run is successful. ``1`` for a known
        ``IcebergError``, or if ``--keep-going`` skipped a module. ``2`` for an
        unexpected exception.
    """
    args = _build_parser().parse_args(argv)

    try:
        return _run(args)
    except IcebergError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        _report_unexpected_error(exc, show_traceback=_traceback_requested(args))
        return 2


def _run(args: argparse.Namespace) -> int:
    """Analyze the path, then print or write the report and the diagnostics.

    Args:
        args: The parsed command-line arguments.

    Returns:
        ``0`` if the run is successful. ``1`` if the function cannot write the
        output file, or if ``--keep-going`` skipped a module.

    Raises:
        IcebergError: If the configuration or the analysis fails.
    """
    config = _resolve_config(args)
    report = get_public_api_report(args.path, config=config, keep_going=args.keep_going)

    if args.json:
        output = format_json(report.api, report.diagnostics if args.keep_going else None)
    else:
        output = format_tree(report.api, show_overload_implementation=args.show_overload_implementations)

    if args.output is None:
        _print_utf8(output)
    else:
        try:
            _write_output(args.output, output)
        except OSError as exc:
            print(f"error: cannot write {args.output}: {exc.strerror or exc}", file=sys.stderr)
            return 1

    if not args.keep_going:
        return 0

    for diagnostic in report.diagnostics:
        print(format_diagnostic(diagnostic), file=sys.stderr)

    return 1 if report.has_errors else 0
