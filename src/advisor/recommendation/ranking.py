"""Ranking: level > coverage > score; inventory only breaks ties."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import NamedTuple

from advisor.models import (
    COMPATIBILITY_ORDER,
    CommercialStatus,
    CompatibilityLevel,
    CompatibilityResult,
    Evidence,
    Priority,
    Product,
    Recommendation,
    RuleOutcome,
)

LEVEL_TEXT = {
    CompatibilityLevel.COMPATIBLE: "Compatible",
    CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS: "Compatible con condiciones",
    CompatibilityLevel.UNKNOWN: "Compatibilidad no confirmada (faltan datos críticos)",
}


class RankedOutput(NamedTuple):
    recommendations: list[Recommendation]  # ACTIVE only
    risky_options: list[Recommendation]  # NRND only


def _sort_key(result: CompatibilityResult, product: Product) -> tuple[int, float, float, int, str]:
    stock = product.commercial.stock_units if product.commercial else None
    return (
        COMPATIBILITY_ORDER.index(result.level),
        -result.coverage,
        -result.score,
        -(stock or 0),  # tie-breaker only
        product.part_number,
    )


def _evidence(result: CompatibilityResult) -> list[Evidence]:
    seen: set[tuple[str, int, str]] = set()
    out: list[Evidence] = []
    for rule in result.rule_results:
        for ev in rule.evidence:
            if (ev.document_id, ev.page, ev.quote) not in seen:
                seen.add((ev.document_id, ev.page, ev.quote))
                out.append(ev)
    return out


def _rationale(result: CompatibilityResult) -> str:
    musts = [
        r for r in result.rule_results if r.requirement and r.requirement.priority is Priority.MUST
    ]
    ok = sum(r.outcome in (RuleOutcome.PASS, RuleOutcome.CONDITIONAL) for r in musts)
    parts = [f"{LEVEL_TEXT[result.level]}: cumple {ok}/{len(musts)} requisitos obligatorios"]
    if result.conditions:
        parts.append(f"{len(result.conditions)} condición(es) de instalación o verificación")
    if result.missing:
        parts.append(f"sin datos de: {', '.join(result.missing)}")
    return "; ".join(parts) + "."


def _recommendation(rank: int, result: CompatibilityResult, product: Product) -> Recommendation:
    assert product.commercial is not None
    covered = [
        r.message for r in result.rule_results
        if r.requirement and r.outcome in (RuleOutcome.PASS, RuleOutcome.CONDITIONAL)
    ]  # fmt: skip
    uncovered = [
        r.message for r in result.rule_results
        if r.requirement and r.outcome in (RuleOutcome.FAIL, RuleOutcome.MISSING)
    ]  # fmt: skip
    return Recommendation(
        rank=rank,
        product=product,
        commercial=product.commercial,
        compatibility=result,
        covered_requirements=covered,
        uncovered_requirements=uncovered,
        rationale=_rationale(result),
        evidence=_evidence(result),
    )


def rank(results: Sequence[CompatibilityResult], products: Mapping[str, Product]) -> RankedOutput:
    """Drops INCOMPATIBLE and DISCONTINUED/EOL candidates; NRND goes to risky_options."""
    eligible: list[tuple[CompatibilityResult, Product]] = []
    for result in results:
        product = products.get(result.candidate_part_number)
        if (
            result.level is CompatibilityLevel.INCOMPATIBLE
            or product is None
            or product.commercial is None
            or product.commercial.status not in (CommercialStatus.ACTIVE, CommercialStatus.NRND)
        ):
            continue
        eligible.append((result, product))
    eligible.sort(key=lambda pair: _sort_key(*pair))

    def with_status(status: CommercialStatus) -> list[tuple[CompatibilityResult, Product]]:
        return [(r, p) for r, p in eligible if p.commercial and p.commercial.status is status]

    active, nrnd = with_status(CommercialStatus.ACTIVE), with_status(CommercialStatus.NRND)
    return RankedOutput(
        recommendations=[_recommendation(i, r, p) for i, (r, p) in enumerate(active, start=1)],
        risky_options=[_recommendation(i, r, p) for i, (r, p) in enumerate(nrnd, start=1)],
    )
