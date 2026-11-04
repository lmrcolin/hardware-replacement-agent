"""Presentation components for the agent chat.

They only read RecommendationResponse and the agent's own trace; no business logic here.
Levels, ranking and sections come from the agent untouched.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
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
    TechnicalRequirement,
)
from components.images import image_html

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
INTENT_LABEL = {
    "replace": "reemplazar una pieza",
    "find": "buscar por requisitos",
    "status": "consultar estado",
    "other": "otra",
}
OPERATOR_LABEL = {"GTE": "≥", "LTE": "≤", "EQ": "=", "IN": "∈", "HAS": "incluye"}

# What each AgentStep means, in the customer's language.
STEP_TITLE = {
    "PARSE": "Interpretar la consulta",
    "RESOLVE": "Identificar la pieza en el grafo",
    "CLARIFY": "Pedir una aclaración",
    "STATUS": "Consultar el catálogo",
    "DISCOVER": "Buscar candidatos",
    "VALIDATE": "Validar compatibilidad con reglas",
    "RANK": "Ordenar resultados",
    "COMPOSE": "Redactar la respuesta",
    "VERIFY": "Verificar cifras del texto",
}


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


def price_text(c: CommercialInformation) -> str:
    """Price only for ACTIVE parts (catalog rule)."""
    if c.status is not CommercialStatus.ACTIVE or c.price_usd is None:
        return "Sin precio de venta vigente"
    return f"US$ {Decimal(c.price_usd):,.2f}"


def stock_text(c: CommercialInformation) -> str:
    if c.stock_units is None:
        return "Stock no informado"
    if c.stock_units == 0:
        return "Sin stock"
    return f"{c.stock_units:,} unidades"


def all_options(response: RecommendationResponse) -> list[Recommendation]:
    return response.recommendations + response.risky_options + response.unverified_options


def parts_to_replace(products: Iterable[Product]) -> list[Product]:
    """Catalog parts in DISCONTINUED/EOL/NRND, most urgent first."""
    rows = [
        (REPLACE.index(p.commercial.status), p.category.value, p.part_number, p)
        for p in products
        if p.commercial is not None and p.commercial.status in REPLACE
    ]
    return [row[-1] for row in sorted(rows, key=lambda r: r[:3])]


# ---------------------------------------------------------------- agent reasoning


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    detail: str


def _requirement(req: TechnicalRequirement) -> str:
    unit = "" if not req.unit or req.unit == "count" else f" {req.unit}"
    op = OPERATOR_LABEL.get(req.operator.value, req.operator.value)
    return f"{req.key} {op} {_fmt(req.value)}{unit}"


def providers(response: RecommendationResponse) -> tuple[str, str]:
    """(NLU provider, NLG provider) as recorded by the agent in ``llm_provider``."""
    names = [p for p in response.llm_provider.split("+") if p]
    return (names[0], names[-1]) if names else ("—", "—")


def reasoning(
    response: RecommendationResponse,
    trace: Sequence[str],
    *,
    retrieval: str | None = None,
    found_by: str | None = None,
) -> list[Step]:
    """One human-readable line per step the agent actually ran, built from its own outputs."""
    nlu, nlg = providers(response)
    parsed, original = response.parsed_query, response.original
    steps: list[Step] = []
    for key in trace:
        detail = ""
        if key == "PARSE" and parsed is not None:
            reqs = "; ".join(_requirement(r) for r in parsed.requirements) or "ninguno"
            category = CATEGORY_LABEL[parsed.category] if parsed.category else "—"
            detail = (
                f"Modelo: {nlu} · intención: {INTENT_LABEL.get(parsed.intent, parsed.intent)} · "
                f"categoría: {category} · part numbers: {', '.join(parsed.part_numbers) or '—'} · "
                f"requisitos: {reqs}."
            )
        elif key == "RESOLVE":
            if original is not None:
                detail = f"Coincidencia segura en el catálogo: {original.part_number}."
            elif response.clarification_question:
                detail = "Sin coincidencia segura con un part number del catálogo."
            else:
                detail = "Sin part number en la consulta: se busca por requisitos."
        elif key == "CLARIFY":
            detail = response.clarification_question or "Falta un dato para continuar."
        elif key == "STATUS" and original is not None and original.commercial is not None:
            c = original.commercial
            since = f" desde {c.discontinued_on.isoformat()}" if c.discontinued_on else ""
            detail = (
                f"{original.part_number}: {c.status.value}{since}. "
                "El catálogo es la fuente de verdad para estado, precio y stock."
            )
        elif key == "DISCOVER":
            detail = "Misma categoría, vecinos del grafo de conocimiento y búsqueda documental"
            detail += f" ({retrieval})" if retrieval else ""
            detail += f"; evidencia hallada por: {found_by}." if found_by else "."
        elif key == "VALIDATE":
            detail = (
                f"Reglas deterministas: {len(response.recommendations)} recomendado(s), "
                f"{len(response.risky_options)} con riesgo (NRND), "
                f"{len(response.unverified_options)} sin datos suficientes. Los incompatibles se "
                "descartan y un dato faltante nunca cuenta como compatible."
            )
        elif key == "RANK":
            detail = (
                "Nivel de compatibilidad, luego cobertura de requisitos obligatorios, "
                "luego puntuación; "
                "el stock solo desempata."
            )
        elif key == "COMPOSE":
            detail = f"Modelo: {nlg}. Solo redacta con cifras de la respuesta estructurada."
        elif key == "VERIFY":
            replaced = any("datos no verificados" in w for w in response.warnings)
            detail = (
                "El texto generado traía datos no verificados: se muestra la versión verificada."
                if replaced
                else "Cada cifra y part number del texto coincide con los datos estructurados."
            )
        steps.append(Step(key, STEP_TITLE.get(key, key), detail))
    return steps


def reasoning_view(steps: Sequence[Step], response: RecommendationResponse) -> None:
    nlu, nlg = providers(response)
    llm = nlu if nlu == nlg else f"{nlu} → {nlg}"
    label = f"Razonamiento del agente · {len(steps)} pasos · LLM: {llm}"
    with st.status(label, state="complete", expanded=False):
        items = "".join(
            f'<li><span class="step-key">{escape(s.key)}</span> <b>{escape(s.title)}</b>'
            f'<div class="step-detail">{escape(s.detail)}</div></li>'
            for s in steps
        )
        _html(f'<ol class="steps">{items}</ol>')


def clarification_options(question: str | None, known: Iterable[str]) -> list[str]:
    """Catalog part numbers the agent offered in its clarification question, in order of mention."""
    if not question:
        return []
    hits: dict[str, int] = {}
    for pn in sorted(set(known), key=len, reverse=True):
        match = re.search(rf"(?<![\w-]){re.escape(pn)}(?![\w-])", question)
        if match and not any(pn in other for other in hits):
            hits[pn] = match.start()
    return sorted(hits, key=hits.__getitem__)


# ---------------------------------------------------------------- result cards


def original_card(product: Product, *, key: str = "original") -> None:
    c = product.commercial
    with st.container(key=f"card-{key}"):
        left, right = st.columns([1, 5], gap="small")
        left.markdown(image_html(product), unsafe_allow_html=True)
        with right:
            st.markdown(f"**Pieza original: {product.part_number}**")
            if c is None:
                st.caption("Sin información comercial en el catálogo.")
                return
            st.markdown(f"{STATUS_BADGE[c.status]} · {c.description} · {c.manufacturer}")
            since = c.discontinued_on.isoformat() if c.discontinued_on else "—"
            last = c.last_buy_on.isoformat() if c.last_buy_on else "—"
            label = "NRND desde" if c.status is CommercialStatus.NRND else "Descontinuada desde"
            st.caption(
                f"{CATEGORY_LABEL[c.category]} · {label}: {since} · última compra: {last} · "
                f"stock: {stock_text(c)}"
            )


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


def facts_html(c: CommercialInformation, coverage: float) -> str:
    """Catalog facts as wrapping chips (never squeezed into a narrow column)."""
    chips = [
        ("Precio (catálogo)", price_text(c)),
        ("Stock", stock_text(c)),
        ("Requisitos obligatorios", f"{coverage:.0%} cubiertos"),
        ("Estado", c.status.value),
    ]
    return (
        '<div class="facts">'
        + "".join(f"<span><small>{escape(k)}</small><b>{escape(v)}</b></span>" for k, v in chips)
        + "</div>"
    )


def recommendation_card(rec: Recommendation, names: dict[str, str], *, key: str) -> None:
    c = rec.commercial
    with st.container(key=f"card-{key}"):
        left, body = st.columns([1, 5], gap="small")
        left.markdown(image_html(rec.product), unsafe_allow_html=True)
        with body:
            st.subheader(f"{rec.rank}. {rec.product.part_number}", anchor=False)
            st.markdown(
                f"{LEVEL_BADGE[rec.compatibility.level]} · {c.description} · {c.manufacturer}"
            )
            _html(facts_html(c, rec.compatibility.coverage))
        st.write(rec.rationale)
        if rec.compatibility.conditions:
            st.markdown(
                "**Condiciones**\n" + "\n".join(f"- {x}" for x in rec.compatibility.conditions)
            )
        compare, evidence = st.tabs(
            ["Comparación de especificaciones", f"Evidencia ({len(rec.evidence)} citas)"]
        )
        with compare:
            st.dataframe(comparison_table(rec), hide_index=True, width="stretch")
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


def response_view(response: RecommendationResponse, names: dict[str, str], *, turn: int) -> None:
    """The agent's answer: its message first, then the structured result it is based on."""
    if response.is_synthetic:
        st.warning("Respuesta generada con datos sintéticos de prueba.")
    if response.clarification_question:
        st.info(response.clarification_question)
        return
    st.markdown(response.message.replace("\n", "  \n"))
    if response.original is not None:
        original_card(response.original, key=f"{turn}-original")
    if response.recommendations:
        title = "Sustitutos recomendados" if response.original else "Productos que cumplen"
        st.markdown(f"##### {title}")
        for rec in response.recommendations:
            recommendation_card(rec, names, key=f"{turn}-rec-{rec.rank}")
    open_caveats = not response.recommendations
    if response.risky_options:
        with st.expander(
            f"Opciones con riesgo (NRND) · {len(response.risky_options)}", expanded=open_caveats
        ):
            st.caption(
                "Siguen en inventario pero no se recomiendan para nuevos diseños; "
                "sin precio de venta vigente."
            )
            for rec in response.risky_options:
                recommendation_card(rec, names, key=f"{turn}-risk-{rec.rank}")
    if response.unverified_options:
        with st.expander(
            f"Posibles, sin datos suficientes · {len(response.unverified_options)}",
            expanded=open_caveats,
        ):
            st.caption(
                "Su datasheet no declara algún dato crítico: la compatibilidad no está "
                "confirmada y requiere validación de un experto. No se presentan como recomendados."
            )
            for rec in response.unverified_options:
                recommendation_card(rec, names, key=f"{turn}-unv-{rec.rank}")
    for warning in response.warnings:
        st.caption(f"Aviso: {warning}")
    with st.expander("Escalar a un experto"):
        st.caption(
            "Copia este resumen y compártelo con el experto (no se envía nada automáticamente)."
        )
        st.code(expert_summary(response), language=None)
