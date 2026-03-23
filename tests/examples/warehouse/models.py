__all__ = [
    "Product",
    "Warehouse",
]


class Product:
    TAX_RATE: float = 0.2

    def __init__(self, sku: str, name: str, price, quantity=0):
        self.sku: str = sku
        self.name: str = name
        self.price = price
        self.quantity = quantity

    @property
    def total_value(self) -> float: ...

    @property
    def price_with_tax(self): ...

    def restock(self, units: int): ...
    def sell(self, units): ...

    @classmethod
    def from_dict(cls, data) -> Product: ...

    @staticmethod
    def is_valid_sku(sku: str) -> bool: ...


class Warehouse:
    def __init__(self, name):
        self.name = name
        self._products = {}

    def add(self, product): ...
    def get(self, sku: str) -> Product | None: ...
    def all_products(self) -> list[Product]: ...
