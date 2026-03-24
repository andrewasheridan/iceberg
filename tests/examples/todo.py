class Task:
    DEFAULT_PRIORITY = 1

    def __init__(self, title, description=""):
        self.title = title
        self.description = description
        self.done = False
        self.priority = self.DEFAULT_PRIORITY

    def complete(self): ...
    def reset(self): ...

    @classmethod
    def urgent(cls, title): ...

    @staticmethod
    def is_valid_title(title): ...


class TodoList:
    def __init__(self, name):
        self.name = name
        self._tasks = []

    @property
    def count(self): ...

    def add(self, task): ...
    def remove(self, title): ...
    def pending(self): ...
    def complete_all(self): ...


def from_lines(lines): ...
