"""Streamlit shell backed by MockAdvisorAgent. Final UI is B-21 (Dev3)."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mock_agent import MockAdvisorAgent

from advisor.agent import Advisor
from advisor.models import CustomerQuery, Recommendation

EXAMPLE = (
    "Necesito una tarjeta de red 100 Gigabit Ethernet con soporte RDMA y offload de IPsec. "
    "Usábamos la Intel E810 pero ya no la encuentro"
)


@st.cache_resource
def get_agent() -> Advisor:
    return MockAdvisorAgent()


def render_recommendation(rec: Recommendation) -> None:
    c = rec.commercial
    with st.container(border=True):
        st.subheader(f"{rec.rank}. {rec.product.part_number}")
        cols = st.columns(4)
        cols[0].metric("Compatibilidad", rec.compatibility.level.value)
        cols[1].metric("Precio USD", f"{c.price_usd:,.2f}" if c.price_usd is not None else "—")
        cols[2].metric("Stock", c.stock_units if c.stock_units is not None else "—")
        cols[3].metric("Cobertura", f"{rec.compatibility.coverage:.0%}")
        st.write(rec.rationale)
        if rec.compatibility.conditions:
            st.markdown("**Condiciones:** " + "; ".join(rec.compatibility.conditions))
        with st.expander("Evidencia"):
            for ev in rec.evidence:
                st.caption(f"{ev.document_id[:12]} · p.{ev.page} · {ev.quote}")


st.set_page_config(page_title="Emerson Replacement Advisor", layout="wide")
st.title("Emerson Replacement Advisor")
st.caption("Prototipo · agente simulado (MockAdvisorAgent) · datos sintéticos")

text = st.text_area("Describe la pieza a reemplazar", value=EXAMPLE, height=100)
if st.button("Buscar sustituto", type="primary") and text.strip():
    response = get_agent().answer(CustomerQuery(text=text.strip()))
    if response.is_synthetic:
        st.warning("Respuesta generada con datos sintéticos de prueba.")
    st.info(response.message)
    if response.clarification_question:
        st.write(response.clarification_question)
    for rec in response.recommendations:
        render_recommendation(rec)
    if response.risky_options:
        st.subheader("Opciones con riesgo (NRND)")
        for rec in response.risky_options:
            render_recommendation(rec)
    for warning in response.warnings:
        st.caption(f"Aviso: {warning}")
