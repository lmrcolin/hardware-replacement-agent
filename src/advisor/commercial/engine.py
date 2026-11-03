"""Commercial engine. The catalog is the source of truth for status, price and stock."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import NamedTuple

from advisor.models import CommercialInformation, CommercialStatus


class Availability(NamedTuple):
    status: CommercialStatus
    price_usd: Decimal | None  # only for ACTIVE
    stock_units: int | None


class CommercialEngine:
    def __init__(self, catalog: Sequence[CommercialInformation]) -> None:
        self.catalog = list(catalog)
        self._by_part = {row.part_number: row for row in self.catalog}
        if len(self._by_part) != len(self.catalog):
            raise ValueError("duplicated part numbers in catalog")

    def get(self, part_number: str) -> CommercialInformation:
        """Catalog row for ``part_number``; KeyError if absent."""
        return self._by_part[part_number]

    def availability(self, part_number: str) -> Availability:
        """Status, price (ACTIVE only, never shown otherwise) and stock from the catalog."""
        row = self.get(part_number)
        price = row.price_usd if row.status is CommercialStatus.ACTIVE else None
        return Availability(row.status, price, row.stock_units)

    def is_sellable(self, part_number: str) -> bool:
        return self.get(part_number).status is CommercialStatus.ACTIVE
