"""Cost workbook: structure, formulas over named assumptions, real catalog data, LibreOffice recalculation."""

from __future__ import annotations

import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook

from advisor.ingestion import discover_documents
from advisor.models import CommercialStatus, DocumentType
from advisor.parsing import parse_catalog

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from build_tco_excel import INPUTS, SHEETS, build_workbook

pytestmark = [pytest.mark.integration, pytest.mark.data]
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def catalog():  # type: ignore[no-untyped-def]
    records = discover_documents(ROOT / "data" / "raw")
    return parse_catalog(next(r for r in records if r.doc_type is DocumentType.CATALOG))


@pytest.fixture(scope="module")
def workbook_path(tmp_path_factory: pytest.TempPathFactory, catalog) -> Path:  # type: ignore[no-untyped-def]
    return build_workbook(tmp_path_factory.mktemp("cost") / "tco.xlsx", catalog)


def test_sheets_and_assumptions_are_labelled(workbook_path: Path) -> None:
    wb = load_workbook(workbook_path)
    assert tuple(wb.sheetnames) == SHEETS
    ws = wb["Supuestos"]
    for row in ws.iter_rows(min_row=4, max_row=3 + len(INPUTS), values_only=True):
        _label, _value, _unit, kind, source, name = row
        assert kind in {"DATO", "SUPUESTO"} and source and name in wb.defined_names, row
        if kind == "SUPUESTO":
            assert "SUPUESTO" in source or "POR CONFIRMAR" in source, row


def test_totals_are_formulas(workbook_path: Path) -> None:
    wb = load_workbook(workbook_path)
    for sheet in ("Desarrollo", "Mantenimiento_1_anio", "TCO_anual"):
        formulas = [
            c.value
            for row in wb[sheet].iter_rows()
            for c in row
            if isinstance(c.value, str) and c.value.startswith("=")
        ]
        assert formulas, sheet
    assert str(wb["TCO_anual"]["B8"].value).startswith("=")


def test_inventory_rows_match_catalog(workbook_path: Path, catalog) -> None:  # type: ignore[no-untyped-def]
    ws = load_workbook(workbook_path)["Inventario"]
    rows = {r[0]: r for r in ws.iter_rows(min_row=4, max_row=3 + len(catalog), values_only=True)}
    for item in catalog:
        _, _, _, status, price, stock, _ = rows[item.part_number]
        assert status == item.status.value and stock == item.stock_units
        assert price == (float(item.price_usd) if item.price_usd is not None else None)


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice not installed")
def test_recalculates_in_libreoffice(workbook_path: Path, catalog, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    subprocess.run(
        ["soffice", f"-env:UserInstallation=file://{tmp_path}/profile", "--headless", "--calc",
         "--convert-to", "xlsx", "--outdir", str(tmp_path), str(workbook_path)],
        check=True, capture_output=True, timeout=180,
    )  # fmt: skip
    ws = load_workbook(tmp_path / workbook_path.name, data_only=True)["TCO_anual"]
    expected_inventory = sum(
        (c.price_usd or Decimal(0)) * (c.stock_units or 0)
        for c in catalog
        if c.status is CommercialStatus.ACTIVE
    )
    assert ws["B12"].value == pytest.approx(float(expected_inventory))
    assert ws["B14"].value == sum(c.status is not CommercialStatus.ACTIVE for c in catalog)
    assert ws["B8"].value > 0 and ws["B10"].value == 4_000_000
