"""PDF parsing: datasheets to ParsedDocument, commercial catalog to CommercialInformation."""

from __future__ import annotations

import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber
import pymupdf

from advisor.models import (
    Category,
    CommercialInformation,
    CommercialStatus,
    DocumentRecord,
    DocumentType,
    ParsedDocument,
    ParsedPage,
)

log = logging.getLogger(__name__)

CATALOG_COLUMNS = (
    "part number",
    "descripción",
    "fabricante",
    "categoría",
    "status",
    "fecha desc.",
    "última compra",
    "precio usd",
    "stock",
)
EMPTY_CELLS = {"", "-", "—", "n/a"}


class CatalogParseError(ValueError):
    """The catalog PDF does not have the expected table layout."""


def clean_cell(value: str | None) -> str | None:
    """Join wrapped lines, collapse whitespace; placeholders such as '-' become None."""
    if value is None:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return None if text.lower() in EMPTY_CELLS else text


def parse_decimal(value: str | None) -> Decimal | None:
    text = clean_cell(value)
    if text is None:
        return None
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation as exc:
        raise CatalogParseError(f"invalid price: {value!r}") from exc


def parse_int(value: str | None) -> int | None:
    number = parse_decimal(value)
    if number is None:
        return None
    if number != number.to_integral_value():
        raise CatalogParseError(f"expected an integer, got {value!r}")
    return int(number)


def parse_date(value: str | None) -> date | None:
    text = clean_cell(value)
    return date.fromisoformat(text) if text else None


def _title(text: str) -> str | None:
    first = next((line.strip() for line in text.splitlines() if line.strip()), None)
    return first.removesuffix(" - DATASHEET").strip() if first else None


def _pages_pdfplumber(path: Path) -> list[ParsedPage]:
    with pdfplumber.open(path) as pdf:
        return [
            ParsedPage(page_number=i, text=page.extract_text() or "", tables=page.extract_tables())
            for i, page in enumerate(pdf.pages, start=1)
        ]


def _pages_pymupdf(path: Path) -> list[ParsedPage]:
    with pymupdf.open(path) as doc:  # type: ignore[no-untyped-call]
        return [
            ParsedPage(page_number=i, text=str(page.get_text()))
            for i, page in enumerate(doc, start=1)
        ]


def parse_document(record: DocumentRecord) -> ParsedDocument:
    """Text and tables per page with pdfplumber; pymupdf fallback when no text is found."""
    path = Path(record.path)
    pages, parser = _pages_pdfplumber(path), "pdfplumber"
    if not any(p.text.strip() for p in pages):
        pages, parser = _pages_pymupdf(path), "pymupdf"
    if not any(p.text.strip() for p in pages):
        log.warning("no text layer", extra={"document": record.filename})
    return ParsedDocument(
        document_id=record.document_id,
        title=_title(pages[0].text) if pages else None,
        pages=pages,
        parser=parser,
    )


def _check_header(row: list[str | None]) -> None:
    header = tuple((clean_cell(c) or "").lower() for c in row)
    if header != CATALOG_COLUMNS:
        raise CatalogParseError(f"unexpected catalog header: {header}")


def _row_to_commercial(row: list[str | None]) -> CommercialInformation:
    part, desc, maker, cat, status, disc, last_buy, price, stock = (row + [None] * 9)[:9]
    part_number = clean_cell(part)
    if not part_number:
        raise CatalogParseError(f"row without part number: {row}")
    try:
        return CommercialInformation(
            part_number=part_number,
            description=clean_cell(desc) or "",
            manufacturer=clean_cell(maker) or "",
            category=Category(clean_cell(cat) or ""),
            status=CommercialStatus(clean_cell(status) or ""),
            discontinued_on=parse_date(disc),
            last_buy_on=parse_date(last_buy),
            price_usd=parse_decimal(price),
            stock_units=parse_int(stock),
        )
    except ValueError as exc:
        raise CatalogParseError(f"{part_number}: {exc}") from exc


def parse_catalog(record: DocumentRecord) -> list[CommercialInformation]:
    """One CommercialInformation per catalog row; header repeated on every page."""
    if record.doc_type is not DocumentType.CATALOG:
        raise CatalogParseError(f"{record.filename} is not the commercial catalog")
    rows: list[CommercialInformation] = []
    with pdfplumber.open(record.path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                if not table:
                    continue
                _check_header(table[0])
                rows.extend(_row_to_commercial(r) for r in table[1:] if any(r))
    parts = [r.part_number for r in rows]
    duplicates = {p for p in parts if parts.count(p) > 1}
    if duplicates:
        raise CatalogParseError(f"duplicated part numbers: {sorted(duplicates)}")
    log.info("parsed catalog", extra={"rows": len(rows)})
    return rows
