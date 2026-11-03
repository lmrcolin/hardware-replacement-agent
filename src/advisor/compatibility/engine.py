"""Deterministic compatibility engine. No LLM, no retrieval, no network."""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

from advisor.compatibility.checks import Check, compare
from advisor.compatibility.rules import RuleDefinition, RuleSet, load_rules
from advisor.config import REPO_ROOT, get_settings
from advisor.extraction.registry import SpecDefinition, SpecRegistry, load_spec_registry
from advisor.models import (
    CompatibilityLevel,
    CompatibilityResult,
    Operator,
    ParsedQuery,
    Priority,
    Product,
    ProductSpecification,
    RuleOutcome,
    RuleResult,
    Severity,
    TechnicalRequirement,
)

# Requirement keys routed to a specific rule (anything else falls back by operator).
FORM_FACTOR_KEYS = frozenset({"form_factor", "socket", "package", "connector"})
ELECTRICAL_KEYS = frozenset(
    {
        "tdp",
        "voltage",
        "supply_voltage",
        "supply_voltage_min",
        "supply_voltage_max",
        "input_voltage_min",
        "input_voltage_max",
        "output_voltage_min",
        "output_voltage_max",
        "output_current",
    }
)
# Higher capability that changes integration (optics, switch ports): conditional (R-UPGRADE).
UPGRADE_KEYS = frozenset({"port_speed"})

_FALLBACK_BY_OPERATOR = {
    Operator.GTE: "R-NUM-GTE",
    Operator.LTE: "R-NUM-GTE",
    Operator.EQ: "R-MUST-PROTO",
    Operator.IN: "R-MUST-PROTO",
    Operator.HAS: "R-MUST-PROTO",
}

_OUTCOME = {
    Check.PASS: RuleOutcome.PASS,
    Check.FAIL: RuleOutcome.FAIL,
    Check.MISSING: RuleOutcome.MISSING,
    Check.UPGRADE: RuleOutcome.CONDITIONAL,
}


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


@lru_cache(maxsize=1)
def _rules() -> RuleSet:
    return load_rules(_resolve(get_settings().paths.compat_rules))


@lru_cache(maxsize=1)
def _registry() -> SpecRegistry:
    return load_spec_registry(_resolve(get_settings().paths.spec_registry))


def _applies(rule: RuleDefinition, category: str) -> bool:
    return "*" in rule.applies_to or category in rule.applies_to


def _rule_for(requirement: TechnicalRequirement, category: str, rules: RuleSet) -> RuleDefinition:
    by_id = {r.id: r for r in rules.rules}
    preferred: list[str] = []
    if requirement.key in FORM_FACTOR_KEYS:
        preferred.append("R-FF")
    if requirement.key in ELECTRICAL_KEYS:
        preferred.append("R-ELEC")
    preferred.append(_FALLBACK_BY_OPERATOR[requirement.operator])
    for rule_id in preferred:
        rule = by_id.get(rule_id)
        if rule is not None and _applies(rule, category):
            return rule
    raise ValueError(f"no rule in compat_rules.yaml covers requirement {requirement.key!r}")


def _spec(product: Product, key: str) -> ProductSpecification | None:
    return next((s for s in product.specifications if s.key == key), None)


def _severity(
    rule: RuleDefinition, requirement: TechnicalRequirement, definition: SpecDefinition | None
) -> Severity:
    """Registry-critical specs and MUST requirements are judged as CRITICAL."""
    if requirement.priority is Priority.MUST or (definition is not None and definition.critical):
        return Severity.CRITICAL
    return rule.severity


def _unit_mismatch(
    requirement: TechnicalRequirement,
    spec: ProductSpecification | None,
    definition: SpecDefinition | None,
) -> bool:
    expected = requirement.unit or (definition.unit if definition else None)
    actual = spec.unit if spec else None
    return bool(expected and actual and expected != actual)


