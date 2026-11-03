"""Document discovery contract."""

from __future__ import annotations

from pathlib import Path

from advisor.models import DocumentRecord


def discover_documents(root: Path) -> list[DocumentRecord]:
    """List every PDF under ``root`` (sha256 id, type CATALOG/DATASHEET, page count). B-02/B-04."""
    raise NotImplementedError("B-04 ingestion.discover_documents")
