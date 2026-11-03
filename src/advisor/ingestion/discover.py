"""Document discovery: list source PDFs and register them as DocumentRecord."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pymupdf

from advisor.models import DocumentRecord, DocumentType

log = logging.getLogger(__name__)

CATALOG_PREFIX = "Catalogo_Comercial"


def classify(filename: str) -> DocumentType:
    return DocumentType.CATALOG if filename.startswith(CATALOG_PREFIX) else DocumentType.DATASHEET


def _record(path: Path) -> DocumentRecord:
    data = path.read_bytes()
    with pymupdf.open(stream=data, filetype="pdf") as doc:  # type: ignore[no-untyped-call]
        pages = doc.page_count
    return DocumentRecord(
        document_id=hashlib.sha256(data).hexdigest(),
        path=str(path),
        filename=path.name,
        doc_type=classify(path.name),
        size_bytes=len(data),
        pages=pages,
    )


def discover_documents(root: Path) -> list[DocumentRecord]:
    """Every PDF directly under ``root``, sorted by filename (stable order)."""
    if not root.is_dir():
        raise FileNotFoundError(f"PDF directory not found: {root}")
    paths = sorted(p for p in root.iterdir() if p.suffix.lower() == ".pdf")
    records = [_record(p) for p in paths]
    log.info("discovered documents", extra={"root": str(root), "count": len(records)})
    return records
