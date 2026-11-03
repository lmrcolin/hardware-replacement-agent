"""Deterministic compatibility engine. No LLM, no retrieval, no network.

A candidate is judged requirement by requirement against its own extracted specs. Missing data is
reported as MISSING, never as a match; similarity plays no role here.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from functools import lru_cache

from advisor.config import REPO_ROOT, get_settings
from advisor.extraction import SpecDefinition, SpecRegistry, load_spec_registry
from advisor.extraction.values import parse_number
from advisor.models import (
    CompatibilityLevel,
    CompatibilityResult,
    Operator,
    ParsedQuery,
    Priority,
    Product,
    ProductSpecification,
    RequirementOrigin,
    RuleOutcome,
    RuleResult,
    Severity,
    SpecValue,
    TechnicalRequirement,
)

ANY = "*"  # HAS "*" = the candidate declares at least one value for the key
FF_KEYS = {"form_factor", "package", "socket", "connector"}
ELEC_KEYS = {
    "voltage", "supply_voltage", "input_voltage", "output_voltage", "output_current", "tdp",
    "power_delivery",
}  # fmt: skip
SEVERITY = {
    Priority.MUST: Severity.CRITICAL,
    Priority.SHOULD: Severity.MAJOR,
    Priority.NICE: Severity.MINOR,
}
WEIGHT = {Severity.CRITICAL: 3, Severity.MAJOR: 2, Severity.MINOR: 1}
OUTCOME_SCORE = {
    RuleOutcome.PASS: 1.0, RuleOutcome.CONDITIONAL: 0.7, RuleOutcome.MISSING: 0.3,
    RuleOutcome.FAIL: 0.0,
}  # fmt: skip


@lru_cache(maxsize=1)
def default_registry() -> SpecRegistry:
    path = get_settings().paths.spec_registry
    return load_spec_registry(path if path.is_absolute() else REPO_ROOT / path)


def base_key(key: str) -> str:
    return re.sub(r"_(min|max)$", "", key)


# ---------------------------------------------------------------- requirement derivation (B-16)


def _derived(spec: ProductSpecification, definition: SpecDefinition) -> list[TechnicalRequirement]:
    priority = Priority.MUST if definition.critical else Priority.SHOULD
    origin = RequirementOrigin.ORIGINAL_SPEC
    value = spec.value
    if value is None:
        return []
    compare = definition.comparison

    def req(op: Operator, v: SpecValue) -> TechnicalRequirement:
        return TechnicalRequirement(key=spec.key, operator=op, value=v, unit=spec.unit,
                                    priority=priority, origin=origin)  # fmt: skip

    if definition.type == "range":  # candidate range must contain the original's
        return [req(Operator.LTE if spec.key.endswith("_min") else Operator.GTE, value)]
    if definition.type == "number":
        return [req(Operator.LTE if compare == "lte" else Operator.GTE, value)]
    if definition.type == "list" and isinstance(value, list):
        if compare == "intersects":
            return [req(Operator.IN, value)]
        return [req(Operator.HAS, item) for item in value]
    return [req(Operator.EQ, value)]


def derive_requirements(
    original: Product, query: ParsedQuery, *, registry: SpecRegistry | None = None
) -> list[TechnicalRequirement]:
    """Query requirements first; then the original's specs (critical → MUST, others → SHOULD).

    A spec already constrained by the query is not derived again (list items are deduplicated
    item by item, so the query's "IPsec" does not hide the original's other offloads).
    """
    registry = registry or default_registry()
    definitions = registry.for_category(original.category)
    requirements = list(query.requirements)
    query_keys = {r.key for r in query.requirements}
    query_items = {(r.key, str(r.value).casefold()) for r in query.requirements}
    for spec in original.specifications:
        definition = definitions.get(base_key(spec.key))
        if definition is None or not definition.derive:
            continue
        for req in _derived(spec, definition):
            if req.operator is Operator.HAS:
                if (req.key, str(req.value).casefold()) in query_items:
                    continue
            elif req.key in query_keys:
                continue
            requirements.append(req)
    return requirements


# ---------------------------------------------------------------- comparisons


def _norm(value: object) -> str:
    return re.sub(r"[\s_-]+", "", str(value)).casefold()


def _as_list(value: SpecValue) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else [str(value)]


def _interface(required: str, candidate: str) -> tuple[RuleOutcome, str]:
    pcie = r"PCIe (\d)\.0(?: x(\d+))?"
    r_p, c_p = re.fullmatch(pcie, required), re.fullmatch(pcie, candidate)
    if r_p and c_p:
        r_gen, c_gen = int(r_p.group(1)), int(c_p.group(1))
        r_lanes, c_lanes = r_p.group(2), c_p.group(2)
        if r_lanes and c_lanes and int(c_lanes) > int(r_lanes):
            return RuleOutcome.FAIL, f"requiere ranura x{c_lanes}; el original usa x{r_lanes}"
        if r_lanes and c_lanes and int(c_lanes) < int(r_lanes):
            text = f"usa x{c_lanes} en lugar de x{r_lanes}: menor ancho de banda"
            return RuleOutcome.CONDITIONAL, text
        if c_gen > r_gen:
            text = f"{candidate} es retrocompatible con ranuras PCIe {r_gen}.0 (opera a {r_gen}.0)"
            return RuleOutcome.CONDITIONAL, text
        if c_gen < r_gen:
            return RuleOutcome.CONDITIONAL, f"{candidate}: menos ancho de banda que {required}"
        return RuleOutcome.PASS, f"{candidate} = {required}"
    usb = r"USB (\d\.\d)"
    r_u, c_u = re.fullmatch(usb, required), re.fullmatch(usb, candidate)
    if r_u and c_u:
        r_v, c_v = float(r_u.group(1)), float(c_u.group(1))
        if c_v == r_v:
            return RuleOutcome.PASS, f"{candidate} = {required}"
        if c_v > r_v:
            return (
                RuleOutcome.CONDITIONAL,
                f"{candidate} funciona en puertos {required} a esa velocidad",
            )
        return RuleOutcome.CONDITIONAL, f"{candidate} es más lento que {required}"
    if _norm(required) == _norm(candidate):
        return RuleOutcome.PASS, f"{candidate} = {required}"
    return RuleOutcome.FAIL, f"interfaz {candidate} distinta de {required}"


def _rule_id(key: str, op: Operator, definition: SpecDefinition | None) -> str:
    base = base_key(key)
    if base in FF_KEYS:
        return "R-FF"
    if base in ELEC_KEYS:
        return "R-ELEC"
    if definition and definition.comparison == "interface":
        return "R-IFACE"
    if op in (Operator.HAS, Operator.IN):
        return "R-MUST-PROTO"
    if op in (Operator.GTE, Operator.LTE):
        return "R-NUM-GTE"
    return "R-SPEC"


def _compare(
    req: TechnicalRequirement, cand: ProductSpecification, definition: SpecDefinition | None
) -> tuple[RuleOutcome, str, str | None]:
    """(outcome, message, rule override)."""
    key = req.key
    unit = "" if (req.unit or cand.unit) == "count" else (req.unit or cand.unit or "")
    value = cand.value
    assert value is not None
    if req.operator in (Operator.GTE, Operator.LTE):
        if not isinstance(value, int | float) or isinstance(value, bool):
            return RuleOutcome.MISSING, f"{key}: valor no numérico ({value})", "R-MISSING"
        converted: float | None = float(value)
        if req.unit and cand.unit and req.unit != cand.unit:
            converted = parse_number(f"{value} {cand.unit}", req.unit)
        if converted is None:
            text = f"{key}: unidades incompatibles ({cand.unit} vs {req.unit})"
            return RuleOutcome.MISSING, text, "R-MISSING"
        cand_v = converted
        assert isinstance(req.value, int | float)
        required = float(req.value)
        ok = cand_v >= required if req.operator is Operator.GTE else cand_v <= required
        symbol = "≥" if req.operator is Operator.GTE else "≤"
        shown = f"{value} {unit}".strip(), f"{req.value} {unit}".strip()
        if not ok:
            return RuleOutcome.FAIL, f"{key}: {shown[0]} no cumple {symbol} {shown[1]}", None
        if (
            definition is not None
            and definition.upgrade_condition
            and req.operator is Operator.GTE
            and cand_v > required
        ):
            text = definition.upgrade_condition.format(
                original=req.value, candidate=value, unit=unit
            )
            return RuleOutcome.CONDITIONAL, text, "R-UPGRADE"
        return RuleOutcome.PASS, f"{key}: {shown[0]} {symbol} {shown[1]}", None
    if req.operator is Operator.HAS:
        items = {v.casefold() for v in _as_list(value)}
        ok = bool(items) if req.value == ANY else str(req.value).casefold() in items
        what = f"soporte ({', '.join(_as_list(value))})" if req.value == ANY else req.value
        verb = "declara" if ok else "no declara"
        return (RuleOutcome.PASS if ok else RuleOutcome.FAIL), f"{key}: {verb} {what}", None
    if req.operator is Operator.IN:
        wanted = {_norm(v) for v in _as_list(req.value)}
        shared = [v for v in _as_list(value) if _norm(v) in wanted]
        if shared:
            return RuleOutcome.PASS, f"{key}: comparte {', '.join(shared)}", None
        return RuleOutcome.FAIL, f"{key}: {value} sin coincidencia con {req.value}", None
    # EQ
    if definition is not None and definition.comparison == "interface":
        outcome, text = _interface(str(req.value), str(value))
        return outcome, f"{key}: {text}", None
    if _norm(value) == _norm(req.value):
        return RuleOutcome.PASS, f"{key}: {value} = {req.value}", None
    return RuleOutcome.FAIL, f"{key}: {value} ≠ {req.value}", None


# ---------------------------------------------------------------- evaluation (B-15)


def _level(results: Sequence[RuleResult]) -> CompatibilityLevel:
    critical = [r for r in results if r.severity is Severity.CRITICAL]
    if any(r.outcome is RuleOutcome.FAIL for r in critical):
        return CompatibilityLevel.INCOMPATIBLE
    if any(r.outcome is RuleOutcome.MISSING for r in critical):
        return CompatibilityLevel.UNKNOWN
    if any(r.outcome is RuleOutcome.CONDITIONAL for r in results) or any(
        r.severity is Severity.MAJOR and r.outcome in (RuleOutcome.FAIL, RuleOutcome.MISSING)
        for r in results
    ):
        return CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS
    return CompatibilityLevel.COMPATIBLE


def _score(results: Sequence[RuleResult]) -> float:
    total = sum(WEIGHT[r.severity] for r in results)
    if not total:
        return 0.0
    return round(sum(WEIGHT[r.severity] * OUTCOME_SCORE[r.outcome] for r in results) / total, 4)


def _coverage(results: Sequence[RuleResult]) -> float:
    musts = [r for r in results if r.requirement and r.requirement.priority is Priority.MUST]
    if not musts:
        return 1.0
    ok = sum(r.outcome in (RuleOutcome.PASS, RuleOutcome.CONDITIONAL) for r in musts)
    return round(ok / len(musts), 4)


def _spec_map(product: Product) -> dict[str, ProductSpecification]:
    return {s.key: s for s in product.specifications if s.value is not None}


def evaluate(
    original: Product,
    candidate: Product,
    requirements: Sequence[TechnicalRequirement],
    *,
    registry: SpecRegistry | None = None,
) -> CompatibilityResult:
    """Apply the rules; critical FAIL ⇒ INCOMPATIBLE, critical MISSING ⇒ UNKNOWN."""
    registry = registry or default_registry()
    definitions = registry.for_category(candidate.category)
    same_category = original.category is candidate.category
    results = [
        RuleResult(
            rule_id="R-CAT",
            severity=Severity.CRITICAL,
            outcome=RuleOutcome.PASS if same_category else RuleOutcome.FAIL,
            message=f"categoría {candidate.category} {'=' if same_category else '≠'} "
            f"{original.category}",
            original_value=original.category.value,
            candidate_value=candidate.category.value,
        )
    ]
    if same_category:
        cand_specs, orig_specs = _spec_map(candidate), _spec_map(original)
        for req in requirements:
            severity = SEVERITY[req.priority]
            definition = definitions.get(base_key(req.key))
            orig_ev = orig_specs[req.key].evidence if req.key in orig_specs else []
            spec = cand_specs.get(req.key)
            if spec is None:
                results.append(
                    RuleResult(
                        rule_id="R-MISSING",
                        severity=severity,
                        outcome=RuleOutcome.MISSING,
                        message=f"{req.key}: el datasheet de {candidate.part_number} no lo declara",
                        requirement=req,
                        original_value=req.value,
                        evidence=orig_ev,
                    )
                )
                continue
            outcome, message, rule = _compare(req, spec, definition)
            results.append(
                RuleResult(
                    rule_id=rule or _rule_id(req.key, req.operator, definition),
                    severity=severity,
                    outcome=outcome,
                    message=message,
                    requirement=req,
                    original_value=req.value,
                    candidate_value=spec.value,
                    evidence=list(spec.evidence) + list(orig_ev),
                )
            )
    conditions = [
        r.message
        for r in results
        if r.outcome is RuleOutcome.CONDITIONAL
        or (r.severity is Severity.MAJOR and r.outcome is RuleOutcome.FAIL)
    ]
    conditions += [
        f"Verificar {r.requirement.key} (no declarado en el datasheet)"
        for r in results
        if r.severity is Severity.MAJOR and r.outcome is RuleOutcome.MISSING and r.requirement
    ]
    return CompatibilityResult(
        original_part_number=original.part_number,
        candidate_part_number=candidate.part_number,
        level=_level(results),
        rule_results=results,
        coverage=_coverage(results) if same_category else 0.0,
        score=_score(results) if same_category else 0.0,
        conditions=conditions,
        missing=[
            r.requirement.key for r in results if r.outcome is RuleOutcome.MISSING and r.requirement
        ],
    )
