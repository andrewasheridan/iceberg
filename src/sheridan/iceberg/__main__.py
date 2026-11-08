"""Entry point for ``python -m sheridan.iceberg``."""

from sheridan.iceberg._cli import main

__all__: list[str] = []

if __name__ == "__main__":
    raise SystemExit(main())
