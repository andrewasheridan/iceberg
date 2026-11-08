"""Exception hierarchy for the iceberg package.

All exceptions raised by iceberg are subclasses of ``IcebergError``, allowing
callers to catch the entire family with a single clause when desired.
"""

__all__ = ["ConfigError", "IcebergError", "InvalidPathError", "ParseError"]


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
    being constructed from a source file.
    """


class ConfigError(IcebergError):
    """Raised when iceberg configuration is malformed or contains bad values.

    Triggered by a malformed ``.iceberg.toml`` or ``[tool.iceberg]`` table
    inside ``pyproject.toml``, including invalid TOML syntax and
    type-incorrect field values.
    """
