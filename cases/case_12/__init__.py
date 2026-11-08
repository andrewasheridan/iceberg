"""Case 12 - re-exports bound inside try/except fallbacks."""

__all__ = ["parse", "version"]

try:
    from ._fast import parse
except ImportError:
    from ._slow import parse

try:
    from ._version import version
except ImportError:
    version = "0.0.0"
