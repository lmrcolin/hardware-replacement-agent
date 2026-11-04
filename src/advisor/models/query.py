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
    context: ConversationContext | None = None  # previous turn's memory (1.2.0, ADR-014)


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
    intent: Literal["replace", "find", "status", "question", "compare", "other"] = "replace"
    part_numbers: list[str] = []
    category: Category | None = None
    requirements: list[TechnicalRequirement] = []
    # Follow-ups: requirement keys or values the customer no longer needs ("ya no necesito IPsec").
    remove: list[str] = []
    needs_clarification: bool = False
    clarification_question: str | None = None

    @model_validator(mode="after")
    def _clarification_has_question(self) -> ParsedQuery:
        if self.needs_clarification and not self.clarification_question:
            raise ValueError("needs_clarification requires clarification_question")
        return self


class ConversationContext(Contract):
    """What the agent remembers between turns. The UI sends back the context of the last answer;
    the agent itself is stateless."""

    original_part_number: str | None = None
    category: Category | None = None
    requirements: list[TechnicalRequirement] = []  # customer requirements accumulated so far
    recommended: list[str] = []  # last recommended part numbers, best first ("la más barata")
    asked_key: str | None = None  # spec key of the last clarification question
    turn: int = Field(default=0, ge=0)


CustomerQuery.model_rebuild()
