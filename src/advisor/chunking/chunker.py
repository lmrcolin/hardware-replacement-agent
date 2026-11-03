"""Chunking contract."""

from __future__ import annotations

from advisor.models import Chunk, ParsedDocument


def chunk_document(
    doc: ParsedDocument, *, max_chars: int = 1500, overlap: int = 200
) -> list[Chunk]:
    """Stable chunk ids, never crossing documents, with page/section metadata. B-08."""
    raise NotImplementedError("B-08 chunking.chunk_document")
