"""Recommendations returned to the user."""

from __future__ import annotations

from pydantic import Field, model_validator

from advisor.models.base import Contract
from advisor.models.compatibility import CompatibilityResult
from advisor.models.documents import Evidence
from advisor.models.enums import CommercialStatus, CompatibilityLevel
from advisor.models.products import CommercialInformation, Product
from advisor.models.query import CustomerQuery, ParsedQuery
from advisor.models.version import CONTRACT_VERSION


class Recommendation(Contract):
    rank: int = Field(ge=1)
    product: Product
    commercial: CommercialInformation
    compatibility: CompatibilityResult
    covered_requirements: list[str] = []
    uncovered_requirements: list[str] = []
    rationale: str
    evidence: list[Evidence] = []

    @model_validator(mode="after")
    def _consistent(self) -> Recommendation:
        if self.commercial.part_number != self.product.part_number:
            raise ValueError("commercial info must belong to the recommended product")
        if self.compatibility.candidate_part_number != self.product.part_number:
            raise ValueError("compatibility result must refer to the recommended product")
        if self.compatibility.level is CompatibilityLevel.INCOMPATIBLE:
            raise ValueError("INCOMPATIBLE products cannot be recommended")
        return self


class RecommendationResponse(Contract):
    contract_version: str = CONTRACT_VERSION
    query: CustomerQuery
    parsed_query: ParsedQuery | None = None
    original: Product | None = None
    recommendations: list[Recommendation] = []  # ACTIVE only
    risky_options: list[Recommendation] = []  # NRND only
    clarification_question: str | None = None
    message: str
    llm_provider: str = "template"
    warnings: list[str] = []
    is_synthetic: bool = False

    @model_validator(mode="after")
    def _status_rules(self) -> RecommendationResponse:
        for rec in self.recommendations:
            if rec.commercial.status is not CommercialStatus.ACTIVE:
                raise ValueError(f"{rec.product.part_number}: only ACTIVE can be recommended")
        for rec in self.risky_options:
            if rec.commercial.status is not CommercialStatus.NRND:
                raise ValueError(f"{rec.product.part_number}: risky_options are NRND only")
        ranks = [r.rank for r in self.recommendations]
        if ranks != sorted(ranks) or len(ranks) != len(set(ranks)):
            raise ValueError("recommendation ranks must be unique and ascending")
        return self
