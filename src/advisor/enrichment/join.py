"""Catalog ↔ datasheet join. The catalog is the source of truth for identity, status and stock."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from rapidfuzz import fuzz

from advisor.models import CommercialInformation, JoinReport, Product

log = logging.getLogger(__name__)

FUZZY_THRESHOLD = 85.0


def normalize_part(part: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", part.upper())


def _match(
    product: Product, catalog: Sequence[CommercialInformation]
) -> tuple[CommercialInformation, str] | None:
    """Exact → normalized → unique prefix → unique fuzzy (description) match."""
    by_part = {row.part_number: row for row in catalog}
    if product.part_number in by_part:
        return by_part[product.part_number], "exact"
    norm = normalize_part(product.part_number)
    by_norm = {normalize_part(row.part_number): row for row in catalog}
    if norm in by_norm:
        return by_norm[norm], "normalized"
    prefixed = [row for key, row in by_norm.items() if key.startswith(norm) or norm.startswith(key)]
    if len(prefixed) == 1:
        return prefixed[0], "prefix"
    if product.description:
        scored = sorted(
            ((fuzz.token_set_ratio(product.description, row.description), row) for row in catalog),
            key=lambda pair: pair[0],
            reverse=True,
        )
        best = scored[0] if scored else None
        runner_up = scored[1][0] if len(scored) > 1 else 0.0
        if best and best[0] >= FUZZY_THRESHOLD and best[0] > runner_up:
            return best[1], f"fuzzy({best[0]:.0f})"
    return None


def _datasheet_status(product: Product) -> str | None:
    spec = next((s for s in product.specifications if s.key == "datasheet_status"), None)
    if spec is None or not isinstance(spec.value, str):
        return None
    return spec.value.split()[0].upper()


def _enrich(product: Product, row: CommercialInformation) -> Product:
    return Product.model_validate(
        {
            **product.model_dump(exclude={"commercial"}),
            "part_number": row.part_number,
            "manufacturer": row.manufacturer,
            "category": row.category,
            "description": row.description,
            "commercial": row,
        }
    )


def join_catalog(
    products: Sequence[Product], commercial: Sequence[CommercialInformation]
) -> tuple[list[Product], JoinReport]:
    """Attach catalog rows to products; every catalog row yields exactly one Product."""
    joined: dict[str, Product] = {}
    matched: dict[str, str] = {}
    unmatched_documents: list[str] = []
    status_conflicts: list[str] = []
    notes: list[str] = []

    for product in products:
        hit = _match(product, commercial)
        doc_id = product.document_ids[0] if product.document_ids else product.part_number
        if hit is None:
            unmatched_documents.append(doc_id)
            notes.append(f"{product.part_number}: no catalog row matches this datasheet")
            continue
        row, method = hit
        if row.part_number in joined:
            unmatched_documents.append(doc_id)
            notes.append(f"{product.part_number}: catalog row {row.part_number} already matched")
            continue
        if method != "exact":
            notes.append(f"{product.part_number} → {row.part_number} ({method})")
        if product.category is not row.category:
            notes.append(
                f"{row.part_number}: datasheet category {product.category} overridden by catalog"
                f" {row.category}"
            )
        sheet_status = _datasheet_status(product)
        if sheet_status and sheet_status != row.status.value:
            status_conflicts.append(
                f"{row.part_number}: datasheet says {sheet_status}, catalog says {row.status}"
            )
        joined[row.part_number] = _enrich(product, row)
        matched[row.part_number] = doc_id

    for row in commercial:
        if row.part_number not in joined:
            notes.append(f"{row.part_number}: catalog row without datasheet")
            joined[row.part_number] = Product(
                part_number=row.part_number,
                manufacturer=row.manufacturer,
                category=row.category,
                description=row.description,
                commercial=row,
            )

    report = JoinReport(
        matched=matched,
        unmatched_catalog=sorted(set(r.part_number for r in commercial) - set(matched)),
        unmatched_documents=unmatched_documents,
        status_conflicts=status_conflicts,
        notes=notes,
    )
    log.info(
        "joined catalog",
        extra={"matched": len(matched), "unmatched_catalog": len(report.unmatched_catalog)},
    )
    return sorted(joined.values(), key=lambda p: p.part_number), report
