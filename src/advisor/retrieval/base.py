"""Retriever interface and backends: BM25 (local), AI Search (Databricks), hybrid RRF."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

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


class RetrievalUnavailableError(RuntimeError):
    """A remote retriever cannot answer (network, auth, index not ready); callers may degrade."""


AI_SEARCH_COLUMNS = [
    "chunk_id",
    "document_id",
    "page_start",
    "page_end",
    "section",
    "text",
    "part_numbers",
]


def _row_to_chunk(row: Mapping[str, Any]) -> Chunk:
    parts = row.get("part_numbers") or []
    if isinstance(parts, str):
        parts = json.loads(parts) if parts.startswith("[") else [parts]
    return Chunk(
        chunk_id=str(row["chunk_id"]),
        document_id=str(row["document_id"]),
        page_start=int(row["page_start"]),
        page_end=int(row["page_end"]),
        section=row.get("section") or None,
        text=str(row["text"]),
        part_numbers=[str(p) for p in parts],
    )


class AISearchRetriever(Retriever):
    """Databricks AI Search (Vector Search) over the Delta Sync index of gold.document_chunks.

    Embeddings are managed by Databricks (``databricks-gte-large-en``); nothing is downloaded.
    """

    name = "ai_search"

    def __init__(
        self, endpoint: str, index: str, profile: str | None, *, client: Any | None = None
    ) -> None:
        self.endpoint, self.index, self.profile = endpoint, index, profile
        self._client = client

    def _indexes(self) -> Any:
        if self._client is None:
            try:
                from databricks.sdk import WorkspaceClient

                self._client = WorkspaceClient(profile=self.profile)
            except Exception as exc:  # SDK config errors come in many types
                raise RetrievalUnavailableError(f"ai_search: {exc}") from exc
        return self._client.vector_search_indexes

    def search(
        self, query: str, *, top_k: int = 8, filters: Mapping[str, str] | None = None
    ) -> list[ChunkHit]:
        if top_k <= 0 or not query.strip():
            return []
        server_filters = {k: v for k, v in (filters or {}).items() if k == "document_id"}
        try:
            response = self._indexes().query_index(
                index_name=self.index,
                columns=AI_SEARCH_COLUMNS,
                query_text=query,
                num_results=top_k * 2 if filters else top_k,
                filters_json=json.dumps(server_filters) if server_filters else None,
            )
        except RetrievalUnavailableError:
            raise
        except Exception as exc:  # network / auth / index not ready
            raise RetrievalUnavailableError(f"ai_search: {exc}") from exc
        names = [c.name for c in (response.manifest.columns or [])] if response.manifest else []
        rows = (response.result.data_array or []) if response.result else []
        hits: list[ChunkHit] = []
        for values in rows:
            row = dict(zip(names, values, strict=False))
            chunk = _row_to_chunk(row)
            if not _matches(chunk, filters):
                continue
            hits.append(ChunkHit(chunk=chunk, score=round(float(row.get("score", 0.0)), 4),
                                 retriever=self.name))  # fmt: skip
        return hits[:top_k]


class HybridRetriever(Retriever):
    """Reciprocal Rank Fusion of several retrievers (BM25 + AI Search).

    A retriever that is unavailable is skipped (recorded in ``last_errors``), so the fusion degrades
    to the ones that answer instead of failing the request.
    """

    name = "hybrid"

    def __init__(self, retrievers: Sequence[Retriever], *, k: int = 60) -> None:
        if not retrievers:
            raise ValueError("HybridRetriever needs at least one retriever")
        self.retrievers = list(retrievers)
        self.k = k
        self.last_errors: list[str] = []
        self.last_sources: dict[str, int] = {}  # retriever name -> final hits it contributed

    def search(
        self, query: str, *, top_k: int = 8, filters: Mapping[str, str] | None = None
    ) -> list[ChunkHit]:
        self.last_errors = []
        fused: dict[str, float] = {}
        chunks: dict[str, Chunk] = {}
        found_by: dict[str, set[str]] = {}
        answered = 0
        for retriever in self.retrievers:
            try:
                hits = retriever.search(query, top_k=max(top_k * 2, 10), filters=filters)
            except RetrievalUnavailableError as exc:
                self.last_errors.append(str(exc))
                continue
            answered += 1
            for rank, hit in enumerate(hits, start=1):
                cid = hit.chunk.chunk_id
                fused[cid] = fused.get(cid, 0.0) + 1.0 / (self.k + rank)
                chunks.setdefault(cid, hit.chunk)
                found_by.setdefault(cid, set()).add(retriever.name)
        if not answered:
            raise RetrievalUnavailableError("; ".join(self.last_errors))
        ranked = sorted(fused, key=lambda cid: (-fused[cid], cid))[:top_k]
        self.last_sources = {
            r.name: sum(r.name in found_by[cid] for cid in ranked) for r in self.retrievers
        }
        return [
            ChunkHit(chunk=chunks[c], score=round(fused[c], 6), retriever=self.name) for c in ranked
        ]
