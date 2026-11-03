"""Parsing the real PDFs in data/raw (values checked by hand against the catalog PDF)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from advisor.ingestion import discover_documents
from advisor.models import CommercialInformation, CommercialStatus, DocumentType
from advisor.parsing import parse_catalog, parse_document

pytestmark = pytest.mark.data
PDF_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"


@pytest.fixture(scope="module")
def records():  # type: ignore[no-untyped-def]
    return discover_documents(PDF_DIR)


@pytest.fixture(scope="module")
def catalog(records) -> dict[str, CommercialInformation]:  # type: ignore[no-untyped-def]
    record = next(r for r in records if r.doc_type is DocumentType.CATALOG)
    return {row.part_number: row for row in parse_catalog(record)}


def test_document_ids_are_unique(records) -> None:  # type: ignore[no-untyped-def]
    assert len({r.document_id for r in records}) == 33


def test_e810_row(catalog: dict[str, CommercialInformation]) -> None:
    row = catalog["E810-CQDA2"]
    assert row.status is CommercialStatus.DISCONTINUED
    assert row.discontinued_on == date(2025, 8, 1)
    assert row.last_buy_on == date(2026, 2, 28)
    assert row.price_usd is None and row.stock_units == 0


def test_active_row_with_price(catalog: dict[str, CommercialInformation]) -> None:
    row = catalog["MCX75310AAS-NEAT"]
    assert row.status is CommercialStatus.ACTIVE
    assert row.price_usd == Decimal("1250.00") and row.stock_units == 120


def test_wrapped_manufacturer_cells(catalog: dict[str, CommercialInformation]) -> None:
    assert catalog["USB-2633"].manufacturer == "Measurement Computing (MCC)"


def test_price_only_on_active(catalog: dict[str, CommercialInformation]) -> None:
    for row in catalog.values():
        assert (row.price_usd is not None) == (row.status is CommercialStatus.ACTIVE), (
            row.part_number
        )


def test_nrnd_rows(catalog: dict[str, CommercialInformation]) -> None:
    nrnd = {p for p, r in catalog.items() if r.status is CommercialStatus.NRND}
    assert nrnd == {"Cortex-A78", "XC7A200T", "A100-SXM4-80GB"}
    assert catalog["XC7A200T"].stock_units == 500
    assert catalog["Cortex-A78"].stock_units is None


def test_every_datasheet_has_text_and_title(records) -> None:  # type: ignore[no-untyped-def]
    for record in records:
        if record.doc_type is DocumentType.DATASHEET:
            doc = parse_document(record)
            assert doc.title and any(p.text.strip() for p in doc.pages), record.filename
