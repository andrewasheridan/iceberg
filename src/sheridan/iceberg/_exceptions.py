"""Exception hierarchy for the iceberg package.

All exceptions raised by iceberg are subclasses of ``IcebergError``, allowing
callers to catch the entire family with a single clause when desired.
"""

__all__ = ["ConfigError", "IcebergError", "InvalidPathError", "ParseError", "SnapshotError", "SourceReadError"]


class IcebergError(Exception):
    """Base class for all iceberg exceptions.

    Catch this to handle any error raised by the iceberg package without
    needing to enumerate each subclass.
    """


class InvalidPathError(IcebergError):
    """Raised when a supplied path does not exist or is not a valid target.

    A valid target is either a ``.py`` file or a Python package directory.
    Any other path, or a path that does not exist on the filesystem, triggers
    this exception.
    """


class ParseError(IcebergError):
    """Raised when a source file cannot be parsed as valid Python.

    Wraps syntax errors or any other condition that prevents the AST from
    being constructed from a source file. When the location of the problem is
    known, ``str()`` prefixes the message with ``path:lineno:offset:``.

    Attributes:
        message: The bare error message, without location.
        path: The file that failed to parse, or ``None`` when not known.
        lineno: The 1-based line of the error, or ``None`` when not known.
        offset: The 1-based column of the error, or ``None`` when not known.
    """

    def __init__(
        self,
        message: str,
        *,
        path: str | None = None,
        lineno: int | None = None,
        offset: int | None = None,
    ) -> None:
        """Store the message and the location of the error.

        Args:
            message: The bare error message.
            path: The file that failed to parse.
            lineno: The 1-based line of the error.
            offset: The 1-based column of the error.
        """
        self.message = message
        self.path = path
        self.lineno = lineno
        self.offset = offset

        location = [str(part) for part in (path, lineno, offset) if part is not None]
        if location:
            super().__init__(f"{':'.join(location)}: {message}")
        else:
            super().__init__(message)

    @classmethod
    def from_syntax_error(cls, exc: SyntaxError) -> ParseError:
        """Build a ``ParseError`` from the location data in *exc*.

        Args:
            exc: The ``SyntaxError`` raised by ``ast.parse`` or ``compile``.
                A filename of ``"<unknown>"`` (the ``ast.parse`` default) is
                treated as no path.

        Returns:
            A ``ParseError`` carrying the message, path, line and column of *exc*.
        """
        path = exc.filename if exc.filename and exc.filename != "<unknown>" else None

        return cls(exc.msg or str(exc), path=path, lineno=exc.lineno, offset=exc.offset)


class SourceReadError(IcebergError):
    """Raised when a source file cannot be read or decoded.

    Covers files that cannot be opened (missing, broken symlink, no
    permission) and files whose bytes do not match their encoding: UTF-8 by
    default, or the encoding named in a PEP 263 declaration. ``str()``
    prefixes the message with ``path:``.

    Attributes:
        message: The bare error message, without the path.
        path: The file that could not be read.
    """

    def __init__(self, message: str, *, path: str) -> None:
        """Store the message and the path of the file.

        Args:
            message: The bare error message.
            path: The file that could not be read.
        """
        self.message = message
        self.path = path

        super().__init__(f"{path}: {message}")


class ConfigError(IcebergError):
    """Raised when iceberg configuration is malformed or contains bad values.

    Triggered by a malformed ``.iceberg.toml`` or ``[tool.iceberg]`` table
    inside ``pyproject.toml``, including invalid TOML syntax and
    type-incorrect field values.
    """


class SnapshotError(IcebergError):
    """Raised when JSON cannot be loaded back into iceberg models.

    Triggered by text that is not valid JSON, a ``schema_version`` that is
    missing or not supported by this version of iceberg, and nodes with a
    missing field, a field of the wrong type, or an unexpected ``node_type``.
    """
