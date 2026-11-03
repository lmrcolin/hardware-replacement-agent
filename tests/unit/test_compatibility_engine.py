"""Compatibility engine (B-15): rule routing, outcomes and level precedence. Synthetic data only."""

from __future__ import annotations

import pytest

from advisor.compatibility import evaluate
from advisor.compatibility.checks import Check, compare, parse_interface
from advisor.models import (
    Category,
    CompatibilityLevel,
    Operator,
    Priority,
    Product,
    ProductSpecification,
    RequirementOrigin,
    RuleOutcome,
    Severity,
    SpecValue,
    TechnicalRequirement,
)


def req(
    key: str,
    op: Operator,
    value: SpecValue,
    *,
    priority: Priority = Priority.MUST,
    unit: str | None = None,
) -> TechnicalRequirement:
    return TechnicalRequirement(
        key=key,
        operator=op,
        value=value,
        unit=unit,
        priority=priority,
        origin=RequirementOrigin.QUERY,
    )


def product(pn: str, category: Category, **specs: SpecValue | tuple[SpecValue, str]) -> Product:
    items = []
    for key, raw in specs.items():
        value, unit = raw if isinstance(raw, tuple) else (raw, None)
        items.append(ProductSpecification(key=key, value=value, unit=unit))
    return Product(
        part_number=pn,
        manufacturer="Synthetic Labs (fictitious)",
        category=category,
        specifications=items,
        is_synthetic=True,
    )


NIC_OLD = product(
    "SYN-NIC-A",
    Category.NETWORK,
    port_speed=(100, "Gb/s"),
    rdma=["RoCE v2", "iWARP"],
    host_interface="PCIe 4.0 x16",
)
NIC_SAME = product(
    "SYN-NIC-B",
    Category.NETWORK,
    port_speed=(100, "Gb/s"),
    rdma=["RoCE v2"],
    host_interface="PCIe Gen4 x16",
)
NIC_FAST = product(
    "SYN-NIC-C",
    Category.NETWORK,
    port_speed=(400, "Gb/s"),
    rdma=["RoCE v2", "iWARP"],
    host_interface="PCIe 5.0 x16",
)
NIC_NO_RDMA = product("SYN-NIC-D", Category.NETWORK, port_speed=(100, "Gb/s"))


# ----------------------------------------------------------------- checks


@pytest.mark.parametrize(
    ("op", "required", "candidate", "expected"),
    [
        (Operator.GTE, 100, 200, Check.PASS),
        (Operator.GTE, 100, 50, Check.FAIL),
        (Operator.LTE, 400, 350, Check.PASS),
        (Operator.LTE, 400, 700, Check.FAIL),
        (Operator.GTE, 100, None, Check.MISSING),
        (Operator.GTE, 100, "fast", Check.MISSING),
        (Operator.HAS, "RoCE v2", ["RoCE v2", "iWARP"], Check.PASS),
        (Operator.HAS, "roce-v2", ["RoCE v2"], Check.PASS),
        (Operator.HAS, ["RoCE v2", "iWARP"], ["RoCE v2"], Check.FAIL),
        (Operator.EQ, "SXM", ["SXM", "PCIe"], Check.PASS),
        (Operator.EQ, "OAM", ["SXM", "PCIe"], Check.FAIL),
        (Operator.IN, ["U.2", "M.2"], "M.2", Check.PASS),
        (Operator.EQ, "PCIe 4.0 x16", "PCIe Gen4 x16", Check.FAIL),
        (Operator.EQ, "PCIe 4.0 x16", "PCIe 5.0 x16", Check.UPGRADE),
        (Operator.EQ, "USB 2.0", "USB 3.0", Check.UPGRADE),
        (Operator.EQ, "PCIe 5.0 x16", "PCIe 4.0 x16", Check.FAIL),
        (Operator.EQ, "PCIe 4.0 x16", "PCIe 5.0 x8", Check.FAIL),
        (Operator.EQ, True, True, Check.PASS),
        (Operator.EQ, True, "yes", Check.MISSING),
    ],
)
def test_compare(
    op: Operator, required: SpecValue, candidate: SpecValue | None, expected: Check
) -> None:
    assert compare(op, required, candidate) is expected


def test_parse_interface_variants() -> None:
    assert parse_interface("PCIe Gen5 x16") == parse_interface("PCIe 5.0 x16")
    assert parse_interface("USB3.0") is not None
    assert parse_interface("SPI/PAR") is None


# ---------------------------------------------------------------- engine


def test_category_mismatch_is_incompatible_and_short_circuits() -> None:
    mcu = product("SYN-MCU-X", Category.MICROCONTROLLER, sram=(128, "KB"))
    result = evaluate(NIC_OLD, mcu, [req("port_speed", Operator.GTE, 100)])
    assert result.level is CompatibilityLevel.INCOMPATIBLE
    assert [r.rule_id for r in result.rule_results] == ["R-CAT"]
    assert result.coverage == 0.0


