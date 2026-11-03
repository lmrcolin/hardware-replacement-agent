"""Streamlit UI: chat over the real AdvisorAgent (artifacts or in-memory build); mock selectable."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from components.render import response_view
from mock_agent import MockAdvisorAgent

from advisor.agent import Advisor
from advisor.models import CustomerQuery
from advisor.pipeline import BuiltArtifacts, build_agent, load_or_build

REAL, MOCK = "Real (catálogo + datasheets)", "Simulado (fixtures)"
EXAMPLES = {
    "Caso oficial (Intel E810)": (
        "Necesito una tarjeta de red 100 Gigabit Ethernet con soporte RDMA y offload de IPsec. "
        "Usábamos la Intel E810 pero ya no la encuentro"
    ),
    "DAQ descontinuada": "Necesito reemplazar la USB-2627",
    "GPU NRND (sucesor no compatible)": "Necesito reemplazar la A100",
    "Búsqueda por requisitos": "Busco una GPU de 80GB",
    "Part number con errata": "Reemplazo para la E81O-CQDA2",
    "Consulta vaga": "Busco un microcontrolador barato",
}


@st.cache_resource(show_spinner="Cargando catálogo, datasheets y grafo…")
def get_artifacts() -> BuiltArtifacts:
    return load_or_build()


@st.cache_resource
def get_agent(kind: str) -> Advisor:
    return MockAdvisorAgent() if kind == MOCK else build_agent(artifacts=get_artifacts())


st.set_page_config(page_title="Emerson Replacement Advisor", layout="wide")
st.title("Emerson Replacement Advisor")
st.caption(
    "Sustitutos para piezas descontinuadas · el catálogo es la fuente de verdad · "
    "compatibilidad decidida por reglas deterministas con evidencia"
)

history = st.session_state.setdefault("history", [])

with st.sidebar:
    kind = st.radio("Agente", [REAL, MOCK])
    st.markdown("**Ejemplos**")
    for label, text in EXAMPLES.items():
        if st.button(label, use_container_width=True):
            st.session_state["pending"] = text
    if st.button("Limpiar conversación", type="secondary"):
        history.clear()
    agent = get_agent(kind)
    trace = getattr(agent, "last_trace", [])
    if trace:
        st.markdown("**Pasos del último análisis**")
        st.caption(" → ".join(step.value for step in trace))

names = get_artifacts().document_names if kind == REAL else {}
prompt = st.chat_input("Describe la pieza a reemplazar o lo que necesitas")
prompt = prompt or st.session_state.pop("pending", None)
if prompt:
    response = agent.answer(CustomerQuery(text=prompt.strip()))
    history.append((prompt, response))

if not history:
    st.info("Escribe una consulta o elige un ejemplo en la barra lateral.")
for question, response in history:
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        response_view(response, names)
        st.caption(f"Redacción: {response.llm_provider} · contrato {response.contract_version}")
