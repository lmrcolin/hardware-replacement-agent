"""Documents, parsed pages, chunks and evidence."""

from __future__ import annotations

from pydantic import Field, model_validator

from advisor.models.base import Contract
from advisor.models.enums import DocumentType, EvidenceScope

Sha256 = str


class DocumentRecord(Contract):
    document_id: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    path: str
    filename: str
    doc_type: DocumentType
    size_bytes: int = Field(ge=0)
    pages: int | None = Field(default=None, ge=1)


class ParsedPage(Contract):
    page_number: int = Field(ge=1)
    text: str
    tables: list[list[list[str | None]]] = []


class ParsedDocument(Contract):
    document_id: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    title: str | None = None
    pages: list[ParsedPage]
    parser: str  # e.g. "pdfplumber", "pymupdf", "ai_parse_document"

    @model_validator(mode="after")
    def _pages_are_sequential(self) -> ParsedDocument:
        numbers = [p.page_number for p in self.pages]
        if numbers != list(range(1, len(numbers) + 1)):
            raise ValueError("pages must be numbered 1..N in order")
        return self


class Evidence(Contract):
    document_id: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    page: int = Field(ge=1)
    chunk_id: str | None = None
    quote: str = Field(min_length=1)
    scope: EvidenceScope = EvidenceScope.PRODUCT


class Chunk(Contract):
    chunk_id: str = Field(min_length=1)
    document_id: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    section: str | None = None
    text: str = Field(min_length=1)
    part_numbers: list[str] = []

    @model_validator(mode="after")
    def _page_range(self) -> Chunk:
        if self.page_end < self.page_start:
            raise ValueError("page_end must be >= page_start")
        return self


class ChunkHit(Contract):
    chunk: Chunk
    score: float
    retriever: str  # "bm25" | "faiss" | "hybrid" | "ai_search"