def test_no_requirements_same_category_is_compatible() -> None:
    result = evaluate(NIC_OLD, NIC_SAME, [])
    assert result.level is CompatibilityLevel.COMPATIBLE
    assert result.coverage == 1.0


def test_missing_mandatory_protocol_is_incompatible() -> None:
    result = evaluate(NIC_OLD, NIC_SAME, [req("rdma", Operator.HAS, "iWARP")])
    assert result.level is CompatibilityLevel.INCOMPATIBLE
    proto = result.rule_results[1]
    assert (proto.rule_id, proto.outcome, proto.severity) == (
        "R-MUST-PROTO",
        RuleOutcome.FAIL,
        Severity.CRITICAL,
    )


def test_missing_critical_data_is_unknown_never_compatible() -> None:
    result = evaluate(NIC_OLD, NIC_NO_RDMA, [req("rdma", Operator.HAS, "RoCE v2")])
    assert result.level is CompatibilityLevel.UNKNOWN
    assert result.missing == ["rdma"]
    assert result.rule_results[1].rule_id == "R-MISSING"


def test_registry_critical_spec_fails_hard_even_if_should() -> None:
    # port_speed is `critical: true` for Network in spec_registry.yaml.
    slow = product("SYN-NIC-E", Category.NETWORK, port_speed=(25, "Gb/s"))
    result = evaluate(
        NIC_OLD, slow, [req("port_speed", Operator.GTE, 100, priority=Priority.SHOULD)]
    )
    assert result.level is CompatibilityLevel.INCOMPATIBLE


def test_non_critical_failure_gives_conditions() -> None:
    # sriov_vfs is not critical and the requirement is SHOULD => conditional, not incompatible.
    nic = product("SYN-NIC-F", Category.NETWORK, sriov_vfs=(128, "count"))
    result = evaluate(NIC_OLD, nic, [req("sriov_vfs", Operator.GTE, 256, priority=Priority.SHOULD)])
    assert result.level is CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS
    assert result.conditions
    assert result.coverage == 1.0  # no MUST requirements


def test_interface_and_speed_upgrades_are_conditional() -> None:
    result = evaluate(
        NIC_OLD,
        NIC_FAST,
        [
            req("port_speed", Operator.GTE, 100),
            req("host_interface", Operator.EQ, "PCIe 4.0 x16"),
            req("rdma", Operator.HAS, "RoCE v2"),
        ],
    )
    assert result.level is CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS
    upgrades = [r for r in result.rule_results if r.rule_id == "R-UPGRADE"]
    assert {r.requirement.key for r in upgrades if r.requirement} == {
        "port_speed",
        "host_interface",
    }
    assert result.coverage == 1.0
    assert len(result.conditions) == 2


def test_incompatible_units_are_missing_not_match() -> None:
    result = evaluate(NIC_OLD, NIC_SAME, [req("port_speed", Operator.GTE, 100, unit="MB/s")])
    assert result.level is CompatibilityLevel.UNKNOWN
    assert result.rule_results[1].outcome is RuleOutcome.MISSING


def test_form_factor_and_electrical_rules_are_routed() -> None:
    a100 = product("SYN-GPU-A", Category.GPU, form_factor=["SXM4", "PCIe"], tdp=(400, "W"))
    h100 = product("SYN-GPU-B", Category.GPU, form_factor=["SXM5", "PCIe"], tdp=(700, "W"))
    oam = product("SYN-GPU-C", Category.GPU, form_factor=["OAM"], tdp=(750, "W"))
    reqs = [req("form_factor", Operator.EQ, "PCIe"), req("tdp", Operator.LTE, 400)]

    h = evaluate(a100, h100, reqs)
    assert [r.rule_id for r in h.rule_results] == ["R-CAT", "R-FF", "R-ELEC"]
    assert h.level is CompatibilityLevel.INCOMPATIBLE  # TDP 700 W > 400 W envelope

    o = evaluate(a100, oam, reqs[:1])
    assert o.rule_results[1].outcome is RuleOutcome.FAIL
    assert o.level is CompatibilityLevel.INCOMPATIBLE


def test_evidence_and_values_are_reported() -> None:
    result = evaluate(NIC_OLD, NIC_SAME, [req("port_speed", Operator.GTE, 100)])
    rule = result.rule_results[1]
    assert (rule.original_value, rule.candidate_value) == (100, 100)
    assert rule.requirement is not None and rule.requirement.key == "port_speed"


def test_score_never_promotes_level() -> None:
    reqs = [req("port_speed", Operator.GTE, 100), req("rdma", Operator.HAS, "iWARP")]
    worse = evaluate(NIC_OLD, NIC_SAME, reqs)  # fails iWARP but passes speed
    assert worse.level is CompatibilityLevel.INCOMPATIBLE
    assert worse.score > 0


def test_product_cannot_be_its_own_candidate() -> None:
    with pytest.raises(ValueError, match="own candidate"):
        evaluate(NIC_OLD, NIC_OLD, [])
