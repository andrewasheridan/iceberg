"""Warehouse inventory management package.

This package tracks products stored in warehouses and provides utilities for
loading inventory data from CSV files.

Unlike the ``geometry`` package, this ``__init__.py`` declares **no** ``__all__``.
When ``iceberg show`` encounters a package whose ``__init__.py`` has no
``__all__``, it reports each submodule individually — ``models`` and ``utils``
— each using their own ``__all__`` to determine the public API surface.

Running with ``--use-ast`` produces the same per-module view regardless of
whether ``__init__.py`` declares ``__all__``.
"""

from warehouse.models import Product as Product
from warehouse.models import Warehouse as Warehouse
from warehouse.utils import format_sku as format_sku
from warehouse.utils import load_csv as load_csv
