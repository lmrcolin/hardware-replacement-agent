"""Model contracts: validators encode the hard rules and fixtures always conform."""

from __future__ import annotations

import warnings
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from advisor.compatibility import load_rules
from advisor.config import load_settings
from advisor.extraction import load_spec_registry
from advisor.models import (
    CONTRACT_VERSION,
    Category,
    CommercialInformation,
    CommercialStatus,
    CompatibilityLevel,
    CompatibilityResult,
    DataConsistencyWarning,
    EdgeType,
    GraphEdge,
    Operator,
    ParsedQuery,
    Product,
    Recommendation,
    RecommendationResponse,
    RequirementOrigin,
    RuleOutcome,
    RuleResult,
    Severity,
    TechnicalRequirement,
)

pytestmark = pytest.mark.contract
ROOT = Path(__file__).resolve().parents[2]


def _commercial(
    status: CommercialStatus, price: str | None, part: str = "X-1"
) -> CommercialInformation:
    return CommercialInformation(
        part_number=part,
        description="d",
        manufacturer="m",
        category=Category.NETWORK,
        status=status,
        price_usd=Decimal(price) if price else None,
        stock_units=10,
    )


def _rule(outcome: RuleOutcome, severity: Severity = Severity.CRITICAL) -> RuleResult:
    return RuleResult(rule_id="R-CAT", severity=severity, outcome=outcome, message="m")


def _result(level: CompatibilityLevel, *rules: RuleResult, cand: str = "B") -> CompatibilityResult:
    return CompatibilityResult(
        original_part_number="A",
        candidate_part_number=cand,
        level=level,
        rule_results=list(rules),
        coverage=1.0,
        score=1.0,
    )


def test_contract_version_is_semver() -> None:
    assert CONTRACT_VERSION == "1.0.0"


