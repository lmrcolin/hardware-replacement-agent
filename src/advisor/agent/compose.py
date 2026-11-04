"""COMPOSE (deterministic draft from structured data) and VERIFY (no invented figures)."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal

from advisor.models import (
    CommercialStatus,
    CompatibilityLevel,
    CompatibilityResult,
    Product,
    Recommendation,
    Relaxation,
    RuleOutcome,
    Severity,
)

LEVEL_ES = {
    CompatibilityLevel.COMPATIBLE: "compatible",
    CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS: "compatible con condiciones",
    CompatibilityLevel.UNKNOWN: "compatibilidad NO confirmada (faltan datos críticos)",
    CompatibilityLevel.INCOMPATIBLE: "incompatible",
}
STATUS_ES = {
    CommercialStatus.ACTIVE: "ACTIVE (disponible)",
    CommercialStatus.DISCONTINUED: "DISCONTINUED (descontinuado)",
    CommercialStatus.EOL: "EOL (fin de vida)",
    CommercialStatus.NRND: "NRND (no recomendado para nuevos diseños)",
}
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_PART_LIKE = re.compile(
    r"\b[A-Z][A-Z0-9]*\d[A-Z0-9]*(?:-[A-Z0-9]+)+\b|\b[A-Z]{2,}\d{3,}[A-Z0-9]*\b"
)


def money(value: Decimal | None) -> str:
    return f"{value:,.2f} USD" if value is not None else "sin precio"


def describe_status(product: Product) -> str:
    c = product.commercial
    if c is None:
        return f"{product.part_number}: sin información comercial en el catálogo."
    text = f"{product.part_number} ({c.description}, {c.manufacturer}) está {STATUS_ES[c.status]}"
    if c.discontinued_on:
        text += f" desde {c.discontinued_on.isoformat()}"
    if c.last_buy_on:
        text += f"; última compra {c.last_buy_on.isoformat()}"
    if c.status is CommercialStatus.ACTIVE:
        text += f"; precio {money(c.price_usd)}, {c.stock_units} unidades en inventario"
    elif c.stock_units:
        text += f"; quedan {c.stock_units} unidades (sin precio de venta vigente)"
    return text + "."


def _recommendation_line(rec: Recommendation) -> str:
    c = rec.commercial
    line = (
        f"{rec.rank}. {rec.product.part_number} — {c.description} ({c.manufacturer}): "
        f"{LEVEL_ES[rec.compatibility.level]}; {money(c.price_usd)}; {c.stock_units} unidades."
    )
    if rec.compatibility.conditions:
        line += " Condiciones: " + "; ".join(rec.compatibility.conditions) + "."
    return line


def fail_reasons(result: CompatibilityResult, limit: int = 2) -> list[str]:
    """Why a candidate was rejected: critical failures first."""
    fails = [r for r in result.rule_results if r.outcome is RuleOutcome.FAIL]
    critical = [r.message for r in fails if r.severity is Severity.CRITICAL]
    return (critical or [r.message for r in fails])[:limit]


def _price_note(recommendations: Sequence[Recommendation]) -> str | None:
    """Cheapest viable option when it is not already the first one (price never decides fit)."""
    priced = [r for r in recommendations if r.commercial.price_usd is not None]
    if len(priced) < 2 or recommendations[0].commercial.price_usd is None:
        return None
    cheapest = min(priced, key=lambda r: r.commercial.price_usd or Decimal(0))
    if cheapest is recommendations[0]:
        return None
    # Only catalog figures: a computed difference would not be traceable to a source (VERIFY).
    return (
        f"La opción más económica es {cheapest.product.part_number} "
        f"({money(cheapest.commercial.price_usd)}); el orden lo decide la compatibilidad, "
        "no el precio."
    )


def draft_message(
    original: Product | None,
    recommendations: Sequence[Recommendation],
    risky: Sequence[Recommendation],
    blocked_successors: Mapping[str, CompatibilityResult],
    unverified: Sequence[Recommendation] = (),
    rejected: Sequence[tuple[str, str, Sequence[str]]] = (),
    relaxations: Sequence[Relaxation] = (),
) -> str:
    """Deterministic answer. ``rejected`` = (part number, description, reasons) of discarded
    candidates, shown when nothing is recommended so the customer sees why."""
    lines: list[str] = []
    active = (
        original is not None
        and original.commercial is not None
        and original.commercial.status is CommercialStatus.ACTIVE
    )
    if original is not None:
        lines.append(describe_status(original))
    if active:
        lines.append("Está disponible: no necesita sustituto.")
    if recommendations:
        if active:
            header = "Alternativas compatibles en el catálogo:"
        elif original:
            header = "Sustitutos activos recomendados:"
        else:
            header = "Productos activos que cumplen la consulta:"
        lines.append(header)
        lines.extend(_recommendation_line(r) for r in recommendations)
        note = _price_note(recommendations)
        if note:
            lines.append(note)
    elif not active:
        lines.append(
            "No hay un sustituto ACTIVE compatible en el catálogo con la evidencia disponible."
        )
    if rejected and not recommendations and not active:
        lines.append("Candidatos evaluados y descartados:")
        lines.extend(
            f"- {part} — {description}: {'; '.join(reasons)}."
            for part, description, reasons in rejected
        )
    if relaxations:
        lines.append(
            "Alternativas si puedes prescindir de un requisito (no cumplen todo lo pedido):"
        )
        for relaxation in relaxations:
            req, rec = relaxation.dropped, relaxation.option
            unit = "" if not req.unit or req.unit == "count" else f" {req.unit}"
            what = f"{req.key} = {req.value}{unit}" if req.value != "*" else req.key
            lines.append(f"- Sin {what}: " + _recommendation_line(rec).split(". ", 1)[1])
    if risky:
        lines.append("Opciones con riesgo (NRND, sin precio de venta vigente):")
        lines.extend(_recommendation_line(r) for r in risky)
    if unverified:
        lines.append(
            "Posibles, pero sin datos suficientes para confirmar la compatibilidad "
            "(requieren validación de un experto):"
        )
        for rec in unverified:
            lines.append(
                f"- {rec.product.part_number} — {rec.commercial.description}: sin datos de "
                f"{', '.join(rec.compatibility.missing) or 'requisitos críticos'}."
            )
    for successor, result in blocked_successors.items():
        reasons = fail_reasons(result)
        lines.append(
            f"El datasheet indica {successor} como sucesor, pero no es un reemplazo directo: "
            + "; ".join(reasons)
            + "."
        )
    return "\n".join(lines)


def _numbers(text: str) -> set[str]:
    out: set[str] = set()
    for raw in _NUMBER.findall(text):
        value = raw.replace(",", "").rstrip(".")
        out.add(value)
        if "." in value:
            out.add(value.rstrip("0").rstrip("."))
        if value.isdigit():  # "01" in 2025-08-01 is the same figure as "1 de agosto"
            out.add(value.lstrip("0") or "0")
    return out


def unverified_tokens(text: str, draft: str, known_parts: Iterable[str]) -> list[str]:
    """Numbers and part-number-like tokens in ``text`` that do not come from the draft/catalog."""
    allowed_numbers = _numbers(draft)
    allowed_parts = set(known_parts) | set(_PART_LIKE.findall(draft))
    bad = [n for n in _numbers(text) if n not in allowed_numbers]
    bad += [p for p in _PART_LIKE.findall(text) if p not in allowed_parts]
    return sorted(set(bad))
