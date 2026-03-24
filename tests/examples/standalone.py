"""Library-card system — fully typed, partial __all__."""

__all__ = ["Book", "Library", "add_shelf"]

import datetime

MAX_SHELVES: int = 100


class Book:
    DEFAULT_LOAN_DAYS: int = 14

    def __init__(self, title: str, author: str, isbn: str) -> None:
        self.title: str = title
        self.author: str = author
        self.isbn: str = isbn
        self.available: bool = True
        self._due_date: datetime.date | None = None

    @property
    def due_date(self) -> datetime.date | None: ...

    @due_date.setter
    def due_date(self, value: datetime.date | None) -> None: ...

    def borrow(self, loan_days: int = DEFAULT_LOAN_DAYS) -> datetime.date: ...
    def return_book(self) -> None: ...

    @classmethod
    def from_record(cls, record: dict[str, str]) -> Book: ...

    @staticmethod
    def is_valid_isbn(isbn: str) -> bool: ...


class Library:
    def __init__(self, name: str) -> None:
        self.name: str = name
        self._shelves: dict[str, list[Book]] = {}

    @property
    def shelf_names(self) -> list[str]: ...

    def add_shelf(self, shelf: str) -> None: ...
    def shelve(self, book: Book, shelf: str) -> None: ...
    def find_by_isbn(self, isbn: str) -> Book | None: ...


def add_shelf(library: Library, name: str, *, allow_duplicates: bool = False) -> bool: ...
