"""Knowledge graph over the real catalog + datasheets."""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import pytest

from advisor.chunking import chunk_document
from advisor.enrichment import join_catalog
from advisor.extraction import extract_product, load_spec_registry, normalize
from advisor.ingestion import discover_documents
from advisor.kg import build_graph, candidate_neighbors, load, resolve_part, save
from advisor.models import DiscoveryPath, DocumentType, EdgeType, GraphEdge, GraphNode
from advisor.parsing import parse_catalog, parse_document

pytestmark = pytest.mark.data
ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_QUERY = (
    "Necesito una tarjeta de red 100 Gigabit Ethernet con soporte RDMA y offload de IPsec. "
    "Usábamos la Intel E810 pero ya no la encuentro"
)


@pytest.fixture(scope="module")
def built():  # type: ignore[no-untyped-def]
    registry = load_spec_registry(ROOT / "config" / "spec_registry.yaml")
    records = discover_documents(ROOT / "data" / "raw")
    catalog = parse_catalog(next(r for r in records if r.doc_type is DocumentType.CATALOG))
    docs = [parse_document(r) for r in records if r.doc_type is DocumentType.DATASHEET]
    products, _ = join_catalog([extract_product(d, registry) for d in docs], catalog)
    chunks = [c for d in docs for c in chunk_document(d)]
    text = {d.document_id: normalize(" ".join(p.text for p in d.pages)) for d in docs}
    return build_graph(products, chunks), chunks, text


@pytest.fixture(scope="module")
def graph(built) -> nx.MultiDiGraph:  # type: ignore[no-untyped-def]
    return built[0]


def migrations(graph: nx.MultiDiGraph) -> set[tuple[str, str]]:
    return {
        (graph.nodes[s]["label"], graph.nodes[t]["label"])
        for s, t, k in graph.edges(keys=True)
        if k == EdgeType.MIGRATES_TO.value
    }


def test_migrations_are_exactly_the_documented_ones(graph: nx.MultiDiGraph) -> None:
    assert migrations(graph) == {
        ("E810-CQDA2", "MCX75310AAS-NEAT"),
        ("E810-CQDA2", "BCM57508"),
        ("USB-2627", "USB-2633"),
        ("A100-SXM4-80GB", "H100-SXM5"),
    }


def test_migration_evidence_is_literal_and_traceable(built) -> None:  # type: ignore[no-untyped-def]
    graph, chunks, text = built
    chunk_ids = {c.chunk_id for c in chunks}
    for _, _, key, data in graph.edges(keys=True, data=True):
        if key == EdgeType.MIGRATES_TO.value:
            assert data["evidence"]
            for ev in data["evidence"]:
                assert ev["chunk_id"] in chunk_ids
                assert normalize(ev["quote"]) in text[ev["document_id"]]


def test_connectx7_datasheet_also_backs_e810_migration(graph: nx.MultiDiGraph) -> None:
    data = graph.edges["product:E810-CQDA2", "product:MCX75310AAS-NEAT", "MIGRATES_TO"]
    quotes = " ".join(ev["quote"] for ev in data["evidence"])
    assert (
        "consider NVIDIA ConnectX-7" in quotes
        and "replacement for discontinued Intel E810" in quotes
    )


def test_every_node_and_edge_matches_the_contracts(graph: nx.MultiDiGraph) -> None:
    for node_id, data in graph.nodes(data=True):
        GraphNode(node_id=node_id, **data)
    for s, t, data in graph.edges(data=True):
        GraphEdge(source=s, target=t, **data)


def test_roundtrip(graph: nx.MultiDiGraph, tmp_path: Path) -> None:
    save(graph, tmp_path / "graph.json")
    loaded = load(tmp_path / "graph.json")
    assert set(loaded.nodes) == set(graph.nodes)
    assert loaded.number_of_edges() == graph.number_of_edges()


def test_official_query_resolves_only_e810(graph: nx.MultiDiGraph) -> None:
    matches = resolve_part(graph, OFFICIAL_QUERY)
    assert [m.part_number for m in matches] == ["E810-CQDA2"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("reemplazo para el usb 2627", "USB-2627"),
        ("a100 80gb", "A100-SXM4-80GB"),
        ("E81O-CQDA2", "E810-CQDA2"),
    ],
)
def test_resolution_variants(graph: nx.MultiDiGraph, text: str, expected: str) -> None:
    assert resolve_part(graph, text)[0].part_number == expected


def test_vague_query_resolves_nothing(graph: nx.MultiDiGraph) -> None:
    assert resolve_part(graph, "busco un microcontrolador barato") == []


def test_e810_candidates_come_from_its_migration_notice(graph: nx.MultiDiGraph) -> None:
    candidates = candidate_neighbors(graph, "E810-CQDA2")
    assert {c.part_number for c in candidates} == {"MCX75310AAS-NEAT", "BCM57508"}
    assert all(DiscoveryPath.MIGRATES_TO in c.discovery_paths for c in candidates)


def test_candidates_never_include_the_product_or_other_categories(graph: nx.MultiDiGraph) -> None:
    for _, data in graph.nodes(data=True):
        if data["node_type"] != "Product":
            continue
        part, category = data["label"], data["properties"]["category"]
        for c in candidate_neighbors(graph, part, max_candidates=50):
            assert c.part_number != part
            assert graph.nodes[f"product:{c.part_number}"]["properties"]["category"] == category


def test_unknown_part_raises(graph: nx.MultiDiGraph) -> None:
    with pytest.raises(KeyError):
        candidate_neighbors(graph, "NOPE-123")


def test_model_names_from_catalog_descriptions_resolve(graph: nx.MultiDiGraph) -> None:
    assert resolve_part(graph, "el WD Ultrastar SN860 de 6.4TB")[0].part_number == "WUS4C6464DSP3X5"
    assert resolve_part(graph, "una AMD MI300X")[0].part_number == "MI300X"
