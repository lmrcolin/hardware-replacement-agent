"""Local artifact repository: Parquet tables + node-link graph JSON under ``artifacts/``.

Each Parquet row keeps a few flat, queryable columns plus ``payload``: the full contract as JSON, so
loading is lossless (nested specs, evidence, rule results) and validated by the Pydantic models.
Rows are sorted by key so the same input always produces the same files.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TypeVar

import networkx as nx
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel

from advisor.models import Chunk, CompatibilityResult, Product
from advisor.repository.base import ArtifactRepository

M = TypeVar("M", bound=BaseModel)

PRODUCTS_SCHEMA = pa.schema(
    [
        ("part_number", pa.string()),
        ("manufacturer", pa.string()),
        ("category", pa.string()),
        ("status", pa.string()),
        ("price_usd", pa.decimal128(12, 2)),
        ("stock_units", pa.int64()),
        ("is_synthetic", pa.bool_()),
        ("payload", pa.string()),
    ]
)
CHUNKS_SCHEMA = pa.schema(
    [
        ("chunk_id", pa.string()),
        ("document_id", pa.string()),
        ("page_start", pa.int32()),
        ("page_end", pa.int32()),
        ("section", pa.string()),
        ("part_numbers", pa.list_(pa.string())),
        ("payload", pa.string()),
    ]
)
MATRIX_SCHEMA = pa.schema(
    [
        ("original_part_number", pa.string()),
        ("candidate_part_number", pa.string()),
        ("level", pa.string()),
        ("coverage", pa.float64()),
        ("score", pa.float64()),
        ("payload", pa.string()),
    ]
)


def _product_row(p: Product) -> dict[str, Any]:
    c = p.commercial
    return {
        "part_number": p.part_number,
        "manufacturer": p.manufacturer,
        "category": str(p.category),
        "status": str(c.status) if c else None,
        "price_usd": c.price_usd if c else None,
        "stock_units": c.stock_units if c else None,
        "is_synthetic": p.is_synthetic,
        "payload": p.model_dump_json(),
    }


def _chunk_row(c: Chunk) -> dict[str, Any]:
    return {
        "chunk_id": c.chunk_id,
        "document_id": c.document_id,
        "page_start": c.page_start,
        "page_end": c.page_end,
        "section": c.section,
        "part_numbers": list(c.part_numbers),
        "payload": c.model_dump_json(),
    }


def _matrix_row(r: CompatibilityResult) -> dict[str, Any]:
    return {
        "original_part_number": r.original_part_number,
        "candidate_part_number": r.candidate_part_number,
        "level": str(r.level),
        "coverage": r.coverage,
        "score": r.score,
        "payload": r.model_dump_json(),
    }


class LocalParquetRepository(ArtifactRepository):
    """artifacts/{products,chunks,compat_matrix}.parquet + artifacts/graph.json (from kg.save)."""

    PRODUCTS = "products.parquet"
    CHUNKS = "chunks.parquet"
    MATRIX = "compat_matrix.parquet"
    GRAPH = "graph.json"

    def __init__(self, root: Path) -> None:
        self.root = root

    # ------------------------------------------------------------------ helpers

    def _path(self, name: str) -> Path:
        return self.root / name

    def _write(self, name: str, schema: pa.Schema, rows: list[dict[str, Any]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(rows, schema=schema), self._path(name))

    def _read(self, name: str, model: type[M]) -> list[M]:
        path = self._path(name)
        if not path.exists():
            raise FileNotFoundError(
                f"{path} no existe; genera los artefactos con `make pipeline-local`"
            )
        payloads = pq.read_table(path, columns=["payload"]).column("payload").to_pylist()
        return [model.model_validate_json(p) for p in payloads]

    def _save(
        self,
        name: str,
        schema: pa.Schema,
        items: Sequence[M],
        row: Callable[[M], dict[str, Any]],
        key: Callable[[M], tuple[str, ...]],
    ) -> None:
        keys = [key(i) for i in items]
        if len(keys) != len(set(keys)):
            raise ValueError(f"{name}: claves duplicadas")
        self._write(name, schema, [row(i) for i in sorted(items, key=key)])

    # ------------------------------------------------------------------ contract

    def load_products(self) -> list[Product]:
        return self._read(self.PRODUCTS, Product)

    def load_chunks(self) -> list[Chunk]:
        return self._read(self.CHUNKS, Chunk)

    def load_graph(self) -> nx.MultiDiGraph:
        path = self._path(self.GRAPH)
        if not path.exists():
            raise FileNotFoundError(
                f"{path} no existe; genera los artefactos con `make pipeline-local`"
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        graph = nx.node_link_graph(data, directed=True, multigraph=True, edges="edges")
        if not isinstance(graph, nx.MultiDiGraph):
            raise TypeError(f"{path} no contiene un MultiDiGraph")
        return graph

    def load_compat_matrix(self) -> list[CompatibilityResult]:
        return self._read(self.MATRIX, CompatibilityResult)

    def save_products(self, products: Sequence[Product]) -> None:
        self._save(
            self.PRODUCTS, PRODUCTS_SCHEMA, products, _product_row, lambda p: (p.part_number,)
        )

    def save_chunks(self, chunks: Sequence[Chunk]) -> None:
        self._save(self.CHUNKS, CHUNKS_SCHEMA, chunks, _chunk_row, lambda c: (c.chunk_id,))

    def save_compat_matrix(self, results: Sequence[CompatibilityResult]) -> None:
        self._save(
            self.MATRIX,
            MATRIX_SCHEMA,
            results,
            _matrix_row,
            lambda r: (r.original_part_number, r.candidate_part_number),
        )
