"""Define the exception hierarchy of the iceberg package.

All the exceptions that iceberg raises are subclasses of ``IcebergError``. Thus,
callers can catch all of them with one ``except`` clause.
"""

__all__ = [
    "ConfigError",
    "IcebergError",
    "InvalidPathError",
    "NotFoundError",
    "ParseError",
    "SnapshotError",
    "SourceReadError",
]


class IcebergError(Exception):
    """The base class for all iceberg exceptions.

    Catch this class to handle all the errors that the iceberg package raises.
    Then you do not have to list each subclass.
    """


class InvalidPathError(IcebergError):
    """The error for a path that does not exist or is not a valid target.

    A valid target is a ``.py`` file or a Python package directory. iceberg
    raises this exception for all other paths, and for a path that does not
    exist on the filesystem.
    """


class NotFoundError(IcebergError, LookupError):
    """The error for a search by name that finds nothing in a valid source.

    The source is correct. Thus, this error is different from
    ``InvalidPathError``. It is also a ``LookupError``. Thus, callers that
    catch ``LookupError`` continue to work.
    """


class ParseError(IcebergError):
    """The error for a source file that is not valid Python.

    This error wraps syntax errors, and all other conditions that stop the
    construction of the AST from a source file. If the location of the problem
    is known, ``str()`` puts ``path:lineno:offset:`` before the message.

    Attributes:
        message: The bare error message, without the location.
        path: The file that iceberg cannot parse, or ``None`` if it is not known.
        lineno: The 1-based line of the error, or ``None`` if it is not known.
        offset: The 1-based column of the error, or ``None`` if it is not known.
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
            path: The file that iceberg cannot parse.
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
            exc: The ``SyntaxError`` from ``ast.parse`` or ``compile``. The
                method ignores the filename ``"<unknown>"`` (the default of
                ``ast.parse``) and uses no path.

        Returns:
            A ``ParseError`` with the message, the path, the line and the column
            of *exc*.
        """
        path = exc.filename if exc.filename and exc.filename != "<unknown>" else None

        return cls(exc.msg or str(exc), path=path, lineno=exc.lineno, offset=exc.offset)


class SourceReadError(IcebergError):
    """The error for a source file that iceberg cannot read or decode.

    This error is for these files:

    - Files that iceberg cannot open: a missing file, a broken symlink, or a
      file without read permission.
    - Files with bytes that do not agree with their encoding. The encoding is
      UTF-8, or the encoding that a PEP 263 declaration gives.

    ``str()`` puts ``path:`` before the message.

    Attributes:
        message: The bare error message, without the path.
        path: The file that iceberg cannot read.
    """

    def __init__(self, message: str, *, path: str) -> None:
        """Store the message and the path of the file.

        Args:
            message: The bare error message.
            path: The file that iceberg cannot read.
        """
        self.message = message
        self.path = path

        super().__init__(f"{path}: {message}")


class ConfigError(IcebergError):
    """The error for an iceberg configuration that has an incorrect structure or bad values.

    iceberg raises this error for an incorrect ``.iceberg.toml`` file or
    ``[tool.iceberg]`` table in ``pyproject.toml``. Examples are TOML syntax
    errors and field values of the wrong type.
    """


class SnapshotError(IcebergError):
    """The error for JSON that iceberg cannot load back into its models.

    iceberg raises this error for these problems:

    - The text is not valid JSON.
    - The ``schema_version`` is missing, or this version of iceberg does not
      support it.
    - A node has a missing field, a field of the wrong type, or an unexpected
      ``node_type``.
    """
