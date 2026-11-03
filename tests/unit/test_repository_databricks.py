"""Delta tables + DatabricksSQLRepository (B-20, K3-K8) against an in-memory fake. No network."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, BinaryIO

import networkx as nx
import pyarrow.parquet as pq
import pytest

from advisor.compatibility import evaluate
from advisor.models import (
    CommercialInformation,
    JoinReport,
    ParsedDocument,
    ParsedPage,
    Product,
)
from advisor.repository import ArtifactRepository, DatabricksSQLError, DatabricksSQLRepository
from advisor.repository.databricks_sql import (
    TABLES,
    DeltaTable,
    arrow_table,
    assert_join_is_safe,
    commercial_rows,
    graph_from_rows,
    kg_edge_rows,
    kg_node_rows,
    part_numbers_misread,
    specification_rows,
    write_delta_with_spark,
)

AT = datetime(2026, 11, 3, tzinfo=UTC)
DOC_A, DOC_B = "a" * 64, "b" * 64
CTAS = re.compile(
    r"CREATE OR REPLACE TABLE (?P<table>\S+) COMMENT '.*?' AS "
    r"SELECT \* FROM read_files\('(?P<path>[^']+)'"
)
SELECT = re.compile(r"SELECT (?P<cols>.+?) FROM (?P<table>\S+) ORDER BY")


def _resp(state: str, rows: list[list[Any]] | None = None, chunks: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        statement_id="stmt-1",
        status=SimpleNamespace(state=SimpleNamespace(value=state), error=None),
        result=SimpleNamespace(data_array=rows),
        manifest=SimpleNamespace(total_chunk_count=chunks),
    )


@dataclass
class FakeWarehouse:
    """Understands the handful of statements the repository emits."""

    files: dict[str, bytes] = field(default_factory=dict)
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    statements: list[str] = field(default_factory=list)
    pending: list[list[Any]] = field(default_factory=list)
    fail_with: str | None = None

    def upload(self, path: str, contents: BinaryIO, *, overwrite: bool = False) -> None:
        assert overwrite
        self.files[path] = contents.read()

    def execute_statement(self, statement: str, warehouse_id: str, **_: Any) -> SimpleNamespace:
        assert warehouse_id == "wh-123"
        self.statements.append(statement)
        if self.fail_with:
            resp = _resp("FAILED")
            resp.status.error = SimpleNamespace(message=self.fail_with)
            return resp
        if m := CTAS.search(statement):
            self.tables[m["table"]] = pq.read_table(io.BytesIO(self.files[m["path"]])).to_pylist()
            return _resp("SUCCEEDED")
        if m := SELECT.search(statement):
            cols = [c.strip() for c in m["cols"].split(",")]
            rows = [[r[c] for c in cols] for r in self.tables[m["table"]]]
            half = len(rows) // 2  # split results in two chunks
            self.pending = rows[half:]
            return _resp("SUCCEEDED", rows[:half], chunks=2)
        return _resp("SUCCEEDED")

    def get_statement(self, statement_id: str) -> SimpleNamespace:
        return _resp("SUCCEEDED")

    def get_statement_result_chunk_n(self, statement_id: str, index: int) -> SimpleNamespace:
        assert index == 1
        return SimpleNamespace(data_array=self.pending)


def repo_with(fake: FakeWarehouse) -> DatabricksSQLRepository:
    client = SimpleNamespace(statement_execution=fake, files=fake)
    return DatabricksSQLRepository("emerson", "wh-123", "emerson_hw", "gold", client=client)


# ------------------------------------------------------------------------------ repository


def test_is_an_artifact_repository() -> None:
    assert isinstance(repo_with(FakeWarehouse()), ArtifactRepository)


def test_products_roundtrip_through_volume_and_ctas(products: dict[str, Product]) -> None:
    fake = FakeWarehouse()
    repo = repo_with(fake)
    repo.save_products(list(products.values()))
    assert set(fake.files) == {"/Volumes/emerson_hw/gold/artifacts/_delta/gold_products.parquet"}
    assert any(
        "CREATE VOLUME IF NOT EXISTS `emerson_hw`.`gold`.`artifacts`" in s for s in fake.statements
    )
    assert repo.load_products() == sorted(products.values(), key=lambda p: p.part_number)
    row = fake.tables["`emerson_hw`.`gold`.`products`"][0]
    assert {"status", "price_usd", "stock_units", "payload", "is_synthetic", "_ingested_at"} <= set(
        row
    )


def test_matrix_and_graph_roundtrip(
    products: dict[str, Product], mock_graph: nx.MultiDiGraph
) -> None:
    fake = FakeWarehouse()
    repo = repo_with(fake)
    original = products["SYN-NIC-100"]
    results = [evaluate(original, c, []) for c in products.values() if c is not original]
    repo.save_compat_matrix(results)
    assert repo.load_compat_matrix() == sorted(results, key=lambda r: r.candidate_part_number)

    repo.save_graph(mock_graph)
    graph = repo.load_graph()
    assert set(graph.nodes) == set(mock_graph.nodes)
    assert set(graph.edges(keys=True)) == set(mock_graph.edges(keys=True))


def test_only_gold_schema_is_accepted() -> None:
    with pytest.raises(ValueError, match="gold"):
        DatabricksSQLRepository("p", "wh", "emerson_hw", "silver")


def test_failed_statement_raises_with_message() -> None:
    fake = FakeWarehouse(fail_with="PERMISSION_DENIED: no CREATE VOLUME")
    with pytest.raises(DatabricksSQLError, match="PERMISSION_DENIED"):
        repo_with(fake).load_products()


def test_running_statement_is_polled_until_timeout() -> None:
    api = SimpleNamespace(
        execute_statement=lambda **_: _resp("RUNNING"),
        get_statement=lambda _id: _resp("RUNNING"),
    )
    client = SimpleNamespace(statement_execution=api, files=None)
    repo = DatabricksSQLRepository(
        "p", "wh", "emerson_hw", "gold", client=client, poll_seconds=0.0, timeout_seconds=0.0
    )
    with pytest.raises(DatabricksSQLError, match="timeout"):
        repo.execute("SELECT 1")


@pytest.mark.parametrize("catalog", ["emerson-hw", "emerson_hw; DROP"])
def test_identifiers_are_validated(catalog: str) -> None:
    with pytest.raises(ValueError, match="inválido"):
        DatabricksSQLRepository("p", "wh", catalog, "gold")


# ------------------------------------------------------------------------ tables and rows


def test_every_table_has_audit_columns_and_comment() -> None:
    for spec in TABLES.values():
        assert {"is_synthetic", "_ingested_at"} <= set(spec.schema.names), spec.key
        assert (
            spec.comment
            and "'" not in spec.ctas("emerson_hw").split("COMMENT '")[1].split("' AS")[0]
        )


def test_commercial_rows_keep_catalog_values(
    commercial_rows_fixture: list[CommercialInformation],
) -> None:
    table = arrow_table(
        TABLES["silver.commercial"],
        commercial_rows(commercial_rows_fixture, is_synthetic=True, ingested_at=AT),
    )
    rows = {r["part_number"]: r for r in table.to_pylist()}
    for c in commercial_rows_fixture:
        assert rows[c.part_number]["status"] == c.status
        assert rows[c.part_number]["price_usd"] == c.price_usd
        assert rows[c.part_number]["inventory_value_usd"] == c.inventory_value_usd


def test_specification_rows_are_unique_per_part_and_key(products: dict[str, Product]) -> None:
    rows = specification_rows(products.values(), ingested_at=AT)
    table = arrow_table(TABLES["silver.product_specifications"], rows)
    assert table.num_rows == sum(len(p.specifications) for p in products.values())


def test_duplicate_keys_are_rejected(products: dict[str, Product]) -> None:
    rows = specification_rows([products["SYN-NIC-100"]] * 2, ingested_at=AT)
    with pytest.raises(ValueError, match="duplicadas"):
        arrow_table(TABLES["silver.product_specifications"], rows)


def test_kg_rows_rebuild_the_same_graph(mock_graph: nx.MultiDiGraph) -> None:
    nodes = kg_node_rows(mock_graph, is_synthetic=True, ingested_at=AT)
    edges = kg_edge_rows(mock_graph, is_synthetic=True, ingested_at=AT)
    graph = graph_from_rows(
        [[r["node_id"], r["node_type"], r["label"], r["properties"]] for r in nodes],
        [[r["source"], r["target"], r["edge_type"], r["weight"], r["evidence"]] for r in edges],
    )
    assert dict(graph.nodes(data=True)) == dict(mock_graph.nodes(data=True))
    assert sorted(graph.edges(keys=True, data=True)) == sorted(
        mock_graph.edges(keys=True, data=True)
    )


# ---------------------------------------------------------------- ADR-012 safety cross-check


def _doc(doc_id: str, text: str) -> ParsedDocument:
    return ParsedDocument(
        document_id=doc_id, pages=[ParsedPage(page_number=1, text=text)], parser="t"
    )


def test_misread_part_numbers_are_detected() -> None:
    report = JoinReport(matched={"H9HCNNNCPMML": DOC_A, "A100-SXM4-80GB": DOC_B})
    docs = {DOC_A: _doc(DOC_A, "Part Number: H9HCNNNCPMML"), DOC_B: _doc(DOC_B, "NVIDIA A100 80GB")}
    ai = {DOC_A: '{"text": "Part Number: H9HCNNCPMML"}', DOC_B: '{"text": "NVIDIA A100 80GB"}'}
    # A100 matched by prefix (absent from the text layer) is not a misread.
    assert part_numbers_misread(report, docs, ai) == ["H9HCNNNCPMML"]
    with pytest.raises(ValueError, match="misread_by_ai_parse_document"):
        assert_join_is_safe(report, ["H9HCNNNCPMML"])


def test_clean_join_passes() -> None:
    report = JoinReport(matched={"X-1": DOC_A})
    docs = {DOC_A: _doc(DOC_A, "Part Number: X-1")}
    assert part_numbers_misread(report, docs, {DOC_A: "... X-1 ..."}) == []
    assert_join_is_safe(report, [])
    with pytest.raises(ValueError, match="status_conflicts"):
        assert_join_is_safe(JoinReport(status_conflicts=["X-1"]), [])


def test_money_is_decimal_in_arrow(commercial_rows_fixture: list[CommercialInformation]) -> None:
    table = arrow_table(
        TABLES["silver.commercial"],
        commercial_rows(commercial_rows_fixture, is_synthetic=True, ingested_at=AT),
    )
    prices = [p for p in table.column("price_usd").to_pylist() if p is not None]
    assert prices and all(isinstance(p, Decimal) for p in prices)


@pytest.fixture
def commercial_rows_fixture(
    commercial_rows: list[CommercialInformation],
) -> list[CommercialInformation]:
    return commercial_rows


class _FakeSpark:
    """Records the SQL a notebook would run; the table exists or not depending on ``exists``."""

    def __init__(self, exists: bool, rows: int) -> None:
        self.sql_log: list[str] = []
        self.catalog = SimpleNamespace(tableExists=lambda name: exists)
        self._rows = rows

    def sql(self, statement: str) -> None:
        self.sql_log.append(statement)

    def table(self, name: str) -> SimpleNamespace:
        return SimpleNamespace(count=lambda: self._rows)


@pytest.mark.parametrize(
    ("exists", "verb"), [(True, "INSERT OVERWRITE"), (False, "CREATE OR REPLACE")]
)
def test_stream_source_table_keeps_its_id_when_rewritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exists: bool, verb: str
) -> None:
    spec = TABLES["gold.document_chunks"]
    monkeypatch.setattr(
        DeltaTable, "staging_path", lambda self, catalog: str(tmp_path / "c.parquet")
    )
    spark = _FakeSpark(exists, rows=0)
    write_delta_with_spark(spark, "emerson_hw", spec, [], keep_table_id=True)
    assert spark.sql_log[-1].startswith(verb)
