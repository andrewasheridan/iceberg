__all__ = ["BaseFormat"]


class BaseFormat:
    name: str

    def __init__(self, name: str) -> None:
        self.name: str = name

    def serialize(self, data: object) -> str: ...
    def deserialize(self, text: str) -> object: ...
