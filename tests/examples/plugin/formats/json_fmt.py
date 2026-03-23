__all__ = ["JsonFormat"]

from plugin.formats.base import BaseFormat


class JsonFormat(BaseFormat):
    indent: int

    def __init__(self, indent: int = 2) -> None:
        self.indent: int = indent

    def serialize(self, data: object) -> str: ...
    def deserialize(self, text: str) -> object: ...