class TestCommercial:
    def test_price_on_non_active_warns(self) -> None:
        with pytest.warns(DataConsistencyWarning):
            _commercial(CommercialStatus.NRND, "10.00")

    def test_active_without_price_warns(self) -> None:
        with pytest.warns(DataConsistencyWarning):
            _commercial(CommercialStatus.ACTIVE, None)

    def test_consistent_rows_do_not_warn(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            _commercial(CommercialStatus.ACTIVE, "5.00")
            _commercial(CommercialStatus.DISCONTINUED, None)

    def test_inventory_value(self) -> None:
        assert _commercial(CommercialStatus.ACTIVE, "2.50").inventory_value_usd == Decimal("25.00")
        assert _commercial(CommercialStatus.EOL, None).inventory_value_usd is None

    def test_json_roundtrip_with_computed_field(self) -> None:
        row = _commercial(CommercialStatus.ACTIVE, "2.50")
        assert CommercialInformation.model_validate(row.model_dump(mode="json")) == row

    def test_negative_stock_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CommercialInformation(
                part_number="X",
                description="d",
                manufacturer="m",
                category=Category.CPU,
                status=CommercialStatus.EOL,
                stock_units=-1,
            )


class TestCompatibilityResult:
    def test_critical_fail_forces_incompatible(self) -> None:
        with pytest.raises(ValidationError, match="INCOMPATIBLE"):
            _result(CompatibilityLevel.COMPATIBLE, _rule(RuleOutcome.FAIL))
        assert _result(CompatibilityLevel.INCOMPATIBLE, _rule(RuleOutcome.FAIL))

    @pytest.mark.parametrize(
        "level", [CompatibilityLevel.COMPATIBLE, CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS]
    )
    def test_critical_missing_caps_at_unknown(self, level: CompatibilityLevel) -> None:
        with pytest.raises(ValidationError, match="UNKNOWN"):
            _result(level, _rule(RuleOutcome.MISSING))
        assert _result(CompatibilityLevel.UNKNOWN, _rule(RuleOutcome.MISSING))

    def test_minor_fail_allows_conditions(self) -> None:
        r = _result(
            CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS, _rule(RuleOutcome.FAIL, Severity.MINOR)
        )
        assert r.level is CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS

    def test_self_candidate_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _result(CompatibilityLevel.COMPATIBLE, cand="A")


class TestRequirementsAndQuery:
    def test_gte_requires_number(self) -> None:
        with pytest.raises(ValidationError):
            TechnicalRequirement(
                key="k", operator=Operator.GTE, value="fast", origin=RequirementOrigin.QUERY
            )

    def test_in_requires_list(self) -> None:
        with pytest.raises(ValidationError):
            TechnicalRequirement(
                key="k", operator=Operator.IN, value="a", origin=RequirementOrigin.QUERY
            )

    def test_clarification_needs_question(self) -> None:
        with pytest.raises(ValidationError):
            ParsedQuery(original_text="x", needs_clarification=True)


class TestGraph:
    def test_migrates_to_requires_evidence(self) -> None:
        with pytest.raises(ValidationError):
            GraphEdge(source="product:A", target="product:B", edge_type=EdgeType.MIGRATES_TO)

    def test_no_self_loops(self) -> None:
        with pytest.raises(ValidationError):
            GraphEdge(source="product:A", target="product:A", edge_type=EdgeType.SIMILAR_TO)


class TestRecommendationResponse:
    def _rec(
        self, products: dict[str, Product], part: str, level: CompatibilityLevel
    ) -> Recommendation:
        p = products[part]
        assert p.commercial is not None
        return Recommendation(
            rank=1,
            product=p,
            commercial=p.commercial,
            rationale="r",
            compatibility=CompatibilityResult(
                original_part_number="SYN-NIC-100",
                candidate_part_number=part,
                level=level,
                coverage=1.0,
                score=1.0,
            ),
        )

    def test_only_active_in_recommendations(self, products: dict[str, Product], responses) -> None:  # type: ignore[no-untyped-def]
        base = responses["replacement_found"]
        rec = self._rec(products, "SYN-GPU-100", CompatibilityLevel.COMPATIBLE)  # NRND
        with pytest.raises(ValidationError, match="ACTIVE"):
            RecommendationResponse(query=base.query, recommendations=[rec], message="m")

    def test_risky_options_only_nrnd(self, products: dict[str, Product], responses) -> None:  # type: ignore[no-untyped-def]
        base = responses["replacement_found"]
        active = self._rec(products, "SYN-NIC-200", CompatibilityLevel.COMPATIBLE)
        with pytest.raises(ValidationError, match="NRND"):
            RecommendationResponse(query=base.query, risky_options=[active], message="m")
        nrnd = self._rec(products, "SYN-GPU-100", CompatibilityLevel.UNKNOWN)
        assert RecommendationResponse(query=base.query, risky_options=[nrnd], message="m")

    def test_incompatible_cannot_be_recommended(self, products: dict[str, Product]) -> None:
        with pytest.raises(ValidationError, match="INCOMPATIBLE"):
            self._rec(products, "SYN-NIC-200", CompatibilityLevel.INCOMPATIBLE)


class TestFixtures:
    def test_six_synthetic_products(self, products: dict[str, Product]) -> None:
        assert len(products) == 6
        assert all(p.is_synthetic and p.part_number.startswith("SYN-") for p in products.values())
        cats = sorted(p.category.value for p in products.values())
        assert cats == ["DAQ", "GPU", "GPU", "Microcontroller", "Network", "Network"]

    def test_every_spec_has_evidence(self, products: dict[str, Product]) -> None:
        assert all(s.evidence for p in products.values() for s in p.specifications)

    def test_three_responses_valid(self, responses: dict[str, RecommendationResponse]) -> None:
        assert set(responses) == {"replacement_found", "clarification", "no_substitute"}
        assert all(
            r.is_synthetic and r.contract_version == CONTRACT_VERSION for r in responses.values()
        )

    def test_mock_graph_has_products(self, mock_graph, products: dict[str, Product]) -> None:  # type: ignore[no-untyped-def]
        assert {f"product:{p}" for p in products} <= set(mock_graph.nodes)


class TestConfig:
    def test_settings_load(self) -> None:
        s = load_settings(ROOT / "config" / "settings.yaml")
        assert s.databricks.volume_pdf_dir == "/Volumes/emerson_hw/bronze/raw_files"
        assert s.llm.providers[-1] == "template"

    def test_spec_registry_covers_all_categories(self) -> None:
        reg = load_spec_registry(ROOT / "config" / "spec_registry.yaml")
        assert set(reg.categories) == set(Category)
        assert all(3 <= len(keys) <= 6 for keys in reg.categories.values())
        assert all(any(d.critical for d in keys.values()) for keys in reg.categories.values())

    def test_compat_rules_declared(self) -> None:
        ids = {r.id for r in load_rules(ROOT / "config" / "compat_rules.yaml").rules}
        assert ids == {
            "R-CAT",
            "R-FF",
            "R-MUST-PROTO",
            "R-ELEC",
            "R-NUM-GTE",
            "R-UPGRADE",
            "R-MISSING",
        }
