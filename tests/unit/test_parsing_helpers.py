from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from advisor.ingestion.discover import classify
from advisor.models import DocumentType
from advisor.parsing.pdf import (
    CatalogParseError,
    clean_cell,
    parse_date,
    parse_decimal,
    parse_int,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Measurement Computing\n(MCC)", "Measurement Computing (MCC)"),
        ("  Intel  ", "Intel"),
        ("-", None),
        ("", None),
        (None, None),
    ],
)
def test_clean_cell(raw: str | None, expected: str | None) -> None:
    assert clean_cell(raw) == expected


def test_numbers_with_thousands_separator() -> None:
    assert parse_decimal("2,150.00") == Decimal("2150.00")
    assert parse_int("50,000") == 50000
    assert parse_int("-") is None


def test_invalid_numbers_raise() -> None:
    with pytest.raises(CatalogParseError):
        parse_decimal("abc")
    with pytest.raises(CatalogParseError):
        parse_int("1.5")


def test_dates() -> None:
    assert parse_date("2025-08-01") == date(2025, 8, 1)
    assert parse_date("-") is None


def test_classify() -> None:
    assert classify("Catalogo_Comercial_Precios_Inventario_2026.pdf") is DocumentType.CATALOG
    assert classify("Intel_E810_100GbE_NIC.pdf") is DocumentType.DATASHEET
