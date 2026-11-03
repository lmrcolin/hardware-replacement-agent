"""Presentation components. They only read RecommendationResponse; no business logic here.

Marketplace layout: product cards with a "buy box" column (price, stock, status), tabs for the
spec comparison and the cited evidence. Order and sections come from the engine unchanged:
filters only hide cards, they never re-rank or move a card between sections.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from html import escape

import pandas as pd
import streamlit as st

from advisor.models import (
    Category,
    CommercialInformation,
    CommercialStatus,
    CompatibilityLevel,
    Product,
    Recommendation,
    RecommendationResponse,
    RuleOutcome,
)
from components.images import image_html

LEVEL_BADGE = {
    CompatibilityLevel.COMPATIBLE: ":green-badge[Compatible]",
    CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS: ":orange-badge[Compatible con condiciones]",
    CompatibilityLevel.UNKNOWN: ":gray-badge[No confirmada: faltan datos críticos]",
    CompatibilityLevel.INCOMPATIBLE: ":red-badge[Incompatible]",
}
LEVEL_LABEL = {
    CompatibilityLevel.COMPATIBLE: "Compatible",
    CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS: "Con condiciones",
    CompatibilityLevel.UNKNOWN: "Sin datos suficientes",
    CompatibilityLevel.INCOMPATIBLE: "Incompatible",
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
CATEGORY_LABEL = {
    Category.CPU: "CPU",
    Category.DAQ: "Adquisición de datos",
    Category.FPGA: "FPGA",
    Category.GPU: "GPU",
    Category.MEMORY: "Memoria",
    Category.MICROCONTROLLER: "Microcontrolador",
    Category.NETWORK: "Red",
    Category.POWER: "Energía",
    Category.SENSOR: "Sensor",
    Category.STORAGE: "Almacenamiento",
}
REPLACE = (CommercialStatus.DISCONTINUED, CommercialStatus.EOL, CommercialStatus.NRND)


def _html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def _fmt(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) or "—"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def price_html(c: CommercialInformation) -> str:
    """Price only for ACTIVE parts (catalog rule); cents as superscript."""
    if c.status is not CommercialStatus.ACTIVE or c.price_usd is None:
        return '<div class="no-price">Sin precio de venta vigente</div>'
    units, cents = f"{Decimal(c.price_usd):,.2f}".split(".")
    return f'<div class="price"><sup>US$</sup>{units}<sup>{cents}</sup></div>'


def stock_html(c: CommercialInformation) -> str:
    if c.stock_units is None:
        return '<div class="muted">Stock no informado en el catálogo</div>'
    if c.stock_units == 0:
        return '<div class="stock-out">Sin stock</div>'
    return f'<div class="stock-in">En stock: {c.stock_units:,} unidades</div>'


# ---------------------------------------------------------------- landing


def replacement_tiles(
    products: Iterable[Product], on_pick: Callable[[str], None], *, per_row: int = 4
) -> None:
    """Catalog parts that need a replacement (DISCONTINUED/EOL/NRND) as clickable tiles."""
    parts = sorted(
        (
            (REPLACE.index(p.commercial.status), p.category.value, p.part_number, p)
            for p in products
            if p.commercial and p.commercial.status in REPLACE
        ),
        key=lambda row: row[:3],
    )
    if not parts:
        return
    _html('<div class="band">Piezas del catálogo que necesitan reemplazo</div>')
    st.caption(f"{len(parts)} piezas DISCONTINUED, EOL o NRND · elige una para buscar sustituto")
    for start in range(0, len(parts), per_row):
        cols = st.columns(per_row)
        for col, (*_, product) in zip(cols, parts[start : start + per_row], strict=False):
            c = product.commercial
            assert c is not None
            with col, st.container(key=f"tile-{c.part_number}"):
                _html(image_html(product, css_class="pimg pimg-tile"))
                _html(
                    f'<span class="status-red">{c.status.value}</span> '
                    f'<span class="muted">· {escape(CATEGORY_LABEL[c.category])}</span>'
                )
                _html(
                    f"<b>{escape(c.part_number)}</b><br><span class='muted'>"
                    f"{escape(c.description)} · {escape(c.manufacturer)}</span>"
                )
                st.button(
                    "Buscar sustituto",
                    key=f"pick-{c.part_number}",
                    type="primary",
                    on_click=on_pick,
                    args=(f"Necesito reemplazar la {c.part_number}",),
                    use_container_width=True,
                )


# ---------------------------------------------------------------- results


@dataclass(frozen=True)
class Filters:
    """Display-only filters chosen in the left rail; empty means 'all'."""

    category: Category | None = None
    levels: frozenset[CompatibilityLevel] = field(default_factory=frozenset)
    manufacturers: frozenset[str] = field(default_factory=frozenset)

    def keep(self, rec: Recommendation) -> bool:
        return (
            (self.category is None or rec.commercial.category is self.category)
            and (not self.levels or rec.compatibility.level in self.levels)
            and (not self.manufacturers or rec.commercial.manufacturer in self.manufacturers)
        )


def all_options(response: RecommendationResponse) -> list[Recommendation]:
    return response.recommendations + response.risky_options + response.unverified_options


def original_card(product: Product) -> None:
    c = product.commercial
    with st.container(key="original"):
        left, mid, right = st.columns([1, 5, 2.2])
        left.markdown(image_html(product), unsafe_allow_html=True)
        with mid:
            st.markdown(f"#### Pieza original: {product.part_number}")
            if c is None:
                st.caption("Sin información comercial en el catálogo.")
                return
            st.markdown(f"{STATUS_BADGE[c.status]} · {c.description} · {c.manufacturer}")
            st.caption(f"Categoría: {CATEGORY_LABEL[c.category]}")
        with right:
            since = c.discontinued_on.isoformat() if c.discontinued_on else "—"
            last = c.last_buy_on.isoformat() if c.last_buy_on else "—"
            since_label = (
                "NRND desde" if c.status is CommercialStatus.NRND else "Descontinuada desde"
            )
            _html(
                f'<div class="muted">{since_label}</div><b>{since}</b>'
                f'<div class="muted" style="margin-top:6px">Última compra</div><b>{last}</b>'
            )
            _html(stock_html(c))


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


def recommendation_card(
    rec: Recommendation, names: dict[str, str], *, key: str, best: bool = False
) -> None:
    c = rec.commercial
    with st.container(key=f"card-{key}"):
        left, mid, right = st.columns([1, 4.6, 1.8])
        left.markdown(image_html(rec.product), unsafe_allow_html=True)
        with mid:
            if best:
                _html('<div class="choice">Mejor <span>compatibilidad</span></div>')
            st.subheader(f"{rec.rank}. {rec.product.part_number}", anchor=False)
            st.markdown(f"{c.description} · de **{c.manufacturer}**")
            st.markdown(LEVEL_BADGE[rec.compatibility.level])
            coverage = rec.compatibility.coverage
            _html(
                f'<div class="coverage"><div style="width:{coverage:.0%}"></div></div>'
                f'<div class="muted">Requisitos obligatorios cubiertos: {coverage:.0%}</div>'
            )
            st.write(rec.rationale)
            if rec.compatibility.conditions:
                st.markdown(
                    "**Condiciones**\n" + "\n".join(f"- {x}" for x in rec.compatibility.conditions)
                )
        with right:
            _html(price_html(c))
            _html(stock_html(c))
            st.markdown(STATUS_BADGE[c.status])
        compare, evidence = st.tabs(
            ["Comparación de especificaciones", f"Evidencia ({len(rec.evidence)} citas)"]
        )
        with compare:
            st.dataframe(comparison_table(rec), hide_index=True, use_container_width=True)
        with evidence:
            if not rec.evidence:
                st.caption("Sin citas para este candidato.")
            for ev in rec.evidence:
                source = names.get(ev.document_id, ev.document_id[:12])
                st.caption(f"{source} · p.{ev.page} — “{ev.quote}”")


def expert_summary(response: RecommendationResponse) -> str:
    """Plain-text summary for escalation to a human expert (copy only; nothing is sent)."""
    lines = [f"Consulta: {response.query.text}"]
    if response.original and response.original.commercial:
        c = response.original.commercial
        lines.append(f"Original: {response.original.part_number} ({c.description}) — {c.status}")
    for rec in all_options(response):
        lines.append(
            f"- {rec.product.part_number}: {rec.compatibility.level}; "
            f"condiciones: {'; '.join(rec.compatibility.conditions) or 'ninguna'}; "
            f"sin datos: {', '.join(rec.compatibility.missing) or 'ninguno'}"
        )
    if not response.recommendations:
        lines.append("- Sin sustituto ACTIVE confirmado.")
    lines += [f"Aviso: {w}" for w in response.warnings]
    return "\n".join(lines)


def _section(
    title: str,
    recs: list[Recommendation],
    names: dict[str, str],
    filters: Filters,
    *,
    key: str,
    note: str | None = None,
    note_class: str = "band-warn",
    best_first: bool = False,
) -> None:
    shown = [r for r in recs if filters.keep(r)]
    if not recs:
        return
    _html(f'<div class="band">{escape(title)}</div>')
    if note:
        _html(f'<div class="{note_class}">{escape(note)}</div>')
    if len(shown) < len(recs):
        st.caption(f"{len(recs) - len(shown)} de {len(recs)} ocultas por los filtros.")
    for rec in shown:
        best = best_first and rec is recs[0]
        recommendation_card(rec, names, key=f"{key}-{rec.rank}", best=best)


def response_view(
    response: RecommendationResponse, names: dict[str, str], filters: Filters | None = None
) -> None:
    filters = filters or Filters()
    if response.is_synthetic:
        st.warning("Respuesta generada con datos sintéticos de prueba.")
    if response.clarification_question:
        st.info(response.clarification_question)
        return
    if response.original is not None:
        original_card(response.original)
    with st.container(key="card-summary"):
        _html('<div class="muted">Resumen del asesor</div>')
        st.markdown(response.message.replace("\n", "  \n"))
    _section(
        "Sustitutos recomendados" if response.original else "Productos que cumplen",
        response.recommendations,
        names,
        filters,
        key="rec",
        best_first=True,
    )
    _section(
        "Opciones con riesgo (NRND)",
        response.risky_options,
        names,
        filters,
        key="risk",
        note="Siguen en inventario pero no se recomiendan para nuevos diseños; "
        "sin precio de venta vigente.",
    )
    _section(
        "Posibles, sin datos suficientes",
        response.unverified_options,
        names,
        filters,
        key="unv",
        note="Su datasheet no declara algún dato crítico: la compatibilidad no está confirmada y "
        "requiere validación de un experto. No se presentan como recomendados.",
        note_class="band-gray",
    )
    for warning in response.warnings:
        st.caption(f"Aviso: {warning}")
    with st.expander("Escalar a un experto"):
        st.caption(
            "Copia este resumen y compártelo con el experto (no se envía nada automáticamente)."
        )
        st.code(expert_summary(response), language=None)
