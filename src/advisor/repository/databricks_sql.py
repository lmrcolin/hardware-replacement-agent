"""Delta tables in Unity Catalog and the Databricks artifact repository (SQL warehouse).

One definition per table (:data:`TABLES`) is shared by the notebooks (which write with Spark) and
by :class:`DatabricksSQLRepository` (which reads/writes through the Statement Execution API), so
both sides always agree on columns. Tables keep the flat columns of ``docs/TODO.md`` plus, where
the repository must rebuild a contract, ``payload`` (the contract as JSON: lossless).

Writes are idempotent everywhere: rows → Parquet in the volume ``{catalog}.gold.artifacts``
(under ``_delta/``) → ``CREATE OR REPLACE TABLE ... AS SELECT * FROM read_files(...)``.
"""

from __future__ import annotations

import io
import json
import re
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, TypeVar, cast

import networkx as nx
import pyarrow as pa
import pyarrow.parquet as pq
from databricks.sdk.service.sql import ExecuteStatementRequestOnWaitTimeout
from pydantic import BaseModel

from advisor.models import (
    Chunk,
    CommercialInformation,
    CompatibilityResult,
    JoinReport,
    ParsedDocument,
    Product,
)
from advisor.repository.base import ArtifactRepository

M = TypeVar("M", bound=BaseModel)

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DONE = {"SUCCEEDED"}
_FAILED = {"FAILED", "CANCELED", "CLOSED"}
ARTIFACTS_VOLUME = "artifacts"  # {catalog}.gold.artifacts
STAGING_DIR = "_delta"  # Parquet staging for CTAS (K6 exports live at the volume root)

AUDIT = [("is_synthetic", pa.bool_()), ("_ingested_at", pa.timestamp("us", tz="UTC"))]


def _identifier(value: str, what: str) -> str:
    if not _IDENTIFIER.match(value):
        raise ValueError(f"{what} inválido para Unity Catalog: {value!r}")
    return value


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


# ---------------------------------------------------------------------------- table definitions


@dataclass(frozen=True)
class DeltaTable:
    layer: str  # bronze | silver | gold
    name: str
    schema: pa.Schema
    order_by: str
    comment: str

    @property
    def key(self) -> str:
        return f"{self.layer}.{self.name}"

    def fqn(self, catalog: str) -> str:
        return f"`{_identifier(catalog, 'catálogo')}`.`{self.layer}`.`{self.name}`"

    def staging_path(self, catalog: str) -> str:
        volume = f"/Volumes/{catalog}/gold/{ARTIFACTS_VOLUME}"
        return f"{volume}/{STAGING_DIR}/{self.layer}_{self.name}.parquet"

    def ctas(self, catalog: str) -> str:
        comment = self.comment.replace("'", "''")
        return (
            f"CREATE OR REPLACE TABLE {self.fqn(catalog)} COMMENT '{comment}' AS "
            f"SELECT * FROM read_files('{self.staging_path(catalog)}', format => 'parquet') "
            f"ORDER BY {self.order_by}"
        )

    def insert_overwrite(self, catalog: str) -> str:
        """Replace the rows but keep the Delta table id: ``CREATE OR REPLACE`` assigns a new id,
        which breaks streaming readers such as the AI Search Delta Sync index."""
        return (
            f"INSERT OVERWRITE {self.fqn(catalog)} "
            f"SELECT * FROM read_files('{self.staging_path(catalog)}', format => 'parquet') "
            f"ORDER BY {self.order_by}"
        )


def _table(
    layer: str, name: str, cols: list[tuple[str, pa.DataType]], order: str, doc: str
) -> DeltaTable:
    return DeltaTable(layer, name, pa.schema([*cols, *AUDIT]), order, doc)


STR, DATE, INT, FLOAT = pa.string(), pa.date32(), pa.int64(), pa.float64()
MONEY = pa.decimal128(14, 2)

