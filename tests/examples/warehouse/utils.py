__all__ = [
    "format_sku",
    "load_csv",
]


from warehouse.models import Product

SKU_PREFIX = "WH"


def format_sku(prefix: str, number): ...


def load_csv(path) -> list[Product]: ...
