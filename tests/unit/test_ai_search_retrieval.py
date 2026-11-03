"""AI Search and hybrid retrieval without network (fake SDK client)."""

from __future__ import annotations

from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

import pytest

from advisor.config import Settings
from advisor.models import Chunk, ChunkHit
from advisor.pipeline import build_retriever
from advisor.retrieval import (
    AISearchRetriever,
    BM25Retriever,
    HybridRetriever,
    RetrievalUnavailableError,
    Retriever,
)

DOC = "a" * 64
CHUNKS = [
    Chunk(
        chunk_id=f"{DOC[:12]}:1:{i}",
        document_id=DOC,
        page_start=1,
        page_end=1,
        section=s,
        text=t,
        part_numbers=["SYN-NIC-100"],
    )
    for i, (s, t) in enumerate(
        [
            ("Overview", "100GbE NIC with RDMA"),
            ("Offloads", "IPsec and TLS offload"),
            ("Power", "TDP 18W"),
        ]
    )
]
COLUMNS = [
    "chunk_id",
    "document_id",
    "page_start",
    "page_end",
    "section",
    "text",
    "part_numbers",
    "score",
]


class FakeIndexes:
    def __init__(self, rows: list[list[Any]] | None = None, error: Exception | None = None) -> None:
        self.rows, self.error, self.calls = rows or [], error, []

    def query_index(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        manifest = SimpleNamespace(columns=[SimpleNamespace(name=c) for c in COLUMNS])
        return SimpleNamespace(manifest=manifest, result=SimpleNamespace(data_array=self.rows))


def row(chunk: Chunk, score: float, parts: Any = None) -> list[Any]:
    return [chunk.chunk_id, chunk.document_id, chunk.page_start, chunk.page_end, chunk.section, chunk.text,
            parts if parts is not None else chunk.part_numbers, score]  # fmt: skip


def ai_search(indexes: FakeIndexes) -> AISearchRetriever:
    return AISearchRetriever(
        "ep", "cat.gold.idx", None, client=SimpleNamespace(vector_search_indexes=indexes)
    )


def test_ai_search_maps_rows_to_chunk_hits() -> None:
    indexes = FakeIndexes([row(CHUNKS[1], 0.91), row(CHUNKS[0], 0.75, parts='["SYN-NIC-100"]')])
    hits = ai_search(indexes).search("ipsec offload", top_k=2)
    assert [h.chunk.chunk_id for h in hits] == [CHUNKS[1].chunk_id, CHUNKS[0].chunk_id]
    assert hits[0].score == 0.91 and hits[0].retriever == "ai_search"
    assert hits[1].chunk.part_numbers == ["SYN-NIC-100"]  # JSON string arrays are decoded
    call = indexes.calls[0]
    assert call["index_name"] == "cat.gold.idx" and call["query_text"] == "ipsec offload"
    assert "text" in call["columns"] and call["num_results"] == 2


def test_ai_search_filters() -> None:
    indexes = FakeIndexes([row(CHUNKS[0], 0.9)])
    hits = ai_search(indexes).search(
        "nic", top_k=3, filters={"document_id": DOC, "part_number": "OTHER"}
    )
    assert hits == []  # part_number is filtered client-side
    assert indexes.calls[0]["filters_json"] == '{"document_id": "' + DOC + '"}'


def test_ai_search_errors_are_typed() -> None:
    with pytest.raises(RetrievalUnavailableError):
        ai_search(FakeIndexes(error=RuntimeError("index not ready"))).search("nic")


class Broken(Retriever):
    name = "broken"

    def search(
        self, query: str, *, top_k: int = 8, filters: Mapping[str, str] | None = None
    ) -> list[ChunkHit]:
        raise RetrievalUnavailableError("down")


def test_hybrid_rrf_rewards_agreement() -> None:
    semantic = ai_search(FakeIndexes([row(CHUNKS[1], 0.9), row(CHUNKS[2], 0.8)]))
    hybrid = HybridRetriever([BM25Retriever(CHUNKS), semantic])
    hits = hybrid.search("IPsec offload", top_k=3)
    assert hits[0].chunk.chunk_id == CHUNKS[1].chunk_id  # first in both rankings
    assert all(h.retriever == "hybrid" for h in hits) and hybrid.last_errors == []


def test_hybrid_degrades_to_the_retrievers_that_answer() -> None:
    hybrid = HybridRetriever([BM25Retriever(CHUNKS), Broken()])
    hits = hybrid.search("IPsec", top_k=2)
    assert hits and hits[0].chunk.chunk_id == CHUNKS[1].chunk_id
    assert hybrid.last_errors == ["down"]
    with pytest.raises(RetrievalUnavailableError):
        HybridRetriever([Broken()]).search("x")


@pytest.mark.parametrize(
    ("backend", "kind"),
    [("bm25", BM25Retriever), ("ai_search", AISearchRetriever), ("hybrid", HybridRetriever)],
)
def test_build_retriever_by_settings(backend: str, kind: type) -> None:
    settings = Settings.model_validate({"retrieval": {"backend": backend}})
    assert isinstance(build_retriever(settings, CHUNKS), kind)