def _evaluate_requirement(
    requirement: TechnicalRequirement,
    original: Product,
    candidate: Product,
    rules: RuleSet,
    specs: dict[str, SpecDefinition],
) -> RuleResult:
    category = str(candidate.category)
    definition = specs.get(requirement.key)
    rule = _rule_for(requirement, category, rules)
    severity = _severity(rule, requirement, definition)
    cand_spec = _spec(candidate, requirement.key)
    orig_spec = _spec(original, requirement.key)
    cand_value = cand_spec.value if cand_spec else None
    common = {
        "requirement": requirement,
        "original_value": orig_spec.value if orig_spec else None,
        "candidate_value": cand_value,
        "evidence": list(cand_spec.evidence) if cand_spec else [],
    }

    if _unit_mismatch(requirement, cand_spec, definition):
        return RuleResult(
            rule_id="R-MISSING",
            severity=severity,
            outcome=RuleOutcome.MISSING,
            message=(
                f"{requirement.key}: unidad {cand_spec.unit if cand_spec else None} no comparable "
                f"con {requirement.unit or (definition.unit if definition else None)}"
            ),
            **common,
        )

    check = compare(requirement.operator, requirement.value, cand_value)
    if check is Check.MISSING:
        return RuleResult(
            rule_id="R-MISSING",
            severity=severity,
            outcome=RuleOutcome.MISSING,
            message=f"{requirement.key}: sin dato comparable en {candidate.part_number}",
            **common,
        )

    target = f"{requirement.operator} {requirement.value}"
    if check is Check.UPGRADE:
        return RuleResult(
            rule_id="R-UPGRADE",
            severity=Severity.MINOR,
            outcome=RuleOutcome.CONDITIONAL,
            message=(
                f"{requirement.key}: {cand_value} es una versión superior de {requirement.value}; "
                "verificar compatibilidad del slot/puerto y drivers"
            ),
            **common,
        )

    if (
        check is Check.PASS
        and requirement.key in UPGRADE_KEYS
        and requirement.operator is Operator.GTE
        and isinstance(cand_value, int | float)
        and float(cand_value) > float(requirement.value)  # type: ignore[arg-type]
    ):
        return RuleResult(
            rule_id="R-UPGRADE",
            severity=Severity.MINOR,
            outcome=RuleOutcome.CONDITIONAL,
            message=(
                f"{requirement.key}: {cand_value} supera {requirement.value}; "
                "verificar transceptores, cables y puertos del switch"
            ),
            **common,
        )

    verdict = "cumple" if check is Check.PASS else "no cumple"
    return RuleResult(
        rule_id=rule.id,
        severity=severity,
        outcome=_OUTCOME[check],
        message=f"{requirement.key}: {cand_value} {verdict} {target}",
        **common,
    )


def _level(results: Sequence[RuleResult]) -> CompatibilityLevel:
    critical = [r for r in results if r.severity is Severity.CRITICAL]
    if any(r.outcome is RuleOutcome.FAIL for r in critical):
        return CompatibilityLevel.INCOMPATIBLE
    if any(r.outcome is RuleOutcome.MISSING for r in critical):
        return CompatibilityLevel.UNKNOWN
    if any(r.outcome in (RuleOutcome.FAIL, RuleOutcome.CONDITIONAL) for r in results):
        return CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS
    return CompatibilityLevel.COMPATIBLE


def _score(results: Sequence[RuleResult]) -> float:
    """Share of rules satisfied (CONDITIONAL counts half). Never used to promote a level."""
    weights = {
        RuleOutcome.PASS: 1.0,
        RuleOutcome.CONDITIONAL: 0.5,
        RuleOutcome.MISSING: 0.0,
        RuleOutcome.FAIL: 0.0,
    }
    return sum(weights[r.outcome] for r in results) / len(results) if results else 0.0


def derive_requirements(original: Product, query: ParsedQuery) -> list[TechnicalRequirement]:
    """Query requirements + critical specs of the original (spec_registry). B-16."""
    raise NotImplementedError("B-16 compatibility.derive_requirements")


def evaluate(
    original: Product, candidate: Product, requirements: Sequence[TechnicalRequirement]
) -> CompatibilityResult:
    """Apply compat_rules.yaml; critical FAIL ⇒ INCOMPATIBLE, critical MISSING ⇒ UNKNOWN. B-15."""
    if original.part_number == candidate.part_number:
        raise ValueError(f"{original.part_number} cannot be evaluated as its own candidate")

    rules = _rules()
    category_rule = next(r for r in rules.rules if r.id == "R-CAT")
    same_category = original.category == candidate.category
    cat_result = RuleResult(
        rule_id="R-CAT",
        severity=category_rule.severity,
        outcome=RuleOutcome.PASS if same_category else RuleOutcome.FAIL,
        message=(
            f"categoría {candidate.category}"
            + (" coincide" if same_category else f" distinta de {original.category}")
        ),
    )
    if not same_category:
        return CompatibilityResult(
            original_part_number=original.part_number,
            candidate_part_number=candidate.part_number,
            level=CompatibilityLevel.INCOMPATIBLE,
            rule_results=[cat_result],
            coverage=0.0,
            score=0.0,
        )

    specs = _registry().for_category(candidate.category)
    req_results = [
        _evaluate_requirement(req, original, candidate, rules, specs) for req in requirements
    ]
    results = [cat_result, *req_results]

    musts = [
        (req, res)
        for req, res in zip(requirements, req_results, strict=True)
        if req.priority is Priority.MUST
    ]
    satisfied = sum(
        1 for _, res in musts if res.outcome in (RuleOutcome.PASS, RuleOutcome.CONDITIONAL)
    )
    return CompatibilityResult(
        original_part_number=original.part_number,
        candidate_part_number=candidate.part_number,
        level=_level(results),
        rule_results=results,
        coverage=satisfied / len(musts) if musts else 1.0,
        score=_score(results),
        conditions=[
            r.message
            for r in req_results
            if r.outcome is RuleOutcome.CONDITIONAL
            or (r.outcome is RuleOutcome.FAIL and r.severity is not Severity.CRITICAL)
        ],
        missing=[
            r.requirement.key
            for r in req_results
            if r.outcome is RuleOutcome.MISSING and r.requirement
        ],
    )
