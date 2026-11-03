"""Customer queries and technical requirements."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from advisor.models.base import Contract
from advisor.models.enums import Category, Operator, Priority, RequirementOrigin
from advisor.models.products import SpecValue


class CustomerQuery(Contract):
    text: str = Field(min_length=1, max_length=4000)
    language: Literal["es", "en"] | None = None
    session_id: str | None = None


class TechnicalRequirement(Contract):
    key: str = Field(min_length=1)
    operator: Operator
    value: SpecValue
    unit: str | None = None
    priority: Priority = Priority.MUST
    origin: RequirementOrigin

    @model_validator(mode="after")
    def _value_fits_operator(self) -> TechnicalRequirement:
        numeric = isinstance(self.value, int | float) and not isinstance(self.value, bool)
        if self.operator in (Operator.GTE, Operator.LTE) and not numeric:
            raise ValueError(f"{self.operator} requires a numeric value")
        if self.operator is Operator.IN and not isinstance(self.value, list):
            raise ValueError("IN requires a list value")
        return self


class ParsedQuery(Contract):
    original_text: str
    intent: Literal["replace", "find", "status", "other"] = "replace"
    part_numbers: list[str] = []
    category: Category | None = None
    requirements: list[TechnicalRequirement] = []
    needs_clarification: bool = False
    clarification_question: str | None = None

    @model_validator(mode="after")
    def _clarification_has_question(self) -> ParsedQuery:
        if self.needs_clarification and not self.clarification_question:
            raise ValueError("needs_clarification requires clarification_question")
        return self