TABLES: dict[str, DeltaTable] = {
    t.key: t
    for t in [
        _table(
            "silver", "commercial",
            [("part_number", STR), ("description", STR), ("manufacturer", STR), ("category", STR),
             ("status", STR), ("discontinued_on", DATE), ("last_buy_on", DATE),
             ("price_usd", MONEY),
             ("stock_units", INT), ("inventory_value_usd", MONEY)],
            "part_number",
            "Catálogo comercial (verdad de estado, precio y stock); 1 fila por part number. "
            "Leído con parse_catalog (capa de texto, ADR-012).",
        ),
        _table(
            "silver", "products",
            [("part_number", STR), ("manufacturer", STR), ("category", STR), ("description", STR),
             ("document_ids", pa.list_(STR))],
            "part_number",
            "Producto por datasheet cruzado con el catálogo (join_catalog).",
        ),
        _table(
            "silver", "product_specifications",
            [("part_number", STR), ("key", STR), ("value", STR), ("unit", STR), ("raw_value", STR),
             ("evidence", STR)],
            "part_number, key",
            "Specs normalizadas por producto (spec_registry.yaml); value y evidence en JSON.",
        ),
        _table(
            "gold", "products",
            [("part_number", STR), ("manufacturer", STR), ("category", STR), ("description", STR),
             ("status", STR), ("price_usd", MONEY), ("stock_units", INT), ("payload", STR)],
            "part_number",
            "Producto + comercial para el agente; payload = contrato Product en JSON.",
        ),
        _table(
            "gold", "document_chunks",
            [("chunk_id", STR), ("document_id", STR), ("page_start", INT), ("page_end", INT),
             ("section", STR), ("text", STR), ("part_numbers", pa.list_(STR)), ("payload", STR)],
            "chunk_id",
            "Chunks de datasheets por sección para retrieval (Change Data Feed para AI Search).",
        ),
        _table(
            "gold", "compat_matrix",
            [("original_part_number", STR), ("candidate_part_number", STR), ("level", STR),
             ("coverage", FLOAT), ("score", FLOAT), ("conditions", STR), ("missing", STR),
             ("rule_results", STR), ("payload", STR)],
            "original_part_number, candidate_part_number",
            "Cada pieza no ACTIVE contra su categoría (derive_requirements + evaluate).",
        ),
        _table(
            "gold", "kg_nodes",
            [("node_id", STR), ("node_type", STR), ("label", STR), ("properties", STR)],
            "node_id",
            "Nodos del grafo de conocimiento (advisor.kg.build_graph); properties en JSON.",
        ),
        _table(
            "gold", "kg_edges",
            [("source", STR), ("target", STR), ("edge_type", STR), ("weight", FLOAT),
             ("evidence", STR)],
            "source, target, edge_type",
            "Aristas del grafo de conocimiento; edge_type es también la clave de la arista.",
        ),
    ]
}  # fmt: skip


# ------------------------------------------------------------------------------- row builders


def commercial_rows(
    catalog: Iterable[CommercialInformation], *, is_synthetic: bool, ingested_at: datetime
) -> list[dict[str, Any]]:
    return [
        {
            **c.model_dump(mode="python", include=set(CommercialInformation.model_fields)),
            "category": str(c.category),
            "status": str(c.status),
            "inventory_value_usd": c.inventory_value_usd,
            "is_synthetic": is_synthetic,
            "_ingested_at": ingested_at,
        }
        for c in catalog
    ]


def silver_product_rows(
    products: Iterable[Product], *, ingested_at: datetime
) -> list[dict[str, Any]]:
    return [
        {
            "part_number": p.part_number,
            "manufacturer": p.manufacturer,
            "category": str(p.category),
            "description": p.description,
            "document_ids": list(p.document_ids),
            "is_synthetic": p.is_synthetic,
            "_ingested_at": ingested_at,
        }
        for p in products
    ]


