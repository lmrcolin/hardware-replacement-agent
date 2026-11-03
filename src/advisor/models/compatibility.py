"""Candidates and compatibility results."""

from __future__ import annotations

from pydantic import Field, model_validator

from advisor.models.base import Contract
from advisor.models.documents import Evidence
from advisor.models.enums import CompatibilityLevel, DiscoveryPath, RuleOutcome, Severity
from advisor.models.products import SpecValue
from advisor.models.query import TechnicalRequirement


class CandidateProduct(Contract):
    part_number: str
    discovery_paths: list[DiscoveryPath] = Field(min_length=1)
    discovery_score: float = Field(default=0.0, ge=0.0)


class RuleResult(Contract):
    rule_id: str = Field(pattern=r"^R-[A-Z0-9-]+$")
    severity: Severity
    outcome: RuleOutcome
    message: str
    requirement: TechnicalRequirement | None = None
    original_value: SpecValue | None = None
    candidate_value: SpecValue | None = None
    evidence: list[Evidence] = []


class CompatibilityResult(Contract):
    original_part_number: str
    candidate_part_number: str
    level: CompatibilityLevel
    rule_results: list[RuleResult] = []
    coverage: float = Field(ge=0.0, le=1.0)  # share of MUST requirements satisfied
    score: float = Field(ge=0.0)
    conditions: list[str] = []
    missing: list[str] = []

    @model_validator(mode="after")
    def _level_respects_critical_rules(self) -> CompatibilityResult:
        if self.original_part_number == self.candidate_part_number:
            raise ValueError("a product cannot be its own candidate")
        critical = [r for r in self.rule_results if r.severity is Severity.CRITICAL]
        if any(r.outcome is RuleOutcome.FAIL for r in critical):
            if self.level is not CompatibilityLevel.INCOMPATIBLE:
                raise ValueError("a failed CRITICAL rule requires level INCOMPATIBLE")
        elif any(r.outcome is RuleOutcome.MISSING for r in critical) and self.level in (
            CompatibilityLevel.COMPATIBLE,
            CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS,
        ):
            raise ValueError("missing CRITICAL data caps the level at UNKNOWN")
        return self
