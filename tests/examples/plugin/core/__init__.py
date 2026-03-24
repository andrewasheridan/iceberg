__all__ = ["Plugin", "Registry"]


class Plugin:
    name: str
    version: str

    def __init__(self, name: str, version: str = "0.1.0") -> None:
        self.name: str = name
        self.version: str = version

    def load(self) -> bool: ...
    def unload(self) -> None: ...


class Registry:
    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}

    def register(self, plugin: Plugin) -> None: ...
    def get(self, name: str) -> Plugin | None: ...
    def all_plugins(self) -> list[Plugin]: ...
