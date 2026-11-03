"""Presentation components. They only read RecommendationResponse; no business logic here."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from advisor.models import (
    CommercialStatus,
    CompatibilityLevel,
    Product,
    Recommendation,
    RecommendationResponse,
    RuleOutcome,
)

LEVEL_BADGE = {
    CompatibilityLevel.COMPATIBLE: ":green-badge[Compatible]",
    CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS: ":orange-badge[Compatible con condiciones]",
    CompatibilityLevel.UNKNOWN: ":gray-badge[No confirmada: faltan datos críticos]",
    CompatibilityLevel.INCOMPATIBLE: ":red-badge[Incompatible]",
}
STATUS_BADGE = {
    CommercialStatus.ACTIVE: ":green-badge[ACTIVE]",
    CommercialStatus.NRND: ":orange-badge[NRND · no recomendado para nuevos diseños]",
    CommercialStatus.DISCONTINUED: ":red-badge[DISCONTINUED]",
    CommercialStatus.EOL: ":red-badge[EOL · fin de vida]",
}
OUTCOME_LABEL = {
    RuleOutcome.PASS: "✓ cumple",
    RuleOutcome.CONDITIONAL: "◐ con condición",
    RuleOutcome.FAIL: "✗ no cumple",
    RuleOutcome.MISSING: "? sin dato",
}


def _fmt(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) or "—"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def original_card(product: Product) -> None:
    c = product.commercial
    with st.container(border=True):
        st.markdown(f"#### Pieza original: {product.part_number}")
        if c is None:
            st.caption("Sin información comercial en el catálogo.")
            return
        st.markdown(f"{STATUS_BADGE[c.status]} · {c.description} · {c.manufacturer} · {c.category}")
        cols = st.columns(4)
        cols[0].metric(
            "Descontinuada desde", c.discontinued_on.isoformat() if c.discontinued_on else "—"
        )
        cols[1].metric("Última compra", c.last_buy_on.isoformat() if c.last_buy_on else "—")
        cols[2].metric("Stock", c.stock_units if c.stock_units is not None else "—")
        # Price is only shown for ACTIVE parts (catalog rule).
        price = (
            f"{c.price_usd:,.2f}" if c.status is CommercialStatus.ACTIVE and c.price_usd else "—"
        )
        cols[3].metric("Precio USD", price)


def comparison_table(rec: Recommendation) -> pd.DataFrame:
    """Original vs candidate per evaluated requirement, straight from the engine's RuleResults."""
    rows = []
    for rule in rec.compatibility.rule_results:
        req = rule.requirement
        rows.append(
            {
                "Requisito": req.key if req else "categoría",
                "Original / requerido": _fmt(rule.original_value),
                "Sustituto": _fmt(rule.candidate_value),
                "Unidad": (req.unit if req and req.unit != "count" else "") or "",
                "Resultado": OUTCOME_LABEL[rule.outcome],
                "Regla": rule.rule_id,
                "Prioridad": req.priority.value if req else "MUST",
            }
        )
    return pd.DataFrame(rows)


def recommendation_card(rec: Recommendation, names: dict[str, str]) -> None:
    c = rec.commercial
    with st.container(border=True):
        st.subheader(f"{rec.rank}. {rec.product.part_number}")
        st.markdown(f"{LEVEL_BADGE[rec.compatibility.level]} · {c.description} · {c.manufacturer}")
        cols = st.columns(4)
        cols[0].metric("Precio USD", f"{c.price_usd:,.2f}" if c.price_usd is not None else "—")
        cols[1].metric("Stock", c.stock_units if c.stock_units is not None else "—")
        cols[2].metric("Requisitos obligatorios", f"{rec.compatibility.coverage:.0%}")
        cols[3].metric("Estado", c.status.value)
        st.write(rec.rationale)
        if rec.compatibility.conditions:
            st.markdown(
                "**Condiciones**\n" + "\n".join(f"- {x}" for x in rec.compatibility.conditions)
            )
        with st.expander("Comparación de especificaciones"):
            st.dataframe(comparison_table(rec), hide_index=True, use_container_width=True)
        with st.expander(f"Evidencia ({len(rec.evidence)} citas)"):
            for ev in rec.evidence:
                source = names.get(ev.document_id, ev.document_id[:12])
                st.caption(f"{source} · p.{ev.page} — “{ev.quote}”")


def expert_summary(response: RecommendationResponse) -> str:
    """Plain-text summary for escalation to a human expert (copy only; nothing is sent)."""
    lines = [f"Consulta: {response.query.text}"]
    if response.original and response.original.commercial:
        c = response.original.commercial
        lines.append(f"Original: {response.original.part_number} ({c.description}) — {c.status}")
    for rec in response.recommendations + response.risky_options + response.unverified_options:
        lines.append(
            f"- {rec.product.part_number}: {rec.compatibility.level}; "
            f"condiciones: {'; '.join(rec.compatibility.conditions) or 'ninguna'}; "
            f"sin datos: {', '.join(rec.compatibility.missing) or 'ninguno'}"
        )
    if not response.recommendations:
        lines.append("- Sin sustituto ACTIVE confirmado.")
    lines += [f"Aviso: {w}" for w in response.warnings]
    return "\n".join(lines)


def response_view(response: RecommendationResponse, names: dict[str, str]) -> None:
    if response.is_synthetic:
        st.warning("Respuesta generada con datos sintéticos de prueba.")
    if response.clarification_question:
        st.info(response.clarification_question)
        return
    if response.original is not None:
        original_card(response.original)
    st.markdown(response.message.replace("\n", "  \n"))
    if response.recommendations:
        st.markdown(
            "### Sustitutos recomendados" if response.original else "### Productos que cumplen"
        )
        for rec in response.recommendations:
            recommendation_card(rec, names)
    if response.risky_options:
        st.markdown("### Opciones con riesgo (NRND)")
        st.caption(
            "Siguen en inventario pero no se recomiendan para nuevos diseños; "
            "sin precio de venta vigente."
        )
        for rec in response.risky_options:
            recommendation_card(rec, names)
    if response.unverified_options:
        st.markdown("### Posibles, sin datos suficientes")
        st.caption(
            "Su datasheet no declara algún dato crítico: la compatibilidad no está confirmada y "
            "requiere validación de un experto. No se presentan como recomendados."
        )
        for rec in response.unverified_options:
            recommendation_card(rec, names)
    for warning in response.warnings:
        st.caption(f"Aviso: {warning}")
    with st.expander("Escalar a un experto"):
        st.caption(
            "Copia este resumen y compártelo con el experto (no se envía nada automáticamente)."
        )
        st.code(expert_summary(response), language=None)
