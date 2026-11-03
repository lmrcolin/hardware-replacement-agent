"""Commercial engine contract. The catalog is the source of truth."""

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

    def get(self, part_number: str) -> CommercialInformation:
        """Catalog row for ``part_number``; KeyError if absent. B-14."""
        raise NotImplementedError("B-14 commercial.CommercialEngine.get")

    def availability(self, part_number: str) -> Availability:
        """Status, price (ACTIVE only) and stock from the catalog. B-14."""
        raise NotImplementedError("B-14 commercial.CommercialEngine.availability")
