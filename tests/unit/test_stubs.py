"""Expected behaviour of every module contract.

Each test is ``xfail(strict=True, raises=NotImplementedError)`` while the stub is pending.
When a contract is implemented the test XPASSes, strict mode fails the run, and whoever implemented it
removes the marker. Any other exception (wrong behaviour) fails immediately.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import networkx as nx
import pytest

from advisor import chunking, enrichment, extraction, ingestion, kg, parsing
from advisor.agent import AdvisorAgent
from advisor.commercial import CommercialEngine
from advisor.compatibility import derive_requirements, evaluate
from advisor.llm import TemplateClient
from advisor.models import (
    CommercialInformation,
    CommercialStatus,
    CompatibilityLevel,
    CustomerQuery,
    DocumentRecord,
    DocumentType,
    Operator,
    ParsedDocument,
    ParsedPage,
    ParsedQuery,
    Product,
    RequirementOrigin,
    TechnicalRequirement,
)
from advisor.recommendation import rank
from advisor.repository import LocalParquetRepository
from advisor.retrieval import BM25Retriever

ROOT = Path(__file__).resolve().parents[2]
PDF_DIR = ROOT / "data" / "raw"
CATALOG = PDF_DIR / "Catalogo_Comercial_Precios_Inventario_2026.pdf"


def pending(backlog: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(raises=NotImplementedError, strict=True, reason=f"{backlog} pending")


pytestmark = pytest.mark.stub


def record(path: Path, doc_type: DocumentType) -> DocumentRecord:
    data = path.read_bytes()
    return DocumentRecord(
        document_id=hashlib.sha256(data).hexdigest(),
        path=str(path),
        filename=path.name,
        doc_type=doc_type,
        size_bytes=len(data),
    )


SYNTH_DOC = ParsedDocument(
    document_id="0" * 64,
    title="SYN-NIC-100 - DATASHEET",
    pages=[ParsedPage(page_number=1, text="SYN-NIC-100. Port speed: 2x 100GbE. RDMA: RoCE v2.")],
    parser="synthetic",
)


def bare(p: Product) -> Product:
    return p.model_copy(update={"commercial": None})


# ---------- Datos ----------
def test_discover_documents_finds_33_pdfs() -> None:
    docs = ingestion.discover_documents(PDF_DIR)
    assert len(docs) == 33
    assert sum(d.doc_type is DocumentType.CATALOG for d in docs) == 1


def test_parse_catalog_returns_32_rows_with_expected_statuses() -> None:
    rows = parsing.parse_catalog(record(CATALOG, DocumentType.CATALOG))
    assert len(rows) == 32
    counts = {s: sum(r.status is s for r in rows) for s in CommercialStatus}
    assert counts == {
        CommercialStatus.ACTIVE: 21,
        CommercialStatus.DISCONTINUED: 6,
        CommercialStatus.EOL: 2,
        CommercialStatus.NRND: 3,
    }
    assert all(r.price_usd is None for r in rows if r.status is not CommercialStatus.ACTIVE)


def test_parse_document_reads_datasheet() -> None:
    doc = parsing.parse_document(
        record(PDF_DIR / "Intel_E810_100GbE_NIC.pdf", DocumentType.DATASHEET)
    )
    assert doc.pages and "E810" in doc.pages[0].text


@pending("B-06")
def test_extract_product_attaches_evidence() -> None:
    registry = extraction.load_spec_registry(ROOT / "config" / "spec_registry.yaml")
    product = extraction.extract_product(SYNTH_DOC, registry)
    assert product.commercial is None
    assert all(s.evidence for s in product.specifications if s.value is not None)


@pending("B-07")
def test_join_catalog_matches_all(
    products: dict[str, Product], commercial_rows: list[CommercialInformation]
) -> None:
    joined, report = enrichment.join_catalog([bare(p) for p in products.values()], commercial_rows)
    assert len(report.matched) == 6 and not report.unmatched_catalog
    assert all(p.commercial is not None for p in joined)


@pending("B-08")
def test_chunk_ids_are_stable() -> None:
    first = chunking.chunk_document(SYNTH_DOC)
    assert first and [c.chunk_id for c in first] == [
        c.chunk_id for c in chunking.chunk_document(SYNTH_DOC)
    ]


@pending("B-09")
def test_graph_roundtrip(products: dict[str, Product], tmp_path: Path) -> None:
    g = kg.build_graph(list(products.values()), [])
    kg.save(g, tmp_path / "graph.json")
    loaded = kg.load(tmp_path / "graph.json")
    assert set(loaded.nodes) == set(g.nodes) and loaded.number_of_edges() == g.number_of_edges()


# ---------- Inteligencia ----------
@pending("B-11")
def test_resolve_part_fuzzy(mock_graph: nx.MultiDiGraph) -> None:
    assert kg.resolve_part(mock_graph, "syn nic 100")[0].part_number == "SYN-NIC-100"


@pending("B-12")
def test_candidate_neighbors(mock_graph: nx.MultiDiGraph) -> None:
    parts = {c.part_number for c in kg.candidate_neighbors(mock_graph, "SYN-NIC-100")}
    assert "SYN-NIC-200" in parts and "SYN-NIC-100" not in parts


@pending("B-13")
def test_bm25_respects_top_k() -> None:
    assert len(BM25Retriever([]).search("100GbE RDMA", top_k=3)) <= 3


@pending("B-14")
def test_commercial_engine(commercial_rows: list[CommercialInformation]) -> None:
    engine = CommercialEngine(commercial_rows)
    assert engine.get("SYN-NIC-200").status is CommercialStatus.ACTIVE
    assert engine.availability("SYN-GPU-100").price_usd is None  # NRND: no price


@pending("B-15")
def test_category_mismatch_is_incompatible(products: dict[str, Product]) -> None:
    result = evaluate(products["SYN-NIC-100"], products["SYN-MCU-100"], [])
    assert result.level is CompatibilityLevel.INCOMPATIBLE


@pending("B-15")
def test_missing_required_spec_is_never_compatible(products: dict[str, Product]) -> None:
    req = TechnicalRequirement(
        key="rdma", operator=Operator.HAS, value="RoCE v2", origin=RequirementOrigin.QUERY
    )
    result = evaluate(
        products["SYN-GPU-100"], products["SYN-GPU-200"], [req]
    )  # GPUs have no rdma spec
    assert result.level in (CompatibilityLevel.UNKNOWN, CompatibilityLevel.INCOMPATIBLE)


@pending("B-16")
def test_derive_requirements_keeps_query_requirements(products: dict[str, Product]) -> None:
    req = TechnicalRequirement(
        key="port_speed", operator=Operator.GTE, value=100, origin=RequirementOrigin.QUERY
    )
    query = ParsedQuery(original_text="x", part_numbers=["SYN-NIC-100"], requirements=[req])
    assert req in derive_requirements(products["SYN-NIC-100"], query)


@pending("B-17")
def test_rank_only_recommends_active(products: dict[str, Product]) -> None:
    results = [
        evaluate(products["SYN-NIC-100"], products["SYN-NIC-200"], []),
        evaluate(products["SYN-NIC-100"], products["SYN-MCU-100"], []),
    ]
    out = rank(results, products)
    assert [r.product.part_number for r in out.recommendations] == ["SYN-NIC-200"]


@pending("B-18")
def test_template_llm_parses_query() -> None:
    parsed = TemplateClient().complete_json("Reemplazo para SYN-NIC-100", ParsedQuery)
    assert "SYN-NIC-100" in parsed.part_numbers


@pending("B-19")
def test_agent_recommends_only_active(
    products: dict[str, Product],
    commercial_rows: list[CommercialInformation],
    mock_graph: nx.MultiDiGraph,
) -> None:
    agent = AdvisorAgent(
        graph=mock_graph,
        products=list(products.values()),
        commercial=CommercialEngine(commercial_rows),
        retriever=BM25Retriever([]),
        llm_chain=[TemplateClient()],
    )
    resp = agent.answer(CustomerQuery(text="Necesito reemplazar SYN-NIC-100 con RDMA"))
    assert resp.recommendations and resp.recommendations[0].product.part_number == "SYN-NIC-200"


# ---------- Producto ----------
@pending("B-20")
def test_local_repository_roundtrip(products: dict[str, Product], tmp_path: Path) -> None:
    repo = LocalParquetRepository(tmp_path)
    repo.save_products(list(products.values()))
    assert {p.part_number for p in repo.load_products()} == set(products)
