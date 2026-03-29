"""Enumerations used across sheridan-iceberg."""

__all__ = [
    "MemberKind",
    "ParamKind",
    "ShowFormat",
]

from enum import StrEnum, auto


class ShowFormat(StrEnum):
    """Supported output formats for the show command."""

    tree = auto()
    json = auto()


class ParamKind(StrEnum):
    """Kind of a function parameter, matching Python's parameter categories.

    Attributes:
        positional_only: Parameter before the ``/`` separator.
        positional_or_keyword: Regular parameter, passable by position or name.
        var_positional: ``*args`` parameter.
        keyword_only: Parameter after ``*`` or ``*args``, keyword-only.
        var_keyword: ``**kwargs`` parameter.
    """

    positional_only = auto()
    positional_or_keyword = auto()
    var_positional = auto()
    keyword_only = auto()
    var_keyword = auto()


class MemberKind(StrEnum):
    """Kind of a public class member.

    Attributes:
        class_var: Class-level variable or annotated attribute.
        instance_attr: Instance attribute assigned in ``__init__``.
        property: ``@property``-decorated method.
        classmethod: ``@classmethod``-decorated method.
        staticmethod: ``@staticmethod``-decorated method.
        method: Regular instance method.
    """

    class_var = auto()
    instance_attr = auto()
    property = auto()
    classmethod = auto()
    staticmethod = auto()
    method = auto()
