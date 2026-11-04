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
    Evidence,
    Product,
    Recommendation,
    RecommendationResponse,
    RuleOutcome,
    TechnicalRequirement,
)
from components.images import image_html
from components.theme import level_badge, status_badge

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
    "PLAN": "Planear qué herramientas usar",
    "RELAX": "Negociar requisitos",
    "ANSWER": "Responder con los datasheets",
    "COMPARE": "Comparar productos",
}
TOOL_LABEL = {
    "lookup_part": "Identificar la pieza",
    "find_substitutes": "Buscar y validar sustitutos",
    "search_catalog": "Buscar en el catálogo por requisitos",
    "relax_requirements": "Negociar requisitos",
    "ask_datasheets": "Consultar datasheets",
    "compare": "Comparar productos",
    "ask_customer": "Preguntar al cliente",
    "finish": "Responder",
}


def _decider(name: str) -> str:
    if name.startswith("rules"):
        return "reglas" + name[5:]
    labels = {"databricks": "Llama 3.3", "ollama": "Ollama", "template": "plantillas",
              "claude": "Claude", "rules": "reglas"}  # fmt: skip
    return labels.get(name, name)


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
    """A quiet, collapsible line: what the agent did, who planned it, and every internal step."""
    nlu, nlg = providers(response)
    llm = _decider(nlu) if nlu == nlg else f"{_decider(nlu)} → {_decider(nlg)}"
    calls = [c for c in response.tool_calls if c.tool != "finish"]
    planner = next((c.decided_by for c in calls if not c.decided_by.startswith("rules")), "rules")
    count = f"{len(calls)} acciones" if calls else f"{len(steps)} pasos"
    with st.expander(f"Cómo lo resolvió el agente · {count} · plan: {_decider(planner)}"):
        if calls:
            thought = next((c.thought for c in response.tool_calls if c.thought), None)
            if thought:
                st.caption(f"Plan propuesto por {_decider(planner)}: “{thought}”")
            items = "".join(
                f"<li><b>{escape(TOOL_LABEL.get(c.tool, c.tool))}</b>"
                f'<span class="step-key">{escape(_decider(c.decided_by))}</span>'
                f'<div class="step-detail">{escape(c.summary)}</div></li>'
                for c in calls
            )
            _html(f'<ol class="steps">{items}</ol>')
        st.caption(f"Modelo de lenguaje: {llm} · solo interpreta, planea y redacta.")
        items = "".join(
            f"<li><b>{escape(s.title)}</b>"
            f'<span class="step-key">{escape(s.key)}</span>'
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

OUTCOME_MARK = {
    RuleOutcome.PASS: ("ok", "✓ Cumple"),
    RuleOutcome.CONDITIONAL: ("cond", "◐ Con condición"),
    RuleOutcome.FAIL: ("fail", "✕ No cumple"),
    RuleOutcome.MISSING: ("miss", "— Sin dato"),
}


def thumb_html(product: Product) -> str:
    return f'<div class="thumb">{image_html(product)}</div>'


def card_head_html(product: Product, eyebrow: str, badge_html: str, detail: str) -> str:
    return (
        f'<div class="card-head">{thumb_html(product)}<div class="who">'
        f'<div class="eyebrow">{escape(eyebrow)}</div>'
        f'<div class="pn">{escape(product.part_number)}</div>'
        f'<div class="desc">{escape(detail)}</div></div>{badge_html}</div>'
    )


def original_card(product: Product, *, key: str = "original") -> None:
    c = product.commercial
    with st.container(key=f"card-{key}"):
        if c is None:
            _html(card_head_html(product, "Pieza original", "", "Sin información comercial."))
            return
        since = c.discontinued_on.isoformat() if c.discontinued_on else None
        last = c.last_buy_on.isoformat() if c.last_buy_on else None
        bits = [f"{c.description} · {c.manufacturer}"]
        if since:
            bits.append(f"desde {since}")
        if last:
            bits.append(f"última compra {last}")
        _html(card_head_html(product, "Pieza original", status_badge(c.status), " · ".join(bits)))


def comparison_html(rec: Recommendation) -> str:
    """Original (or required) vs candidate per evaluated rule, straight from the engine."""
    rows = []
    for rule in rec.compatibility.rule_results:
        req = rule.requirement
        unit = (req.unit if req and req.unit not in (None, "count") else "") or ""
        css, mark = OUTCOME_MARK[rule.outcome]
        rows.append(
            f'<tr><td class="key">{escape(req.key if req else "categoría")}</td>'
            f"<td>{escape(_fmt(rule.original_value))} {escape(unit)}</td>"
            f"<td>{escape(_fmt(rule.candidate_value))} {escape(unit)}</td>"
            f'<td class="{css}">{mark}</td></tr>'
        )
    return (
        '<table class="specs"><thead><tr><th>Especificación</th><th>Original / requerido</th>'
        "<th>Sustituto</th><th>Resultado</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def comparison_table(rec: Recommendation) -> pd.DataFrame:
    """Same comparison as a table (kept for exports and tests)."""
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
    """Catalog facts in tabular figures (the catalog is the source of truth)."""
    facts = [
        ("Precio (catálogo)", price_text(c)),
        ("Stock", stock_text(c)),
        ("Requisitos obligatorios", f"{coverage:.0%} cubiertos"),
    ]
    return (
        '<div class="facts">'
        + "".join(f"<div><small>{escape(k)}</small><b>{escape(v)}</b></div>" for k, v in facts)
        + "</div>"
    )


def citations_html(evidence: Sequence[Evidence], names: dict[str, str]) -> str:
    return "".join(
        f'<div class="cite"><b>{escape(names.get(ev.document_id, ev.document_id[:12]))} · '
        f"página {ev.page}</b>“{escape(ev.quote)}”</div>"
        for ev in evidence
    )


def recommendation_card(rec: Recommendation, names: dict[str, str], *, key: str) -> None:
    c = rec.commercial
    with st.container(key=f"card-{key}"):
        st.subheader(f"{rec.rank}. {rec.product.part_number}", anchor=False)
        _html(
            card_head_html(
                rec.product, f"Opción {rec.rank}", level_badge(rec.compatibility.level),
                f"{c.description} · {c.manufacturer}",
            )
        )  # fmt: skip
        _html(facts_html(c, rec.compatibility.coverage))
        why = f'<div class="why">{escape(rec.rationale)}'
        if rec.compatibility.conditions:
            why += (
                "<ul>"
                + "".join(f"<li>{escape(x)}</li>" for x in rec.compatibility.conditions)
                + "</ul>"
            )
        _html(why + "</div>")
        with st.expander("Comparación de especificaciones"):
            _html(comparison_html(rec))
        if rec.evidence:
            with st.expander(f"Evidencia de los datasheets · {len(rec.evidence)}"):
                _html(citations_html(rec.evidence, names))


def sales_potential(recommendations: Sequence[Recommendation]) -> tuple[int, Decimal]:
    """Units in stock and their catalog value (price * stock) across the recommended options."""
    units, value = 0, Decimal(0)
    for rec in recommendations:
        c = rec.commercial
        if c.price_usd is not None and c.stock_units:
            units += c.stock_units
            value += c.price_usd * c.stock_units
    return units, value


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


def _message_html(text: str) -> str:
    return (
        '<div class="answer-text">'
        + "<br>".join(escape(line) for line in text.split("\n"))
        + "</div>"
    )


def response_view(response: RecommendationResponse, names: dict[str, str], *, turn: int) -> None:
    """The agent's answer: its message first, then the structured result it is based on."""
    if response.is_synthetic:
        st.caption("Respuesta generada con datos sintéticos de prueba.")
    if response.clarification_question:
        # The agent may list what is for sale (vague query) before asking; show it.
        if "\n" in response.message:
            st.markdown(response.message.replace("\n", "  \n"))
        _html(f'<div class="ask">{escape(response.clarification_question)}</div>')
        return
    st.markdown(response.message.replace("\n", "  \n"))
    if response.original is not None:
        original_card(response.original, key=f"{turn}-original")
    if response.recommendations:
        for rec in response.recommendations:
            recommendation_card(rec, names, key=f"{turn}-rec-{rec.rank}")
        units, value = sales_potential(response.recommendations)
        if units:
            _html(
                f'<div class="impact">Impacto comercial: {units:,} unidades disponibles en estas '
                f"opciones · {value:,.2f} USD a precio de catálogo.</div>"
            )
    open_caveats = not response.recommendations
    if response.risky_options:
        with st.expander(
            f"Opciones con riesgo (NRND) · {len(response.risky_options)}", expanded=open_caveats
        ):
            st.caption(
                "Siguen en inventario pero no se recomiendan para diseños nuevos; "
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
    if response.relaxations:
        with st.expander(
            f"Si puedes prescindir de un requisito · {len(response.relaxations)}",
            expanded=not response.recommendations,
        ):
            st.caption(
                "No cumplen todo lo que pediste: cada opción se vuelve compatible solo si se quita "
                "el requisito indicado. Confírmalo antes de comprar."
            )
            for i, relaxation in enumerate(response.relaxations):
                st.markdown(f"**Sin {_requirement(relaxation.dropped)}**")
                recommendation_card(relaxation.option, names, key=f"{turn}-relax-{i}")
    if response.citations:
        with st.expander(f"Fuentes citadas · {len(response.citations)}"):
            _html(citations_html(response.citations, names))
    with st.expander("Notas y escalar a un experto"):
        if response.warnings:
            _html(
                '<div class="notes">' + "<br>".join(escape(w) for w in response.warnings) + "</div>"
            )
        st.caption("Copia este resumen para un experto (no se envía nada automáticamente).")
        st.code(expert_summary(response), language=None)