def specification_rows(
    products: Iterable[Product], *, ingested_at: datetime
) -> list[dict[str, Any]]:
    return [
        {
            "part_number": p.part_number,
            "key": s.key,
            "value": _json(s.value),
            "unit": s.unit,
            "raw_value": s.raw_value,
            "evidence": _json([e.model_dump(mode="json") for e in s.evidence]),
            "is_synthetic": p.is_synthetic,
            "_ingested_at": ingested_at,
        }
        for p in products
        for s in p.specifications
    ]


def gold_product_rows(
    products: Iterable[Product], *, ingested_at: datetime
) -> list[dict[str, Any]]:
    return [
        {
            "part_number": p.part_number,
            "manufacturer": p.manufacturer,
            "category": str(p.category),
            "description": p.description,
            "status": str(p.commercial.status) if p.commercial else None,
            "price_usd": p.commercial.price_usd if p.commercial else None,
            "stock_units": p.commercial.stock_units if p.commercial else None,
            "payload": p.model_dump_json(),
            "is_synthetic": p.is_synthetic,
            "_ingested_at": ingested_at,
        }
        for p in products
    ]


def chunk_rows(
    chunks: Iterable[Chunk], *, is_synthetic: bool, ingested_at: datetime
) -> list[dict[str, Any]]:
    return [
        {
            **c.model_dump(mode="python"),
            "part_numbers": list(c.part_numbers),
            "payload": c.model_dump_json(),
            "is_synthetic": is_synthetic,
            "_ingested_at": ingested_at,
        }
        for c in chunks
    ]


def matrix_rows(
    results: Iterable[CompatibilityResult], *, is_synthetic: bool, ingested_at: datetime
) -> list[dict[str, Any]]:
    return [
        {
            "original_part_number": r.original_part_number,
            "candidate_part_number": r.candidate_part_number,
            "level": str(r.level),
            "coverage": r.coverage,
            "score": r.score,
            "conditions": _json(r.conditions),
            "missing": _json(r.missing),
            "rule_results": _json([x.model_dump(mode="json") for x in r.rule_results]),
            "payload": r.model_dump_json(),
            "is_synthetic": is_synthetic,
            "_ingested_at": ingested_at,
        }
        for r in results
    ]


def kg_node_rows(
    graph: nx.MultiDiGraph, *, is_synthetic: bool, ingested_at: datetime
) -> list[dict[str, Any]]:
    return [
        {
            "node_id": str(node),
            "node_type": attrs.get("node_type"),
            "label": attrs.get("label"),
            "properties": _json(attrs.get("properties", {})),
            "is_synthetic": is_synthetic,
            "_ingested_at": ingested_at,
        }
        for node, attrs in graph.nodes(data=True)
    ]


def kg_edge_rows(
    graph: nx.MultiDiGraph, *, is_synthetic: bool, ingested_at: datetime
) -> list[dict[str, Any]]:
    rows = []
    for source, target, key, attrs in graph.edges(keys=True, data=True):
        if attrs.get("edge_type", key) != key:
            raise ValueError(f"arista {source}->{target}: clave {key!r} ≠ edge_type")
        rows.append(
            {
                "source": str(source),
                "target": str(target),
                "edge_type": str(key),
                "weight": float(attrs.get("weight", 1.0)),
                "evidence": _json(attrs.get("evidence", [])),
                "is_synthetic": is_synthetic,
                "_ingested_at": ingested_at,
            }
        )
    return rows


def graph_from_rows(
    nodes: Iterable[Sequence[Any]], edges: Iterable[Sequence[Any]]
) -> nx.MultiDiGraph:
    """Inverse of kg_node_rows / kg_edge_rows (same attributes as advisor.kg.build_graph)."""
    graph = nx.MultiDiGraph()
    for node_id, node_type, label, properties in nodes:
        graph.add_node(node_id, node_type=node_type, label=label, properties=json.loads(properties))
    for source, target, edge_type, weight, evidence in edges:
        graph.add_edge(
            source,
            target,
            key=edge_type,
            edge_type=edge_type,
            weight=float(weight),
            evidence=json.loads(evidence),
        )
    return graph


