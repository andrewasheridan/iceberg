# warehouse — package without `__all__` in `__init__.py`

## Purpose

Demonstrates how `iceberg show` behaves when a package's `__init__.py` has
**no `__all__`**. Because there is no authoritative declaration, iceberg
reports every submodule individually using each module's own `__all__` (or
AST inference as fallback).

This package is also the **partial typing** fixture: some members carry type
annotations and others do not. This produces a visible contrast in `iceberg
show` output — annotated members appear with `: type` on attributes and
`→ return` on callables, while unannotated members appear as bare names.

## Structure

```
warehouse/
├── __init__.py   # no __all__ — re-exports Product, Warehouse, format_sku, load_csv
├── models.py     # __all__ = ["Product", "Warehouse"]
└── utils.py      # __all__ = ["format_sku", "load_csv"]
                  # SKU_PREFIX intentionally absent from __all__
```

## Typing coverage per member

### `models.py` — `Product`

| Member | Kind | Typed? |
|---|---|---|
| `TAX_RATE` | class var | Yes — `: float` |
| `__init__(sku, name, price, quantity)` | initialiser | `sku: str`, `name: str` typed; `price` and `quantity` bare; no `→ None` |
| `sku` | instance attr | Yes — `: str` |
| `name` | instance attr | Yes — `: str` |
| `price` | instance attr | No annotation |
| `quantity` | instance attr | No annotation |
| `total_value` | property | Yes — `→ float` |
| `price_with_tax` | property | No return annotation |
| `restock(units)` | method | `units: int` typed; no `→ None` |
| `sell(units)` | method | `units` bare; no return annotation |
| `from_dict(data)` | classmethod | `data` bare; `→ Product` return annotation |
| `is_valid_sku(sku)` | staticmethod | Fully typed: `sku: str`, `→ bool` |

### `models.py` — `Warehouse`

| Member | Kind | Typed? |
|---|---|---|
| `__init__(name)` | initialiser | `name` bare; no `→ None` |
| `name` | instance attr | No annotation |
| `add(product)` | method | `product` bare; no return annotation |
| `get(sku)` | method | `sku: str` typed; `→ Product | None` |
| `all_products()` | method | No params; `→ list[Product]` |

### `utils.py`

| Member | Kind | Typed? |
|---|---|---|
| `SKU_PREFIX` | module constant | No annotation (excluded from `__all__`) |
| `format_sku(prefix, number)` | function | `prefix: str` typed; `number` bare; no return annotation |
| `load_csv(path)` | function | `path` bare; `→ list[Product]` |

## What iceberg show output looks like with mixed typing

Fully typed members show `: type` on attributes and `→ return` on callables:
```
total_value (property) → float
staticmethod is_valid_sku(sku: str) → bool
```

Partially typed members show only the annotated parts:
```
restock(self, units: int)
classmethod from_dict(cls, data) → Product
format_sku(prefix: str, number)
load_csv(path) → list[Product]
```

Unannotated members appear as bare names (properties keep the `(property)` label):
```
price_with_tax (property)
sell(self, units)
name
price
```

## iceberg show output

All three modules are always shown (no suppression):
```
warehouse/
  __init__
    Product
    Warehouse
    format_sku
    load_csv
  models
    Product
      TAX_RATE: float
      sku: str
      name: str
      price
      quantity
      total_value (property) → float
      price_with_tax (property)
      restock(self, units: int)
      sell(self, units)
      classmethod from_dict(cls, data) → Product
      staticmethod is_valid_sku(sku: str) → bool
    Warehouse
      name
      add(self, product)
      get(self, sku: str) → Product | None
      all_products(self) → list[Product]
  utils
    format_sku(prefix: str, number)
    load_csv(path) → list[Product]
```

See `tests/expected/show/warehouse_tree.txt` for the complete output.
