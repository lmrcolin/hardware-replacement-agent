"""Safety and behaviour tests for the deterministic compatibility engine and ranking."""

from __future__ import annotations

from decimal import Decimal

import pytest

from advisor.commercial import CommercialEngine
from advisor.compatibility import derive_requirements, evaluate
from advisor.compatibility.engine import _interface
from advisor.models import (
    Category,
    CommercialInformation,
    CommercialStatus,
    CompatibilityLevel,
    CompatibilityResult,
    Evidence,
    Operator,
    ParsedQuery,
    Priority,
    Product,
    ProductSpecification,
    RequirementOrigin,
    RuleOutcome,
    TechnicalRequirement,
)
from advisor.recommendation import rank

EV = [Evidence(document_id="0" * 64, page=1, quote="synthetic")]


def nic(
    part: str, status: CommercialStatus = CommercialStatus.ACTIVE, stock: int = 10, **specs: object
) -> Product:
    price = Decimal("100.00") if status is CommercialStatus.ACTIVE else None
    defaults: dict[str, object] = {
        "port_speed": 100,
        "host_interface": "PCIe 4.0 x16",
        "rdma": ["RoCE v2"],
    }
    defaults.update(specs)
    units = {"port_speed": "Gb/s"}
    return Product(
        part_number=part,
        manufacturer="Synthetic Labs (fictitious)",
        category=Category.NETWORK,
        specifications=[
            ProductSpecification(key=k, value=v, unit=units.get(k), evidence=EV)  # type: ignore[arg-type]
            for k, v in defaults.items()
            if v is not None
        ],
        commercial=CommercialInformation(
            part_number=part,
            description=part,
            manufacturer="Synthetic Labs (fictitious)",
            category=Category.NETWORK,
            status=status,
            price_usd=price,
            stock_units=stock,
        ),
        is_synthetic=True,
    )


def req(
    key: str,
    op: Operator,
    value: object,
    priority: Priority = Priority.MUST,
    unit: str | None = None,
) -> TechnicalRequirement:
    return TechnicalRequirement(
        key=key,
        operator=op,
        value=value,
        unit=unit,
        priority=priority,  # type: ignore[arg-type]
        origin=RequirementOrigin.QUERY,
    )


ORIGINAL = nic("SYN-OLD", CommercialStatus.DISCONTINUED)


# ---------------------------------------------------------------- safety


@pytest.mark.safety
def test_missing_must_protocol_is_incompatible() -> None:
    result = evaluate(ORIGINAL, nic("SYN-A"), [req("rdma", Operator.HAS, "iWARP")])
    assert result.level is CompatibilityLevel.INCOMPATIBLE


@pytest.mark.safety
def test_lower_must_number_is_incompatible() -> None:
    result = evaluate(
        ORIGINAL, nic("SYN-A", port_speed=40), [req("port_speed", Operator.GTE, 100, unit="Gb/s")]
    )
    assert result.level is CompatibilityLevel.INCOMPATIBLE


@pytest.mark.safety
@pytest.mark.parametrize("missing_key", ["port_speed", "rdma"])
def test_missing_critical_data_is_unknown_never_compatible(missing_key: str) -> None:
    candidate = nic("SYN-A", **{missing_key: None})
    reqs = [req("port_speed", Operator.GTE, 100, unit="Gb/s"), req("rdma", Operator.HAS, "*")]
    result = evaluate(ORIGINAL, candidate, reqs)
    assert result.level is CompatibilityLevel.UNKNOWN
    assert missing_key in result.missing


@pytest.mark.safety
def test_should_failures_only_add_conditions() -> None:
    result = evaluate(ORIGINAL, nic("SYN-A"), [req("rdma", Operator.HAS, "iWARP", Priority.SHOULD)])
    assert result.level is CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS
    assert any("iWARP" in c for c in result.conditions)


def test_identical_specs_are_compatible() -> None:
    reqs = derive_requirements(ORIGINAL, ParsedQuery(original_text="x"))
    result = evaluate(ORIGINAL, nic("SYN-A"), reqs)
    assert result.level is CompatibilityLevel.COMPATIBLE and result.coverage == 1.0


def test_upgrade_is_conditional_with_explicit_condition() -> None:
    reqs = derive_requirements(ORIGINAL, ParsedQuery(original_text="x"))
    result = evaluate(ORIGINAL, nic("SYN-A", port_speed=400), reqs)
    assert result.level is CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS
    assert any(r.rule_id == "R-UPGRADE" for r in result.rule_results)


def test_unit_conversion_before_comparing() -> None:
    result = evaluate(
        ORIGINAL, nic("SYN-A"), [req("port_speed", Operator.GTE, 100_000, unit="Mbps")]
    )
    assert result.level is CompatibilityLevel.COMPATIBLE