def arrow_table(spec: DeltaTable, rows: list[dict[str, Any]]) -> pa.Table:
    """Rows → Arrow table with the exact schema, sorted, rejecting duplicate keys."""
    order = [c.strip() for c in spec.order_by.split(",")]

    def sort_key(r: dict[str, Any]) -> tuple[str, ...]:
        return tuple("" if r[c] is None else str(r[c]) for c in order)

    keys = [sort_key(r) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError(f"{spec.key}: claves duplicadas en {spec.order_by}")
    return pa.Table.from_pylist(sorted(rows, key=sort_key), schema=spec.schema)


def parquet_bytes(table: pa.Table) -> bytes:
    sink = io.BytesIO()
    pq.write_table(table, sink)
    return sink.getvalue()


def now_utc() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------- writing from a notebook (Spark)


def write_delta_with_spark(
    spark: Any,
    catalog: str,
    spec: DeltaTable,
    rows: list[dict[str, Any]],
    *,
    keep_table_id: bool = False,
) -> int:
    """Notebook path: stage Parquet on the volume (FUSE write) and CTAS. Returns the row count.

    ``keep_table_id`` overwrites an existing table in place (for tables read by a stream)."""
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{_identifier(catalog, 'catálogo')}`.`{spec.layer}`")
    spark.sql(f"CREATE VOLUME IF NOT EXISTS `{catalog}`.`gold`.`{ARTIFACTS_VOLUME}`")
    path = Path(spec.staging_path(catalog))
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(arrow_table(spec, rows), path)
    exists = spark.catalog.tableExists(f"{catalog}.{spec.layer}.{spec.name}")
    spark.sql(spec.insert_overwrite(catalog) if keep_table_id and exists else spec.ctas(catalog))
    count = spark.table(spec.fqn(catalog)).count()
    if count != len(rows):
        raise RuntimeError(f"{spec.key}: {count} filas escritas, se esperaban {len(rows)}")
    return int(count)


# ------------------------------------------------------------- ADR-012 safety cross-check (K3)


def part_numbers_misread(
    report: JoinReport,
    documents: Mapping[str, ParsedDocument],
    ai_parsed_text: Mapping[str, str],
) -> list[str]:
    """Catalog part numbers that the PDF text layer contains but ``ai_parse_document`` lost.

    ``documents`` maps document_id → text-layer ParsedDocument; ``ai_parsed_text`` maps
    document_id → the ``ai_parse_document`` output (as JSON text) from ``bronze.documents_parsed``.
    A part number absent from the text layer itself (matched by prefix, e.g. the A100) is skipped.
    """
    misread = []
    for part, doc_id in sorted(report.matched.items()):
        doc = documents.get(doc_id)
        if doc is None or not any(part in page.text for page in doc.pages):
            continue
        if part not in ai_parsed_text.get(doc_id, ""):
            misread.append(part)
    return misread


def assert_join_is_safe(report: JoinReport, misread: Sequence[str]) -> None:
    problems = {
        "unmatched_catalog": report.unmatched_catalog,
        "status_conflicts": report.status_conflicts,
        "misread_by_ai_parse_document": list(misread),
    }
    if any(problems.values()):
        raise ValueError(f"cruce catálogo/datasheets inseguro (ADR-012): {problems}")


# ------------------------------------------------------------------ repository (SQL warehouse)


class WorkspaceClientLike(Protocol):
    """Subset of ``databricks.sdk.WorkspaceClient`` used here (lets tests inject a fake)."""

    statement_execution: Any
    files: Any


class DatabricksSQLError(RuntimeError):
    """A statement did not succeed on the warehouse."""


class DatabricksSQLRepository(ArtifactRepository):
    """Statement Execution API on the SQL warehouse (databricks-sdk, --profile). B-20.

    Reads and writes the ``gold`` tables of :data:`TABLES` in ``catalog``. ``schema`` is kept for
    the public signature and must be ``gold``.
    """

    def __init__(
        self,
        profile: str,
        warehouse_id: str,
        catalog: str,
        schema: str = "gold",
        *,
        client: WorkspaceClientLike | None = None,
        poll_seconds: float = 2.0,
        timeout_seconds: float = 600.0,
    ) -> None:
        if schema != "gold":
            raise ValueError(f"las tablas del repositorio viven en gold, no en {schema!r}")
        self.profile, self.warehouse_id = profile, warehouse_id
        self.catalog = _identifier(catalog, "catálogo")
        self.schema = schema
        self._client = client
        self._poll, self._timeout = poll_seconds, timeout_seconds

    # ------------------------------------------------------------------ infrastructure

    @property
    def client(self) -> WorkspaceClientLike:
        if self._client is None:
            from databricks.sdk import WorkspaceClient  # deferred: only needed when used

            self._client = cast(WorkspaceClientLike, WorkspaceClient(profile=self.profile or None))
        return self._client

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

    def write(self, spec: DeltaTable, rows: list[dict[str, Any]]) -> None:
        """Upload the staged Parquet through the Files API and rebuild the table (idempotent)."""
        self.execute(f"CREATE SCHEMA IF NOT EXISTS `{self.catalog}`.`{spec.layer}`")
        self.execute(f"CREATE VOLUME IF NOT EXISTS `{self.catalog}`.`gold`.`{ARTIFACTS_VOLUME}`")
        data = parquet_bytes(arrow_table(spec, rows))
        self.client.files.upload(spec.staging_path(self.catalog), io.BytesIO(data), overwrite=True)
        self.execute(spec.ctas(self.catalog))

    def _payloads(self, key: str, model: type[M]) -> list[M]:
        spec = TABLES[key]
        rows = self.execute(
            f"SELECT payload FROM {spec.fqn(self.catalog)} ORDER BY {spec.order_by}"
        )
        return [model.model_validate_json(row[0]) for row in rows]

    # ------------------------------------------------------------------ contract

    def load_products(self) -> list[Product]:
        return self._payloads("gold.products", Product)

    def load_chunks(self) -> list[Chunk]:
        return self._payloads("gold.document_chunks", Chunk)

    def load_compat_matrix(self) -> list[CompatibilityResult]:
        return self._payloads("gold.compat_matrix", CompatibilityResult)

    def load_graph(self) -> nx.MultiDiGraph:
        nodes, edges = TABLES["gold.kg_nodes"], TABLES["gold.kg_edges"]
        return graph_from_rows(
            self.execute(
                f"SELECT node_id, node_type, label, properties FROM {nodes.fqn(self.catalog)} "
                f"ORDER BY {nodes.order_by}"
            ),
            self.execute(
                "SELECT source, target, edge_type, weight, evidence "
                f"FROM {edges.fqn(self.catalog)} "
                f"ORDER BY {edges.order_by}"
            ),
        )

    def save_products(self, products: Sequence[Product]) -> None:
        self.write(TABLES["gold.products"], gold_product_rows(products, ingested_at=now_utc()))

    def save_chunks(self, chunks: Sequence[Chunk]) -> None:
        rows = chunk_rows(chunks, is_synthetic=False, ingested_at=now_utc())
        self.write(TABLES["gold.document_chunks"], rows)

    def save_compat_matrix(self, results: Sequence[CompatibilityResult]) -> None:
        rows = matrix_rows(results, is_synthetic=False, ingested_at=now_utc())
        self.write(TABLES["gold.compat_matrix"], rows)

    # ------------------------------------------------------------------ extra (not in contract)

    def save_graph(self, graph: nx.MultiDiGraph) -> None:
        """Persist the KG as ``gold.kg_nodes`` / ``gold.kg_edges`` (also written by notebook 04)."""
        at = now_utc()
        self.write(TABLES["gold.kg_nodes"], kg_node_rows(graph, is_synthetic=False, ingested_at=at))
        self.write(TABLES["gold.kg_edges"], kg_edge_rows(graph, is_synthetic=False, ingested_at=at))


def _state(resp: Any) -> str:
    state = getattr(getattr(resp, "status", None), "state", None)
    return str(getattr(state, "value", state))
