"""DatabricksSQLRepository (B-20) against an in-memory fake warehouse. No network."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, BinaryIO

import networkx as nx
import pyarrow.parquet as pq
import pytest

from advisor.compatibility import evaluate
from advisor.models import Product
from advisor.repository import ArtifactRepository, DatabricksSQLError, DatabricksSQLRepository

CTAS = re.compile(
    r"CREATE OR REPLACE TABLE (?P<table>\S+) AS SELECT \* FROM read_files\('(?P<path>[^']+)'"
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

    # files API
    def upload(self, path: str, contents: BinaryIO, *, overwrite: bool = False) -> None:
        assert overwrite
        self.files[path] = contents.read()

    # statement execution API
    def execute_statement(self, statement: str, warehouse_id: str, **_: Any) -> SimpleNamespace:
        assert warehouse_id == "wh-123"
        self.statements.append(statement)
        if self.fail_with:
            resp = _resp("FAILED")
            resp.status.error = SimpleNamespace(message=self.fail_with)
            return resp
        if m := CTAS.search(statement):
            table = pq.read_table(io.BytesIO(self.files[m["path"]]))
            self.tables[m["table"]] = table.to_pylist()
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


def test_is_an_artifact_repository() -> None:
    assert isinstance(repo_with(FakeWarehouse()), ArtifactRepository)


def test_products_roundtrip_through_volume_and_ctas(products: dict[str, Product]) -> None:
    fake = FakeWarehouse()
    repo = repo_with(fake)
    repo.save_products(list(products.values()))
    assert set(fake.files) == {"/Volumes/emerson_hw/gold/artifacts/products.parquet"}
    assert any(
        "CREATE VOLUME IF NOT EXISTS `emerson_hw`.`gold`.`artifacts`" in s for s in fake.statements
    )
    assert repo.load_products() == sorted(products.values(), key=lambda p: p.part_number)


def test_matrix_and_graph_roundtrip(
    products: dict[str, Product], mock_graph: nx.MultiDiGraph
) -> None:
    fake = FakeWarehouse()
    repo = repo_with(fake)
    original = products["SYN-NIC-100"]
    results = [evaluate(original, c, []) for c in products.values() if c is not original]
    repo.save_compat_matrix(results)
    assert {r.candidate_part_number for r in repo.load_compat_matrix()} == {
        r.candidate_part_number for r in results
    }

    repo.save_graph(mock_graph)
    graph = repo.load_graph()
    assert set(graph.nodes) == set(mock_graph.nodes)
    assert set(graph.edges(keys=True)) == {
        (s, t, str(k)) for s, t, k in mock_graph.edges(keys=True)
    }
    some = next(iter(mock_graph.nodes))
    assert graph.nodes[some] == mock_graph.nodes[some]


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


@pytest.mark.parametrize(
    ("catalog", "schema"), [("emerson-hw", "gold"), ("emerson_hw", "gold; DROP")]
)
def test_identifiers_are_validated(catalog: str, schema: str) -> None:
    with pytest.raises(ValueError, match="inválido"):
        DatabricksSQLRepository("p", "wh", catalog, schema)
