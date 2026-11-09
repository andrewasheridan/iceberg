"""Command-line interface for iceberg."""

__all__ = ["main"]

import argparse
import dataclasses
import os
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
    """Tell whether the user asked for full tracebacks on unexpected errors.

    Args:
        args: The parsed command-line arguments.

    Returns:
        True if ``--traceback`` was given or ``ICEBERG_DEBUG`` is set to ``1``.
    """
    return args.traceback or os.environ.get("ICEBERG_DEBUG") == "1"


def _report_unexpected_error(exc: Exception, *, show_traceback: bool) -> None:
    """Print an unexpected exception to stderr in a form users can put in a bug report.

    Args:
        exc: The exception that escaped the analysis.
        show_traceback: Print the full traceback instead of a hint on how to get it.
    """
    if show_traceback:
        traceback.print_exception(exc, file=sys.stderr)
    else:
        print(f"unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("Run again with --traceback (or ICEBERG_DEBUG=1) for the full traceback.", file=sys.stderr)

    print(f"This is a bug in iceberg. Please report it at {_ISSUES_URL}", file=sys.stderr)


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
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {value!r}") from None

    if number < 1:
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {value!r}")

    return number


def _new_file_mode() -> int:
    """Compute the permission bits ``open()`` would give a new file under the current umask.

    ``tempfile.mkstemp`` creates files readable only by their owner, which would
    otherwise carry over to the report once it is moved into place.
    """
    umask = os.umask(0)
    os.umask(umask)

    return 0o666 & ~umask


def _write_output(path: Path, text: str) -> None:
    """Write *text* to *path* as UTF-8 with a final newline, replacing it atomically.

    The text goes to a temporary file in the same directory first, so a failed
    write never leaves a partial file at *path* or destroys an existing one.

    Args:
        path: The file to write.
        text: The report text, without the final newline.

    Raises:
        OSError: If the file cannot be written.
    """
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")

    try:
        with os.fdopen(fd, "wb") as file:
            file.write(f"{text}\n".encode())

        os.chmod(temp_name, _new_file_mode())
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def _resolve_config(args: argparse.Namespace) -> Config:
    """Build the configuration for one run from the parsed arguments.

    The base configuration comes from ``--config``, from the defaults when
    ``--no-config`` is given, or else from the file found by walking up from
    the analyzed path. Command-line values then override it.

    Args:
        args: The parsed command-line arguments.

    Returns:
        The configuration to analyze with.

    Raises:
        ConfigError: If the configuration file cannot be loaded.
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
        The parser, with every option the CLI accepts.
    """
    parser = argparse.ArgumentParser(
        prog="iceberg",
        description="Report the public API surface of a Python package or module.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version('sheridan-iceberg')}",
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
        "-o",
        "--output",
        type=Path,
        metavar="PATH",
        help=(
            "Write the report to PATH as UTF-8 instead of stdout. The file is replaced "
            "only when the report is complete, so an error never leaves a partial file."
        ),
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

    config_source = parser.add_mutually_exclusive_group()
    config_source.add_argument(
        "--config",
        type=Path,
        metavar="PATH",
        help=(
            "Read configuration from PATH instead of searching upward from the analyzed path. "
            "A file named pyproject.toml is read from its [tool.iceberg] table."
        ),
    )
    config_source.add_argument(
        "--no-config",
        action="store_true",
        default=False,
        help="Ignore configuration files and use the defaults.",
    )
    parser.add_argument(
        "--max-workers",
        type=_positive_int,
        metavar="N",
        help="Number of worker processes used to parse modules. Overrides 'max_workers' from the configuration file.",
    )

    parser.add_argument(
        "--keep-going",
        action="store_true",
        default=False,
        help=(
            "Skip modules that cannot be read or parsed instead of stopping. Errors and "
            "unresolved names are printed to stderr, and the exit code is 1 if any module was skipped."
        ),
    )
    parser.add_argument(
        "--traceback",
        action="store_true",
        default=False,
        help=(
            "On an unexpected error, print the full traceback for a bug report. "
            "Setting the ICEBERG_DEBUG=1 environment variable does the same."
        ),
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the iceberg CLI.

    Parses *argv* (or ``sys.argv[1:]`` when *argv* is ``None``), resolves the
    public API of the given path, and writes the result to stdout (or to the
    ``--output`` file). With
    ``--keep-going``, diagnostics go to stderr (and into the JSON output).

    Args:
        argv: Argument list to parse.  Defaults to ``sys.argv[1:]``.

    Returns:
        An integer exit code: ``0`` on success, ``1`` on a known
        ``IcebergError`` or when ``--keep-going`` skipped a module, ``2`` on
        any unexpected exception.
    """
    args = _build_parser().parse_args(argv)

    try:
        config = _resolve_config(args)
        report = get_public_api_report(args.path, config=config, keep_going=args.keep_going)
    except IcebergError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        _report_unexpected_error(exc, show_traceback=_traceback_requested(args))
        return 2

    if args.json:
        output = format_json(report.api, report.diagnostics if args.keep_going else None)
    else:
        output = format_tree(report.api, show_overload_implementation=args.show_overload_implementations)

    if args.output is None:
        print(output)
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
