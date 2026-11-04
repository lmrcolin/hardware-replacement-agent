"""Agent tool trace (contract 1.2.0, ADR-014)."""

from __future__ import annotations

from pydantic import Field

from advisor.models.base import Contract


class ToolCall(Contract):
    """One action of the agent: which deterministic tool ran, who chose it and what it found."""

    tool: str = Field(min_length=1)
    arguments: dict[str, str] = {}
    summary: str
    decided_by: str = "rules"  # LLM provider name, or "rules" (deterministic planner)
    thought: str | None = None  # the planner's stated reason (LLM), shown as-is
