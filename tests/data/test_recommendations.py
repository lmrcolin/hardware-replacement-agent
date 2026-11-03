"""End-to-end (deterministic, no LLM) recommendations over the real catalog and datasheets."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from advisor.compatibility import derive_requirements, evaluate
from advisor.enrichment import join_catalog
from advisor.extraction import extract_product, load_spec_registry
from advisor.ingestion import discover_documents
from advisor.models import (
    Category,
    CommercialStatus,
    CompatibilityLevel,
    DocumentType,
    Operator,
    ParsedQuery,
    Product,
    RequirementOrigin,
    RuleOutcome,
    Severity,
    TechnicalRequirement,
)
from advisor.parsing import parse_catalog, parse_document
from advisor.recommendation import RankedOutput, rank

pytestmark = pytest.mark.data
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def products() -> dict[str, Product]:
    registry = load_spec_registry(ROOT / "config" / "spec_registry.yaml")
    records = discover_documents(ROOT / "data" / "raw")
    catalog = parse_catalog(next(r for r in records if r.doc_type is DocumentType.CATALOG))
    docs = [parse_document(r) for r in records if r.doc_type is DocumentType.DATASHEET]
    joined, _ = join_catalog([extract_product(d, registry) for d in docs], catalog)
    return {p.part_number: p for p in joined}


def recommend(
    products: dict[str, Product], part: str, query: ParsedQuery | None = None
) -> RankedOutput:
    original = products[part]
    reqs = derive_requirements(original, query or ParsedQuery(original_text=part))
    results = [evaluate(original, c, reqs) for c in products.values() if c.part_number != part]
    return rank(results, products)


def official_query() -> ParsedQuery:
    def q(key: str, op: Operator, value: object, unit: str | None = None) -> TechnicalRequirement:
        return TechnicalRequirement(key=key, operator=op, value=value, unit=unit,  # type: ignore[arg-type]
                                    origin=RequirementOrigin.QUERY)  # fmt: skip

    return ParsedQuery(
        original_text="NIC 100GbE con RDMA e IPsec offload; usábamos la Intel E810",
        part_numbers=["E810-CQDA2"],
        category=Category.NETWORK,
        requirements=[
            q("port_speed", Operator.GTE, 100, "Gb/s"),
            q("rdma", Operator.HAS, "*"),
            q("offloads", Operator.HAS, "IPsec"),
        ],
    )


def test_official_e810_case(products: dict[str, Product]) -> None:
    out = recommend(products, "E810-CQDA2", official_query())
    recs = [
        (r.product.part_number, r.commercial.price_usd, r.commercial.stock_units)
        for r in out.recommendations
    ]
    assert recs == [
        ("MCX75310AAS-NEAT", Decimal("1250.00"), 120),
        ("BCM57508", Decimal("890.00"), 75),
    ]
    assert all(
        r.compatibility.level is CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS
        for r in out.recommendations
    )
    assert all(r.compatibility.coverage == 1.0 for r in out.recommendations)
    assert out.risky_options == []


@pytest.mark.safety
def test_invariants_for_every_non_active_part(products: dict[str, Product]) -> None:
    for part, product in products.items():
        assert product.commercial is not None
        if product.commercial.status is CommercialStatus.ACTIVE:
            continue
        out = recommend(products, part)
        for rec in out.recommendations + out.risky_options:
            assert rec.product.category is product.category, (part, rec.product.part_number)
            assert rec.compatibility.level is not CompatibilityLevel.INCOMPATIBLE
            critical_fail = [
                r for r in rec.compatibility.rule_results
                if r.severity is Severity.CRITICAL and r.outcome is RuleOutcome.FAIL
            ]  # fmt: skip
            assert not critical_fail, (part, rec.product.part_number)
        assert all(r.commercial.status is CommercialStatus.ACTIVE for r in out.recommendations)
        assert all(r.commercial.status is CommercialStatus.NRND for r in out.risky_options)
        assert all(
            r.compatibility.level is not CompatibilityLevel.UNKNOWN for r in out.recommendations
        )
        assert all(
            r.compatibility.level is CompatibilityLevel.UNKNOWN for r in out.unverified_options
        )


@pytest.mark.parametrize(
    ("part", "expected"),
    [
        (
            "USB-2627",
            ["USB-2633"],
        ),  # the datasheet's recommended replacement is the only one that fits
        ("MPU-6050", []),  # BME680 does not measure rotation/acceleration
        ("WUS4C6464DSP3X5", []),  # 990 PRO: 2 TB < 6.4 TB and M.2 ≠ U.2
        ("IR3555MTRPBF", []),  # TPS65982 is a USB-PD controller, not a power stage
        ("A100-SXM4-80GB", []),  # H100-SXM5: different form factor (SXM5 vs SXM4)
    ],
)
def test_known_outcomes(products: dict[str, Product], part: str, expected: list[str]) -> None:
    assert [r.product.part_number for r in recommend(products, part).recommendations] == expected


def test_arm_core_never_gets_a_confirmed_x86_replacement(products: dict[str, Product]) -> None:
    out = recommend(products, "Cortex-A78")
    assert out.recommendations == []  # ADR-013: UNKNOWN is never presented as recommended
    assert [r.product.part_number for r in out.unverified_options] == ["w9-3595X"]
    assert "architecture" in out.unverified_options[0].compatibility.missing
