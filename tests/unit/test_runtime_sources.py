"""Visible provenance: data source, search status and per-query evidence attribution (no network)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from advisor import pipeline
from advisor.config import Settings
from advisor.models import Chunk
from advisor.pipeline import evidence_sources, retrieval_status, write_manifest
from advisor.retrieval import AISearchRetriever, BM25Retriever, HybridRetriever

DOC = "b" * 64
CHUNKS = [
    Chunk(
        chunk_id=f"{DOC[:12]}:1:{i}", document_id=DOC, page_start=1, page_end=1, section="S", text=t
    )
    for i, t in enumerate(["RDMA RoCE v2 NIC", "IPsec TLS offload", "humidity gas sensor"])
]
COLS = [
    "chunk_id",
    "document_id",
    "page_start",
    "page_end",
    "section",
    "text",
    "part_numbers",
    "score",
]


def ai(rows: list[list[Any]] | None = None, error: Exception | None = None) -> AISearchRetriever:
    class Indexes:
        def query_index(self, **_: Any) -> Any:
            if error:
                raise error
            manifest = SimpleNamespace(columns=[SimpleNamespace(name=c) for c in COLS])
            return SimpleNamespace(manifest=manifest, result=SimpleNamespace(data_array=rows or []))

    return AISearchRetriever(
        "emerson-vs", "cat.gold.idx", None, client=SimpleNamespace(vector_search_indexes=Indexes())
    )


def row(c: Chunk, score: float) -> list[Any]:
    return [c.chunk_id, c.document_id, 1, 1, c.section, c.text, [], score]


def test_status_bm25_and_live_or_down_ai_search() -> None:
    assert retrieval_status(BM25Retriever(CHUNKS)) == "BM25 local (sin red)"
    assert "AI Search ✓ en línea (cat.gold.idx)" in retrieval_status(ai([row(CHUNKS[0], 0.9)]))
    down = retrieval_status(HybridRetriever([BM25Retriever(CHUNKS), ai(error=RuntimeError("401"))]))
    assert down.startswith("híbrida RRF: BM25 ✓ + AI Search ✗")


def test_hybrid_reports_which_backend_found_each_hit() -> None:
    hybrid = HybridRetriever(
        [BM25Retriever(CHUNKS), ai([row(CHUNKS[2], 0.9), row(CHUNKS[1], 0.8)])]
    )
    hybrid.search("IPsec offload", top_k=2)
    assert hybrid.last_sources["ai_search"] >= 1 and set(hybrid.last_sources) == {
        "bm25",
        "ai_search",
    }
    assert evidence_sources(hybrid) is not None and evidence_sources(BM25Retriever(CHUNKS)) is None


def test_manifest_labels_where_artifacts_come_from(tmp_path: Path) -> None:
    write_manifest(tmp_path, "databricks", products=32)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["source"] == "databricks" and manifest["products"] == 32
    assert pipeline._source_label(tmp_path).startswith("artefactos exportados por el job run_all")


def test_databricks_backend_reads_live_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    monkeypatch.setattr(pipeline, "load_databricks", lambda s: called.append("databricks") or "ok")
    settings = Settings.model_validate({"repository_backend": "databricks_sql"})
    assert pipeline.load_or_build(settings) == "ok" and called == ["databricks"]


def test_warehouse_autodetect_requires_a_single_one() -> None:
    settings = Settings()
    one = SimpleNamespace(warehouses=SimpleNamespace(list=lambda: [SimpleNamespace(id="w1")]))
    assert pipeline._warehouse_id(settings, one) == "w1"  # type: ignore[arg-type]
    two = SimpleNamespace(
        warehouses=SimpleNamespace(list=lambda: [SimpleNamespace(id="a"), SimpleNamespace(id="b")])
    )
    with pytest.raises(ValueError, match="ADVISOR_DATABRICKS_WAREHOUSE_ID"):
        pipeline._warehouse_id(settings, two)  # type: ignore[arg-type]