def test_query_requirements_win_over_derived_ones() -> None:
    query = ParsedQuery(
        original_text="x", requirements=[req("port_speed", Operator.GTE, 25, unit="Gb/s")]
    )
    reqs = derive_requirements(ORIGINAL, query)
    assert [r.value for r in reqs if r.key == "port_speed"] == [25]


@pytest.mark.parametrize(
    ("required", "candidate", "outcome"),
    [
        ("PCIe 4.0 x16", "PCIe 4.0 x16", RuleOutcome.PASS),
        ("PCIe 4.0 x16", "PCIe 5.0 x16", RuleOutcome.CONDITIONAL),
        ("PCIe 4.0 x8", "PCIe 4.0 x16", RuleOutcome.FAIL),
        ("USB 2.0", "USB 3.0", RuleOutcome.CONDITIONAL),
        ("USB 2.0", "SPI/PAR", RuleOutcome.FAIL),
    ],
)
def test_interface_rules(required: str, candidate: str, outcome: RuleOutcome) -> None:
    assert _interface(required, candidate)[0] is outcome


# ---------------------------------------------------------------- ranking


def _result(
    part: str, level: CompatibilityLevel, coverage: float = 1.0, score: float = 1.0
) -> CompatibilityResult:
    return CompatibilityResult(original_part_number="SYN-OLD", candidate_part_number=part, level=level,
                               coverage=coverage, score=score)  # fmt: skip


@pytest.mark.safety
def test_stock_never_beats_compatibility_level() -> None:
    products = {"SYN-A": nic("SYN-A", stock=1), "SYN-B": nic("SYN-B", stock=10_000)}
    out = rank(
        [
            _result("SYN-B", CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS),
            _result("SYN-A", CompatibilityLevel.COMPATIBLE),
        ],
        products,
    )
    assert [r.product.part_number for r in out.recommendations] == ["SYN-A", "SYN-B"]


def test_stock_breaks_exact_ties() -> None:
    products = {"SYN-A": nic("SYN-A", stock=1), "SYN-B": nic("SYN-B", stock=50)}
    out = rank(
        [
            _result("SYN-A", CompatibilityLevel.COMPATIBLE),
            _result("SYN-B", CompatibilityLevel.COMPATIBLE),
        ],
        products,
    )
    assert [r.product.part_number for r in out.recommendations] == ["SYN-B", "SYN-A"]


@pytest.mark.safety
def test_only_active_recommended_nrnd_risky_rest_dropped() -> None:
    products = {
        "SYN-A": nic("SYN-A"),
        "SYN-N": nic("SYN-N", CommercialStatus.NRND),
        "SYN-D": nic("SYN-D", CommercialStatus.DISCONTINUED),
        "SYN-E": nic("SYN-E", CommercialStatus.EOL),
        "SYN-I": nic("SYN-I"),
    }
    results = [
        _result(p, CompatibilityLevel.COMPATIBLE) for p in ("SYN-A", "SYN-N", "SYN-D", "SYN-E")
    ]
    results.append(_result("SYN-I", CompatibilityLevel.INCOMPATIBLE, 0.0, 0.0))
    out = rank(results, products)
    assert [r.product.part_number for r in out.recommendations] == ["SYN-A"]
    assert [r.product.part_number for r in out.risky_options] == ["SYN-N"]
    assert out.unverified_options == []


@pytest.mark.safety
def test_unknown_goes_to_unverified_not_recommendations() -> None:
    products = {"SYN-A": nic("SYN-A"), "SYN-U": nic("SYN-U", stock=10_000)}
    out = rank(
        [
            _result("SYN-U", CompatibilityLevel.UNKNOWN),
            _result("SYN-A", CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS),
        ],
        products,
    )
    assert [r.product.part_number for r in out.recommendations] == ["SYN-A"]
    assert [r.product.part_number for r in out.unverified_options] == ["SYN-U"]
    assert out.unverified_options[0].rank == 1


def test_commercial_engine_hides_price_of_non_active() -> None:
    engine = CommercialEngine(
        [nic("SYN-A").commercial, nic("SYN-N", CommercialStatus.NRND).commercial]
    )  # type: ignore[list-item]
    assert engine.availability("SYN-A").price_usd == Decimal("100.00")
    assert engine.availability("SYN-N").price_usd is None
    with pytest.raises(KeyError):
        engine.get("NOPE")


@pytest.mark.parametrize(
    ("required", "candidate", "outcome"),
    [
        ("USB", "USB 3.0", RuleOutcome.PASS),
        ("PCIe", "PCIe 5.0 x16", RuleOutcome.PASS),
        ("USB", "SPI/PAR", RuleOutcome.FAIL),
    ],
)
def test_family_only_interface_requirement(
    required: str, candidate: str, outcome: RuleOutcome
) -> None:
    assert _interface(required, candidate)[0] is outcome
