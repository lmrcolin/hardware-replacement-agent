"""Streamlit UI: real AdvisorAgent built in memory from data/raw (mock selectable)."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mock_agent import MockAdvisorAgent

from advisor.agent import Advisor
from advisor.models import (
    CompatibilityLevel,
    CustomerQuery,
    Recommendation,
    RecommendationResponse,
)
from advisor.pipeline import BuiltArtifacts, build_agent, build_in_memory

REAL, MOCK = "Real (catálogo + datasheets)", "Simulado (fixtures)"
EXAMPLES = {
    "Caso oficial (Intel E810)": (
        "Necesito una tarjeta de red 100 Gigabit Ethernet con soporte RDMA y offload de IPsec. "
        "Usábamos la Intel E810 pero ya no la encuentro"
    ),
    "DAQ descontinuada": "Necesito reemplazar la USB-2627",
    "GPU NRND": "Necesito reemplazar la A100",
    "Por requisitos": "Busco una GPU de 80GB",
    "Consulta vaga": "Busco un microcontrolador barato",
}
LEVEL_BADGE = {
    CompatibilityLevel.COMPATIBLE: ":green[Compatible]",
    CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS: ":orange[Compatible con condiciones]",
    CompatibilityLevel.UNKNOWN: ":gray[No confirmada: faltan datos]",
}


@st.cache_resource(show_spinner="Procesando catálogo y datasheets…")
def get_artifacts() -> BuiltArtifacts:
    return build_in_memory()


@st.cache_resource
def get_agent(kind: str) -> Advisor:
    return MockAdvisorAgent() if kind == MOCK else build_agent(artifacts=get_artifacts())


def render_recommendation(rec: Recommendation, names: dict[str, str]) -> None:
    c = rec.commercial
    level = LEVEL_BADGE.get(rec.compatibility.level, rec.compatibility.level.value)
    with st.container(border=True):
        st.subheader(f"{rec.rank}. {rec.product.part_number}")
        st.caption(f"{c.description} · {c.manufacturer} · {c.status}")
        cols = st.columns(4)
        cols[0].markdown(f"**Compatibilidad**  \n{level}")
        cols[1].metric("Precio USD", f"{c.price_usd:,.2f}" if c.price_usd is not None else "—")
        cols[2].metric("Stock", c.stock_units if c.stock_units is not None else "—")
        cols[3].metric("Requisitos obligatorios", f"{rec.compatibility.coverage:.0%}")
        st.write(rec.rationale)
        if rec.compatibility.conditions:
            st.markdown(
                "**Condiciones**\n" + "\n".join(f"- {x}" for x in rec.compatibility.conditions)
            )
        with st.expander("Detalle por requisito"):
            st.markdown("\n".join(f"- ✓ {x}" for x in rec.covered_requirements) or "—")
            if rec.uncovered_requirements:
                st.markdown("\n".join(f"- ✗ {x}" for x in rec.uncovered_requirements))
        with st.expander(f"Evidencia ({len(rec.evidence)} citas)"):
            for ev in rec.evidence:
                source = names.get(ev.document_id, ev.document_id[:12])
                st.caption(f"{source} · p.{ev.page} — “{ev.quote}”")


def render(response: RecommendationResponse, names: dict[str, str]) -> None:
    if response.is_synthetic:
        st.warning("Respuesta generada con datos sintéticos de prueba.")
    if response.clarification_question:
        st.info(response.clarification_question)
        return
    st.markdown(response.message.replace("\n", "  \n"))
    if response.recommendations:
        st.header("Sustitutos recomendados" if response.original else "Productos que cumplen")
        for rec in response.recommendations:
            render_recommendation(rec, names)
    if response.risky_options:
        st.header("Opciones con riesgo (NRND)")
        for rec in response.risky_options:
            render_recommendation(rec, names)
    for warning in response.warnings:
        st.caption(f"Aviso: {warning}")
    st.caption(f"Redacción: {response.llm_provider} · contrato {response.contract_version}")


st.set_page_config(page_title="Emerson Replacement Advisor", layout="wide")
st.title("Emerson Replacement Advisor")
st.caption(
    "Sustitutos para piezas descontinuadas · el catálogo es la fuente de verdad · "
    "decisiones deterministas"
)

with st.sidebar:
    kind = st.radio("Agente", [REAL, MOCK])
    example = st.selectbox("Ejemplos", list(EXAMPLES))

text = st.text_area(
    "Describe la pieza a reemplazar o lo que necesitas", value=EXAMPLES[example], height=100
)
if st.button("Buscar sustituto", type="primary") and text.strip():
    names = get_artifacts().document_names if kind == REAL else {}
    render(get_agent(kind).answer(CustomerQuery(text=text.strip())), names)
