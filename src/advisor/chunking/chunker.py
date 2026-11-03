"""Chunking: one chunk per datasheet section, split further only when longer than ``max_chars``."""

from __future__ import annotations

from advisor.extraction import Segment, document_part_number, segments
from advisor.models import Chunk, ParsedDocument


def _merge_header_segments(segs: list[Segment]) -> list[Segment]:
    """Consecutive heading-less segments (title + 'Manufacturer:' lines) become one chunk."""
    merged: list[Segment] = []
    for seg in segs:
        prev = merged[-1] if merged else None
        if prev and not seg.heading and not prev.heading and prev.page == seg.page:
            merged[-1] = Segment(prev.page, "", f"{prev.text} {seg.text}")
        else:
            merged.append(seg)
    return merged


def _windows(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    out, start = [], 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):  # cut at the last sentence/word boundary inside the window
            cut = max(text.rfind(". ", start, end), text.rfind(" ", start, end))
            end = cut + 1 if cut > start else end
        out.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [w for w in out if w]


def chunk_document(
    doc: ParsedDocument, *, max_chars: int = 1500, overlap: int = 200
) -> list[Chunk]:
    """Stable chunk ids ``<doc12>:<page>:<n>``; chunks never cross documents."""
    if overlap >= max_chars:
        raise ValueError("overlap must be smaller than max_chars")
    part = document_part_number(doc)
    chunks: list[Chunk] = []
    for i, seg in enumerate(_merge_header_segments(segments(doc))):
        # Keep the datasheet title searchable: it is a heading, so no segment contains it.
        text = f"{doc.title}. {seg.text}" if i == 0 and doc.title else seg.text
        for piece in _windows(text, max_chars, overlap):
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.document_id[:12]}:{seg.page}:{len(chunks)}",
                    document_id=doc.document_id,
                    page_start=seg.page,
                    page_end=seg.page,
                    section=seg.heading or None,
                    text=piece,
                    part_numbers=[part] if part else [],
                )
            )
    return chunks
