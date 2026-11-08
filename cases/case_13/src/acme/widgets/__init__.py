"""Case 13 - re-exports via absolute imports that include the namespace prefix."""

__all__ = ["make_widget"]

from acme.widgets._core import make_widget
