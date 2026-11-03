"""Checks over the real source PDFs (read-only)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.data
PDF_DIR = Path(__file__).resolve().parents[2] / "datos" / "pdfs"


def test_33_pdfs_present() -> None:
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    assert len(pdfs) == 33
    assert (PDF_DIR / "Catalogo_Comercial_Precios_Inventario_2026.pdf") in pdfs


def test_pdfs_are_pdf_files() -> None:
    assert all(p.read_bytes()[:5] == b"%PDF-" for p in PDF_DIR.glob("*.pdf"))
