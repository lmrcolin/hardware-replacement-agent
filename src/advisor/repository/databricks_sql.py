"""Databricks artifact repository over the SQL warehouse (Statement Execution API, databricks-sdk).

Tables (Unity Catalog, ``{catalog}.{schema}``): ``products``, ``document_chunks``,
``compat_matrix``, ``kg_nodes`` and ``kg_edges``. They share the row layout of
:mod:`advisor.repository.local` (flat columns + ``payload`` JSON), so loading is lossless and
validated by the contracts.

Writes are idempotent: the Parquet file is uploaded to the volume ``{catalog}.{schema}.artifacts``
and the table is rebuilt with ``CREATE OR REPLACE TABLE ... AS SELECT * FROM read_files(...)``.
"""

from __future__ import annotations

import io
import json
import re
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol, TypeVar, cast

import networkx as nx
import pyarrow as pa
import pyarrow.parquet as pq
from databricks.sdk.service.sql import ExecuteStatementRequestOnWaitTimeout
from pydantic import BaseModel

from advisor.models import Chunk, CompatibilityResult, Product
from advisor.repository.base import ArtifactRepository
from advisor.repository.local import LocalParquetRepository

M = TypeVar("M", bound=BaseModel)

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DONE = {"SUCCEEDED"}
_FAILED = {"FAILED", "CANCELED", "CLOSED"}

NODES_SCHEMA = pa.schema([("node_id", pa.string()), ("payload", pa.string())])
EDGES_SCHEMA = pa.schema(
    [
        ("source", pa.string()),
        ("target", pa.string()),
        ("edge_key", pa.string()),
        ("payload", pa.string()),
    ]
)


class WorkspaceClientLike(Protocol):
    """Subset of ``databricks.sdk.WorkspaceClient`` used here (lets tests inject a fake)."""

    statement_execution: Any
    files: Any


class DatabricksSQLError(RuntimeError):
    """A statement did not succeed on the warehouse."""


def _identifier(value: str, what: str) -> str:
    if not _IDENTIFIER.match(value):
        raise ValueError(f"{what} inválido para Unity Catalog: {value!r}")
    return value


