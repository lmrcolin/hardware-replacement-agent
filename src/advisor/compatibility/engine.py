"""Deterministic compatibility contracts. No LLM, no retrieval, no network."""

from __future__ import annotations

from collections.abc import Sequence

from advisor.models import CompatibilityResult, ParsedQuery, Product, TechnicalRequirement


def derive_requirements(original: Product, query: ParsedQuery) -> list[TechnicalRequirement]:
    """Query requirements + critical specs of the original (spec_registry). B-16."""
    raise NotImplementedError("B-16 compatibility.derive_requirements")


def evaluate(
    original: Product, candidate: Product, requirements: Sequence[TechnicalRequirement]
) -> CompatibilityResult:
    """Apply compat_rules.yaml; critical FAIL ⇒ INCOMPATIBLE, critical MISSING ⇒ UNKNOWN. B-15."""
    raise NotImplementedError("B-15 compatibility.evaluate")
