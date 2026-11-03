"""LocalParquetRepository (B-20): lossless roundtrips, determinism and clear errors. Synthetic data."""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pyarrow.parquet as pq
import pytest

from advisor.compatibility import evaluate
from advisor.models import Chunk, Product
from advisor.repository import ArtifactRepository, LocalParquetRepository

DOC = "9c9df4bc406668fb5d04d4b2f23669facea8d20a307b8a7e0a668c815bd4081f"


def chunks() -> list[Chunk]:
    return [
        Chunk(
            chunk_id=f"SYN-NIC-100:1:{i}",
            document_id=DOC,
            page_start=1,
            page_end=1,
            section="Network Specifications" if i else None,
            text=f"Synthetic chunk {i}",
            part_numbers=["SYN-NIC-100"] if i else [],
        )
        for i in (2, 0, 1)
    ]


def test_is_an_artifact_repository(tmp_path: Path) -> None:
    assert isinstance(LocalParquetRepository(tmp_path), ArtifactRepository)


def test_products_roundtrip_is_lossless_and_sorted(
    products: dict[str, Product], tmp_path: Path
) -> None:
    repo = LocalParquetRepository(tmp_path / "artifacts")  # created on save
    repo.save_products(list(reversed(products.values())))
    loaded = repo.load_products()
    assert loaded == sorted(products.values(), key=lambda p: p.part_number)
    table = pq.read_table(tmp_path / "artifacts" / "products.parquet")
    assert table.column("part_number").to_pylist() == sorted(products)


def test_products_flat_columns_follow_the_catalog(
    products: dict[str, Product], tmp_path: Path
) -> None:
    repo = LocalParquetRepository(tmp_path)
    repo.save_products(list(products.values()))
    rows = {r["part_number"]: r for r in pq.read_table(tmp_path / "products.parquet").to_pylist()}
    for part, product in products.items():
        commercial = product.commercial
        assert commercial is not None
        assert rows[part]["status"] == commercial.status
        assert rows[part]["price_usd"] == commercial.price_usd
        assert rows[part]["stock_units"] == commercial.stock_units


def test_chunks_roundtrip(tmp_path: Path) -> None:
    repo = LocalParquetRepository(tmp_path)
    repo.save_chunks(chunks())
    assert repo.load_chunks() == sorted(chunks(), key=lambda c: c.chunk_id)


def test_compat_matrix_roundtrip_keeps_rule_results(
    products: dict[str, Product], tmp_path: Path
) -> None:
    original = products["SYN-NIC-100"]
    results = [evaluate(original, c, []) for c in products.values() if c is not original]
    repo = LocalParquetRepository(tmp_path)
    repo.save_compat_matrix(results)
    loaded = repo.load_compat_matrix()
    assert {(r.candidate_part_number, r.level) for r in loaded} == {
        (r.candidate_part_number, r.level) for r in results
    }
    assert all(r.rule_results for r in loaded)
    assert loaded == sorted(results, key=lambda r: r.candidate_part_number)


def test_saving_twice_is_idempotent(products: dict[str, Product], tmp_path: Path) -> None:
    repo = LocalParquetRepository(tmp_path)
    repo.save_products(list(products.values()))
    first = pq.read_table(tmp_path / "products.parquet")
    repo.save_products(list(products.values()))
    assert pq.read_table(tmp_path / "products.parquet").equals(first)


def test_empty_sequences_roundtrip(tmp_path: Path) -> None:
    repo = LocalParquetRepository(tmp_path)
    repo.save_products([])
    repo.save_compat_matrix([])
    assert repo.load_products() == []
    assert repo.load_compat_matrix() == []


def test_duplicate_keys_are_rejected(products: dict[str, Product], tmp_path: Path) -> None:
    nic = products["SYN-NIC-100"]
    with pytest.raises(ValueError, match="duplicadas"):
        LocalParquetRepository(tmp_path).save_products([nic, nic])


def test_graph_is_read_from_kg_node_link_json(mock_graph: nx.MultiDiGraph, tmp_path: Path) -> None:
    data = nx.node_link_data(mock_graph, edges="edges")
    (tmp_path / "graph.json").write_text(json.dumps(data), encoding="utf-8")
    graph = LocalParquetRepository(tmp_path).load_graph()
    assert isinstance(graph, nx.MultiDiGraph)
    assert set(graph.nodes) == set(mock_graph.nodes)
    assert graph.number_of_edges() == mock_graph.number_of_edges()


@pytest.mark.parametrize(
    "method", ["load_products", "load_chunks", "load_compat_matrix", "load_graph"]
)
def test_missing_artifacts_explain_how_to_build_them(method: str, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="pipeline-local"):
        getattr(LocalParquetRepository(tmp_path), method)()
