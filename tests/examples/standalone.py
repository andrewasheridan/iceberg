"""A small library-card system demonstrating the full iceberg show surface.

This module is a self-contained fixture used by functional tests for
``iceberg show``. It exercises every category that ``show`` can report:

- Module-level annotated constants
- Classes with class variables, instance attributes, properties, instance
  methods, classmethods, and staticmethods
- Top-level functions with typed parameters and default values

The domain is a simple library borrowing system: ``Book``, ``Library``,
and the ``add_shelf`` helper function.
"""

__all__ = [
    "Book",
    "Library",
    "add_shelf",
]

import datetime


class Book:
    """A book that can be borrowed from a library.

    Attributes:
        DEFAULT_LOAN_DAYS: The default number of days a book may be borrowed.
        title: The title of the book.
        author: The name of the author.
        isbn: The ISBN-13 identifier.
        available: Whether the book is currently available to borrow.
    """

    DEFAULT_LOAN_DAYS: int = 14

    def __init__(self, title: str, author: str, isbn: str) -> None:
        """Initialise a new Book.

        Args:
            title: The title of the book.
            author: The name of the author.
            isbn: The ISBN-13 identifier string.
        """
        self.title: str = title
        self.author: str = author
        self.isbn: str = isbn
        self.available: bool = True
        self._due_date: datetime.date | None = None

    @property
    def due_date(self) -> datetime.date | None:
        """The date the book is due back, or None if it is on the shelf."""
        return self._due_date

    def borrow(self, loan_days: int = DEFAULT_LOAN_DAYS) -> datetime.date:
        """Mark the book as borrowed and return the due date.

        Args:
            loan_days: Number of days for the loan period.

        Returns:
            The date the book must be returned by.

        Raises:
            ValueError: If the book is not currently available.
        """
        if not self.available:
            raise ValueError(f"{self.title!r} is already on loan.")
        self.available = False
        self._due_date = datetime.date.today() + datetime.timedelta(days=loan_days)
        return self._due_date

    def return_book(self) -> None:
        """Mark the book as returned and clear its due date."""
        self.available = True
        self._due_date = None

    @classmethod
    def from_record(cls, record: dict[str, str]) -> Book:
        """Construct a Book from a dictionary record.

        Args:
            record: A mapping with keys ``title``, ``author``, and ``isbn``.

        Returns:
            A new :class:`Book` instance.
        """
        return cls(
            title=record["title"],
            author=record["author"],
            isbn=record["isbn"],
        )

    @staticmethod
    def is_valid_isbn(isbn: str) -> bool:
        """Return True if *isbn* looks like a well-formed ISBN-13.

        Args:
            isbn: The string to validate.

        Returns:
            ``True`` when *isbn* is exactly 13 digits, ``False`` otherwise.
        """
        return isbn.isdigit() and len(isbn) == 13


class Library:
    """A collection of books organised into named shelves.

    Attributes:
        name: The display name of the library.
    """

    def __init__(self, name: str) -> None:
        """Initialise a new Library.

        Args:
            name: The human-readable name of the library branch.
        """
        self.name: str = name
        self._shelves: dict[str, list[Book]] = {}

    @property
    def shelf_names(self) -> list[str]:
        """Sorted list of shelf names currently in the library."""
        return sorted(self._shelves)

    def add_shelf(self, shelf: str) -> None:
        """Add a new empty shelf by name.

        Args:
            shelf: The label for the new shelf (e.g. ``"Fiction"``).
        """
        self._shelves.setdefault(shelf, [])

    def shelve(self, book: Book, shelf: str) -> None:
        """Place a book on the named shelf.

        Args:
            book: The book to shelve.
            shelf: The target shelf label; created if it does not exist.
        """
        self._shelves.setdefault(shelf, [])
        self._shelves[shelf].append(book)

    def find_by_isbn(self, isbn: str) -> Book | None:
        """Search all shelves for a book with the given ISBN.

        Args:
            isbn: The ISBN-13 to search for.

        Returns:
            The matching :class:`Book`, or ``None`` if not found.
        """
        for books in self._shelves.values():
            for book in books:
                if book.isbn == isbn:
                    return book
        return None


#: Maximum number of shelves a single library may hold.
MAX_SHELVES: int = 100


def add_shelf(library: Library, name: str, *, allow_duplicates: bool = False) -> bool:
    """Add a named shelf to *library*, optionally skipping duplicates.

    Args:
        library: The :class:`Library` to modify.
        name: The shelf label to add.
        allow_duplicates: When ``False`` (default), return ``False`` without
            adding if the shelf already exists.

    Returns:
        ``True`` if the shelf was added, ``False`` if it was skipped.
    """
    if not allow_duplicates and name in library.shelf_names:
        return False
    library.add_shelf(name)
    return True
