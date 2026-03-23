"""Zero-typing demonstration fixture for iceberg show output.

This module intentionally contains no type annotations anywhere — no parameter
types, no return types, no attribute annotations, and no class variable
annotations. It exists to show what iceberg show output looks like when a
module has been written with zero type coverage, contrasting with the fully
typed standalone.py and partially typed warehouse/ package.

Domain: a simple to-do list manager with Task items and a TodoList container.
"""

__all__ = ["Task", "TodoList", "from_lines"]


class Task:
    """A single to-do item with a title, description, priority, and done state."""

    DEFAULT_PRIORITY = 1

    def __init__(self, title, description=""):
        """Initialise a Task.

        Args:
            title: The short summary of what needs to be done.
            description: Optional longer description of the task.
        """
        self.title = title
        self.description = description
        self.done = False
        self.priority = self.DEFAULT_PRIORITY

    def complete(self):
        """Mark this task as done."""
        self.done = True

    def reset(self):
        """Mark this task as not done."""
        self.done = False

    @classmethod
    def urgent(cls, title):
        """Create a high-priority Task.

        Args:
            title: The short summary of the urgent task.

        Returns:
            A new Task with priority set to 10.
        """
        task = cls(title)
        task.priority = 10
        return task

    @staticmethod
    def is_valid_title(title):
        """Return True if title is a non-empty, non-whitespace string.

        Args:
            title: The candidate title string to validate.

        Returns:
            True when the title contains at least one non-whitespace character.
        """
        return bool(title.strip())


class TodoList:
    """An ordered collection of Tasks identified by a list name."""

    def __init__(self, name):
        """Initialise an empty TodoList.

        Args:
            name: The display name for this list.
        """
        self.name = name
        self._tasks = []

    @property
    def count(self):
        """The total number of tasks in the list."""
        return len(self._tasks)

    def add(self, task):
        """Append a task to the list.

        Args:
            task: The Task to add.
        """
        self._tasks.append(task)

    def remove(self, title):
        """Remove the first task whose title matches.

        Args:
            title: The title of the task to remove.
        """
        self._tasks = [t for t in self._tasks if t.title != title]

    def pending(self):
        """Return all tasks that have not yet been completed.

        Returns:
            A list of Task objects where done is False.
        """
        return [t for t in self._tasks if not t.done]

    def complete_all(self):
        """Mark every task in the list as done."""
        for task in self._tasks:
            task.complete()


def from_lines(lines):
    """Create a Task for each non-blank line in the input.

    Args:
        lines: An iterable of strings, one potential task title per line.

    Returns:
        A list of Task objects, one per non-blank stripped line.
    """
    return [Task(line.strip()) for line in lines if line.strip()]
