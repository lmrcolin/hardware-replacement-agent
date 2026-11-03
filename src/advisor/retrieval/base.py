"""Retriever interface and backends (stubs)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

from advisor.models import Chunk, ChunkHit


class Retriever(ABC):
    name: str

    @abstractmethod
    def search(
        self, query: str, *, top_k: int = 8, filters: Mapping[str, str] | None = None
    ) -> list[ChunkHit]:
        """Best-first hits; every hit keeps document_id/page/chunk_id for citations."""


class BM25Retriever(Retriever):
    name = "bm25"

    def __init__(self, chunks: Sequence[Chunk]) -> None:
        self.chunks = list(chunks)

    def search(
        self, query: str, *, top_k: int = 8, filters: Mapping[str, str] | None = None
    ) -> list[ChunkHit]:
        raise NotImplementedError("B-13 retrieval.BM25Retriever.search")


class FaissRetriever(Retriever):
    name = "faiss"

    def __init__(self, chunks: Sequence[Chunk], model_name: str) -> None:
        self.chunks = list(chunks)
        self.model_name = model_name

    def search(
        self, query: str, *, top_k: int = 8, filters: Mapping[str, str] | None = None
    ) -> list[ChunkHit]:
        raise NotImplementedError("B-13 retrieval.FaissRetriever.search")


class AISearchRetriever(Retriever):
    """Optional Databricks AI Search (Delta Sync index). Requires FEATURE_MATRIX = OK."""

    name = "ai_search"

    def __init__(self, endpoint: str, index: str, profile: str) -> None:
        self.endpoint, self.index, self.profile = endpoint, index, profile

    def search(
        self, query: str, *, top_k: int = 8, filters: Mapping[str, str] | None = None
    ) -> list[ChunkHit]:
        raise NotImplementedError("retrieval.AISearchRetriever.search (optional)")
