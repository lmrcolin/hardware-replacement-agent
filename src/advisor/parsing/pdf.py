"""PDF parsing contracts."""

from __future__ import annotations

from advisor.models import CommercialInformation, DocumentRecord, ParsedDocument


def parse_document(record: DocumentRecord) -> ParsedDocument:
    """Text and tables per page (pdfplumber, fallback pymupdf). B-04."""
    raise NotImplementedError("B-04 parsing.parse_document")


def parse_catalog(record: DocumentRecord) -> list[CommercialInformation]:
    """Catalog PDF → one CommercialInformation per row (expects 32, handles wrapped cells). B-03."""
    raise NotImplementedError("B-03 parsing.parse_catalog")