class DatabricksSQLRepository(ArtifactRepository):
    """Statement Execution API on the SQL warehouse (databricks-sdk, --profile). B-20."""

    PRODUCTS = "products"
    CHUNKS = "document_chunks"
    MATRIX = "compat_matrix"
    NODES = "kg_nodes"
    EDGES = "kg_edges"
    VOLUME = "artifacts"

    def __init__(
        self,
        profile: str,
        warehouse_id: str,
        catalog: str,
        schema: str,
        *,
        client: WorkspaceClientLike | None = None,
        poll_seconds: float = 2.0,
        timeout_seconds: float = 600.0,
    ) -> None:
        self.profile, self.warehouse_id = profile, warehouse_id
        self.catalog = _identifier(catalog, "catálogo")
        self.schema = _identifier(schema, "esquema")
        self._client = client
        self._poll, self._timeout = poll_seconds, timeout_seconds

    # ------------------------------------------------------------------ infrastructure

    @property
    def client(self) -> WorkspaceClientLike:
        if self._client is None:
            from databricks.sdk import WorkspaceClient  # deferred: only needed when used

            self._client = cast(WorkspaceClientLike, WorkspaceClient(profile=self.profile or None))
        return self._client

    def table(self, name: str) -> str:
        return f"`{self.catalog}`.`{self.schema}`.`{_identifier(name, 'tabla')}`"

    @property
    def volume_dir(self) -> str:
        return f"/Volumes/{self.catalog}/{self.schema}/{self.VOLUME}"

    def execute(self, statement: str) -> list[list[Any]]:
        """Run one statement and return every row (all result chunks), or raise."""
        api = self.client.statement_execution
        resp = api.execute_statement(
            statement=statement,
            warehouse_id=self.warehouse_id,
            wait_timeout="50s",
            on_wait_timeout=ExecuteStatementRequestOnWaitTimeout.CONTINUE,
        )
        deadline = time.monotonic() + self._timeout
        while _state(resp) not in _DONE:
            if _state(resp) in _FAILED:
                error = getattr(resp.status, "error", None)
                message = getattr(error, "message", None) or _state(resp)
                raise DatabricksSQLError(f"{message}\n-- {statement[:300]}")
            if time.monotonic() > deadline:
                raise DatabricksSQLError(f"timeout tras {self._timeout}s\n-- {statement[:300]}")
            time.sleep(self._poll)
            resp = api.get_statement(resp.statement_id)

        rows: list[list[Any]] = list(getattr(resp.result, "data_array", None) or [])
        chunks = getattr(getattr(resp, "manifest", None), "total_chunk_count", None) or 1
        for index in range(1, chunks):
            part = api.get_statement_result_chunk_n(resp.statement_id, index)
            rows.extend(part.data_array or [])
        return rows

    def _ensure_volume(self) -> None:
        self.execute(f"CREATE SCHEMA IF NOT EXISTS `{self.catalog}`.`{self.schema}`")
        self.execute(
            f"CREATE VOLUME IF NOT EXISTS `{self.catalog}`.`{self.schema}`.`{self.VOLUME}`"
        )

    def _replace_table(self, name: str, parquet: bytes, order_by: str) -> None:
        """Upload ``parquet`` to the volume and rebuild the table from it (idempotent)."""
        self._ensure_volume()
        path = f"{self.volume_dir}/{name}.parquet"
        self.client.files.upload(path, io.BytesIO(parquet), overwrite=True)
        self.execute(
            f"CREATE OR REPLACE TABLE {self.table(name)} AS "
            f"SELECT * FROM read_files('{path}', format => 'parquet') ORDER BY {order_by}"
        )

    def _load(self, name: str, order_by: str, model: type[M]) -> list[M]:
        rows = self.execute(f"SELECT payload FROM {self.table(name)} ORDER BY {order_by}")
        return [model.model_validate_json(row[0]) for row in rows]

    # ------------------------------------------------------------------ contract

    def load_products(self) -> list[Product]:
        return self._load(self.PRODUCTS, "part_number", Product)

    def load_chunks(self) -> list[Chunk]:
        return self._load(self.CHUNKS, "chunk_id", Chunk)

    def load_compat_matrix(self) -> list[CompatibilityResult]:
        return self._load(
            self.MATRIX, "original_part_number, candidate_part_number", CompatibilityResult
        )

    def load_graph(self) -> nx.MultiDiGraph:
        graph = nx.MultiDiGraph()
        for node_id, payload in self.execute(
            f"SELECT node_id, payload FROM {self.table(self.NODES)} ORDER BY node_id"
        ):
            graph.add_node(node_id, **json.loads(payload))
        for source, target, key, payload in self.execute(
            f"SELECT source, target, edge_key, payload FROM {self.table(self.EDGES)} "
            "ORDER BY source, target, edge_key"
        ):
            graph.add_edge(source, target, key=key, **json.loads(payload))
        return graph

    def save_products(self, products: Sequence[Product]) -> None:
        data = _local_parquet(lambda repo: repo.save_products(products), "products.parquet")
        self._replace_table(self.PRODUCTS, data, "part_number")

    def save_chunks(self, chunks: Sequence[Chunk]) -> None:
        data = _local_parquet(lambda repo: repo.save_chunks(chunks), "chunks.parquet")
        self._replace_table(self.CHUNKS, data, "chunk_id")

    def save_compat_matrix(self, results: Sequence[CompatibilityResult]) -> None:
        data = _local_parquet(
            lambda repo: repo.save_compat_matrix(results), "compat_matrix.parquet"
        )
        self._replace_table(self.MATRIX, data, "original_part_number, candidate_part_number")

    # ------------------------------------------------------------------ extra (not in contract)

    def save_graph(self, graph: nx.MultiDiGraph) -> None:
        """Persist the KG as ``kg_nodes`` / ``kg_edges`` (written by notebook 04 in Databricks)."""
        nodes = [
            {"node_id": str(n), "payload": json.dumps(attrs, sort_keys=True, ensure_ascii=False)}
            for n, attrs in sorted(graph.nodes(data=True), key=lambda item: str(item[0]))
        ]
        edges = [
            {
                "source": str(s),
                "target": str(t),
                "edge_key": str(k),
                "payload": json.dumps(attrs, sort_keys=True, ensure_ascii=False),
            }
            for s, t, k, attrs in sorted(
                graph.edges(keys=True, data=True), key=lambda e: (str(e[0]), str(e[1]), str(e[2]))
            )
        ]
        self._replace_table(self.NODES, _parquet(nodes, NODES_SCHEMA), "node_id")
        self._replace_table(self.EDGES, _parquet(edges, EDGES_SCHEMA), "source, target, edge_key")


def _state(resp: Any) -> str:
    state = getattr(getattr(resp, "status", None), "state", None)
    return str(getattr(state, "value", state))


def _parquet(rows: list[dict[str, Any]], schema: pa.Schema) -> bytes:
    sink = io.BytesIO()
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), sink)
    return sink.getvalue()


def _local_parquet(write: Any, filename: str) -> bytes:
    """Reuse LocalParquetRepository's layout (schemas, ordering, key checks) for the upload."""
    with tempfile.TemporaryDirectory() as tmp:
        write(LocalParquetRepository(Path(tmp)))
        return (Path(tmp) / filename).read_bytes()
