"""Recommendations returned to the user."""

from __future__ import annotations

from pydantic import Field, model_validator

from advisor.models.base import Contract
from advisor.models.compatibility import CompatibilityResult
from advisor.models.conversation import ToolCall
from advisor.models.documents import Evidence
from advisor.models.enums import CommercialStatus, CompatibilityLevel
from advisor.models.products import CommercialInformation, Product
from advisor.models.query import (
    ConversationContext,
    CustomerQuery,
    ParsedQuery,
    TechnicalRequirement,
)
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


CONFIRMED_LEVELS = (CompatibilityLevel.COMPATIBLE, CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS)


class Relaxation(Contract):
    """A sale that becomes possible if the customer drops one requirement (never a recommendation:
    it does NOT meet what was asked)."""

    dropped: TechnicalRequirement
    option: Recommendation

    @model_validator(mode="after")
    def _sellable(self) -> Relaxation:
        if self.option.commercial.status is not CommercialStatus.ACTIVE:
            raise ValueError("relaxation options must be ACTIVE")
        if self.option.compatibility.level not in CONFIRMED_LEVELS:
            raise ValueError("relaxation options must be confirmed once the requirement is dropped")
        return self


class RecommendationResponse(Contract):
    contract_version: str = CONTRACT_VERSION
    query: CustomerQuery
    parsed_query: ParsedQuery | None = None
    original: Product | None = None
    recommendations: list[Recommendation] = []  # ACTIVE and COMPATIBLE / WITH_CONDITIONS only
    risky_options: list[Recommendation] = []  # NRND only
    # ACTIVE candidates whose critical data is missing (UNKNOWN): never presented as recommended
    # (ADR-013); they need expert validation.
    unverified_options: list[Recommendation] = []
    clarification_question: str | None = None
    clarification_options: list[str] = []  # quick answers offered with the question (1.2.0)
    relaxations: list[Relaxation] = []  # options if one requirement is dropped (1.2.0)
    citations: list[Evidence] = []  # datasheet passages behind a technical answer (1.2.0)
    tool_calls: list[ToolCall] = []  # what the agent did, in order (1.2.0)
    context: ConversationContext | None = None  # memory to send with the next turn (1.2.0)
    message: str
    llm_provider: str = "template"
    warnings: list[str] = []
    is_synthetic: bool = False

    @model_validator(mode="after")
    def _status_rules(self) -> RecommendationResponse:
        for rec in self.recommendations:
            if rec.commercial.status is not CommercialStatus.ACTIVE:
                raise ValueError(f"{rec.product.part_number}: only ACTIVE can be recommended")
            if rec.compatibility.level not in CONFIRMED_LEVELS:
                raise ValueError(
                    f"{rec.product.part_number}: recommendations need a confirmed level "
                    f"(got {rec.compatibility.level}); UNKNOWN goes to unverified_options"
                )
        for rec in self.unverified_options:
            if rec.commercial.status is not CommercialStatus.ACTIVE:
                raise ValueError(f"{rec.product.part_number}: unverified_options are ACTIVE only")
            if rec.compatibility.level is not CompatibilityLevel.UNKNOWN:
                raise ValueError(f"{rec.product.part_number}: unverified_options are UNKNOWN only")
        for rec in self.risky_options:
            if rec.commercial.status is not CommercialStatus.NRND:
                raise ValueError(f"{rec.product.part_number}: risky_options are NRND only")
        ranks = [r.rank for r in self.recommendations]
        if ranks != sorted(ranks) or len(ranks) != len(set(ranks)):
            raise ValueError("recommendation ranks must be unique and ascending")
        return self
