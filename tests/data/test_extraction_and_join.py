"""Extraction, catalog join and chunking over the real datasheets in data/raw."""

from __future__ import annotations

from pathlib import Path

import pytest

from advisor.chunking import chunk_document
from advisor.enrichment import join_catalog
from advisor.extraction import extract_product, load_spec_registry, normalize
from advisor.ingestion import discover_documents
from advisor.models import DocumentType, ParsedDocument, Product
from advisor.parsing import parse_catalog, parse_document

pytestmark = pytest.mark.data
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def docs() -> list[ParsedDocument]:
    records = discover_documents(ROOT / "data" / "raw")
    return [parse_document(r) for r in records if r.doc_type is DocumentType.DATASHEET]


@pytest.fixture(scope="module")
def joined(docs: list[ParsedDocument]):  # type: ignore[no-untyped-def]
    registry = load_spec_registry(ROOT / "config" / "spec_registry.yaml")
    records = discover_documents(ROOT / "data" / "raw")
    catalog = parse_catalog(next(r for r in records if r.doc_type is DocumentType.CATALOG))
    return join_catalog([extract_product(d, registry) for d in docs], catalog)


@pytest.fixture(scope="module")
def by_part(joined) -> dict[str, Product]:  # type: ignore[no-untyped-def]
    return {p.part_number: p for p in joined[0]}


def spec(product: Product, key: str):  # type: ignore[no-untyped-def]
    return next((s.value for s in product.specifications if s.key == key), None)


def test_every_quote_is_literal(docs: list[ParsedDocument], by_part: dict[str, Product]) -> None:
    text = {d.document_id: normalize(" ".join(p.text for p in d.pages)) for d in docs}
    for product in by_part.values():
        for s in product.specifications:
            assert s.evidence, (product.part_number, s.key)
            for ev in s.evidence:
                assert normalize(ev.quote) in text[ev.document_id], (product.part_number, s.key)


def test_all_32_joined_without_conflicts(joined) -> None:  # type: ignore[no-untyped-def]
    products, report = joined
    assert len(products) == 32 and len(report.matched) == 32
    assert not report.unmatched_catalog and not report.unmatched_documents
    assert not report.status_conflicts
    assert all(p.commercial is not None for p in products)


def test_catalog_identity_wins(by_part: dict[str, Product]) -> None:
    a100 = by_part["A100-SXM4-80GB"]
    assert a100.manufacturer == "NVIDIA" and a100.description == "NVIDIA A100 Tensor Core GPU 80GB"
    assert by_part["E810-CQDA2"].manufacturer == "Intel"


@pytest.mark.safety
def test_e810_does_not_inherit_successor_features(by_part: dict[str, Product]) -> None:
    """The discontinuation notice describes ConnectX-7's IPsec/TLS; the E810 itself has none."""
    e810 = by_part["E810-CQDA2"]
    assert spec(e810, "port_speed") == 100
    assert "RoCE v2" in spec(e810, "rdma")
    assert "IPsec" not in spec(e810, "offloads") and "TLS" not in spec(e810, "offloads")


def test_official_case_candidates_have_ipsec(by_part: dict[str, Product]) -> None:
    for part in ("MCX75310AAS-NEAT", "BCM57508"):
        assert "IPsec" in spec(by_part[part], "offloads")
        assert "RoCE v2" in spec(by_part[part], "rdma")


@pytest.mark.safety
def test_negated_features_are_not_extracted(by_part: dict[str, Product]) -> None:
    assert spec(by_part["RTX-4090"], "interconnect") is None  # "No NVLink support"
    assert "CAN" not in (spec(by_part["RP2040"], "interfaces") or [])  # "state machines can ..."


def test_known_values(by_part: dict[str, Product]) -> None:
    assert spec(by_part["USB-2627"], "analog_inputs") == 64
    assert spec(by_part["USB-2633"], "sample_rate") == 2_000_000
    assert spec(by_part["MT60B4G8HB-48B"], "capacity") == 4  # 32 Gb
    assert spec(by_part["WUS4C6464DSP3X5"], "form_factor") == "U.2"
    assert spec(by_part["MZ-V9P2T0"], "form_factor") == "M.2"
    assert spec(by_part["IR3555MTRPBF"], "input_voltage_max") == 12


def test_chunks_are_stable_and_scoped(docs: list[ParsedDocument]) -> None:
    for doc in docs:
        first, second = chunk_document(doc), chunk_document(doc)
        assert [c.chunk_id for c in first] == [c.chunk_id for c in second]
        assert all(c.document_id == doc.document_id for c in first)
        assert doc.title and doc.title in first[0].text
