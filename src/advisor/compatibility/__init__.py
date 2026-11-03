"""Deterministic compatibility engine driven by config/compat_rules.yaml."""

from advisor.compatibility.engine import derive_requirements, evaluate
from advisor.compatibility.rules import RuleDefinition, RuleSet, load_rules

__all__ = ["RuleDefinition", "RuleSet", "derive_requirements", "evaluate", "load_rules"]
