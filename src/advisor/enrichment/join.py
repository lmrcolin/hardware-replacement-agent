"""Catalog ↔ datasheet join contract."""

from __future__ import annotations

from collections.abc import Sequence

from advisor.models import CommercialInformation, JoinReport, Product


def join_catalog(
    products: Sequence[Product], commercial: Sequence[CommercialInformation]
) -> tuple[list[Product], JoinReport]:
    """Attach catalog rows to products (catalog wins on status/price/stock). B-07."""
    raise NotImplementedError("B-07 enrichment.join_catalog")
