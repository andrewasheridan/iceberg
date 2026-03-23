"""Domain models for the warehouse inventory system."""

__all__ = [
    "Product",
    "Warehouse",
]


class Product:
    """A product held in inventory.

    Attributes:
        TAX_RATE: The default sales-tax rate applied to all products.
        sku: The stock-keeping unit identifier.
        name: The human-readable product name.
        price: The unit price before tax (in the store's base currency).
        quantity: The number of units currently in stock.
    """

    TAX_RATE: float = 0.2

    def __init__(self, sku: str, name: str, price, quantity=0):
        """Initialise a Product.

        Args:
            sku: The unique stock-keeping unit identifier.
            name: The display name of the product.
            price: The unit price before tax.
            quantity: Initial stock quantity (defaults to ``0``).

        Raises:
            ValueError: If *price* is negative or *quantity* is negative.
        """
        if price < 0:
            raise ValueError(f"price must be non-negative, got {price}")
        if quantity < 0:
            raise ValueError(f"quantity must be non-negative, got {quantity}")
        self.sku: str = sku
        self.name: str = name
        self.price = price
        self.quantity = quantity

    @property
    def total_value(self) -> float:
        """The total pre-tax value of all units in stock (price * quantity)."""
        return self.price * self.quantity

    @property
    def price_with_tax(self):
        """The unit price after applying :attr:`TAX_RATE`."""
        return self.price * (1 + self.TAX_RATE)

    def restock(self, units: int):
        """Increase the stock quantity by *units*.

        Args:
            units: The number of units to add.

        Raises:
            ValueError: If *units* is not positive.
        """
        if units <= 0:
            raise ValueError(f"units must be positive, got {units}")
        self.quantity += units

    def sell(self, units):
        """Reduce stock by *units* and return the revenue collected.

        Args:
            units: The number of units sold.

        Returns:
            The total revenue (pre-tax price * units sold).

        Raises:
            ValueError: If *units* exceeds available stock.
        """
        if units > self.quantity:
            raise ValueError(f"cannot sell {units} units; only {self.quantity} in stock")
        self.quantity -= units
        return self.price * units

    @classmethod
    def from_dict(cls, data) -> Product:
        """Construct a Product from a plain dictionary.

        Args:
            data: A mapping with keys ``sku``, ``name``, ``price``, and
                optionally ``quantity``.

        Returns:
            A new :class:`Product` instance.
        """
        return cls(
            sku=str(data["sku"]),
            name=str(data["name"]),
            price=float(data["price"]),  # type: ignore[arg-type]
            quantity=int(str(data.get("quantity", 0))),
        )

    @staticmethod
    def is_valid_sku(sku: str) -> bool:
        """Return True if *sku* is a non-empty alphanumeric string.

        Args:
            sku: The SKU string to validate.

        Returns:
            ``True`` when *sku* contains only alphanumeric characters and is
            not empty.
        """
        return bool(sku) and sku.isalnum()


class Warehouse:
    """A named warehouse that stores an inventory of products.

    Attributes:
        name: The display name of the warehouse location.
    """

    def __init__(self, name):
        """Initialise an empty Warehouse.

        Args:
            name: The human-readable name for this warehouse location.
        """
        self.name = name
        self._products = {}

    def add(self, product):
        """Add a product to the warehouse inventory.

        If a product with the same SKU already exists it is replaced.

        Args:
            product: The :class:`Product` to store.
        """
        self._products[product.sku] = product

    def get(self, sku: str) -> Product | None:
        """Retrieve a product by its SKU.

        Args:
            sku: The stock-keeping unit identifier to look up.

        Returns:
            The matching :class:`Product`, or ``None`` if not found.
        """
        return self._products.get(sku)

    def all_products(self) -> list[Product]:
        """Return all products currently held in the warehouse.

        Returns:
            A list of :class:`Product` instances in insertion order.
        """
        return list(self._products.values())
