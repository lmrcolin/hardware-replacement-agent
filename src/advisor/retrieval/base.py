"""Retriever interface and backends (BM25 implemented; FAISS and AI Search pending)."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

from rank_bm25 import BM25Okapi

from advisor.models import Chunk, ChunkHit


class Retriever(ABC):
    name: str

    @abstractmethod
    def search(
        self, query: str, *, top_k: int = 8, filters: Mapping[str, str] | None = None
    ) -> list[ChunkHit]:
        """Best-first hits; every hit keeps document_id/page/chunk_id for citations."""


def tokenize(text: str) -> list[str]:
    """Lowercase tokens that keep part numbers whole ('e810-cqda2', '100gbe') plus their pieces."""
    tokens: list[str] = []
    for token in re.findall(r"[a-z0-9]+(?:[-.][a-z0-9]+)*", text.lower()):
        tokens.append(token)
        pieces = re.split(r"[-.]", token)
        if len(pieces) > 1:
            tokens.extend(p for p in pieces if p)
    return tokens


def _matches(chunk: Chunk, filters: Mapping[str, str] | None) -> bool:
    if not filters:
        return True
    if "document_id" in filters and chunk.document_id != filters["document_id"]:
        return False
    return not ("part_number" in filters and filters["part_number"] not in chunk.part_numbers)


class BM25Retriever(Retriever):
    """Lexical retrieval: strong on part numbers, acronyms (RDMA, IPsec) and values."""

    name = "bm25"

    def __init__(self, chunks: Sequence[Chunk]) -> None:
        self.chunks = list(chunks)
        corpus = [tokenize(f"{c.section or ''} {c.text}") for c in self.chunks]
        self._index = BM25Okapi(corpus) if self.chunks else None

    def search(
        self, query: str, *, top_k: int = 8, filters: Mapping[str, str] | None = None
    ) -> list[ChunkHit]:
        if self._index is None or top_k <= 0:
            return []
        scores = self._index.get_scores(tokenize(query))
        ranked = sorted(
            (i for i, c in enumerate(self.chunks) if scores[i] > 0 and _matches(c, filters)),
            key=lambda i: (-scores[i], self.chunks[i].chunk_id),
        )
        return [
            ChunkHit(chunk=self.chunks[i], score=round(float(scores[i]), 4), retriever=self.name)
            for i in ranked[:top_k]
        ]


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
