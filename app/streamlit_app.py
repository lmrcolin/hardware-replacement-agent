"""Streamlit UI: conversational front end for the replacement agent (real AdvisorAgent or mock).

Each turn shows what the agent did (its trace, explained), its answer and the structured result
behind it. When the agent asks for clarification, the customer's reply is combined with the
previous question before it is sent, because the agent itself is stateless per query.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from html import escape
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from components.images import image_html
from components.render import (
    clarification_options,
    parts_to_replace,
    reasoning,
    reasoning_view,
    response_view,
)
from components.theme import CSS
from mock_agent import MockAdvisorAgent

from advisor.agent import Advisor, AdvisorAgent
from advisor.models import CommercialStatus, CustomerQuery, RecommendationResponse
from advisor.pipeline import (
    BuiltArtifacts,
    build_agent,
    evidence_sources,
    load_or_build,
    retrieval_status,
)

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


@dataclass
class Turn:
    shown: str  # what the customer typed or clicked
    sent: str  # what was sent to the agent (shown + context when answering a clarification)
    response: RecommendationResponse
    trace: list[str]
    found_by: str | None


@st.cache_resource(show_spinner="Cargando catálogo, datasheets y grafo…")
def get_artifacts() -> BuiltArtifacts:
    return load_or_build()


@st.cache_resource
def get_agent(kind: str) -> Advisor:
    return MockAdvisorAgent() if kind == MOCK else build_agent(artifacts=get_artifacts())


@st.cache_resource(show_spinner="Comprobando la búsqueda documental…")
def get_retrieval_status(kind: str) -> str:
    agent = get_agent(kind)
    return retrieval_status(agent.retriever) if isinstance(agent, AdvisorAgent) else "fixtures"


st.set_page_config(page_title="Emerson Replacement Advisor · Agente", page_icon="🤖", layout="wide")
st.html(CSS)
state = st.session_state
turns: list[Turn] = state.setdefault("turns", [])


def ask(text: str | None = None, *, follow_up: bool = True) -> None:
    """Callback: queue a message. Answers to a clarification carry the previous question."""
    text = (text if text is not None else state.get("chat") or "").strip()
    if not text:
        return
    sent = text
    if follow_up and turns and turns[-1].response.clarification_question:
        sent = f"{turns[-1].sent} {text}"
    state["pending"] = (text, sent)


def new_conversation() -> None:
    turns.clear()
    st.query_params.clear()


# Shareable conversations: ?k=<consulta> opens the chat with that first message (once).
# Only on a fresh session: later reruns keep ?k= in the URL and must not re-send it.
if "k" in st.query_params and not state.get("url_used") and not turns:
    ask(st.query_params["k"], follow_up=False)
state["url_used"] = True

# ---------------------------------------------------------------- sidebar: the agent
with st.sidebar:
    st.markdown(
        '<div class="agent-id"><div class="avatar">AI</div><div><b>Agente de reemplazo</b>'
        "<br><small>Emerson Replacement Advisor</small></div></div>",
        unsafe_allow_html=True,
    )
    kind = st.radio("Fuente de datos", [REAL, MOCK], key="agent")
    agent = get_agent(kind)
    st.button("Nueva conversación", on_click=new_conversation, icon=":material/add_comment:")

    st.markdown("**Herramientas del agente**")
    if isinstance(agent, AdvisorAgent):
        artifacts = get_artifacts()
        chain = " → ".join(c.name for c in agent.llm_chain)
        tools = [
            ("Catálogo comercial", f"{len(artifacts.catalog)} piezas · fuente de verdad"),
            ("Grafo de conocimiento", f"{artifacts.graph.number_of_nodes()} nodos"),
            ("Búsqueda documental", get_retrieval_status(kind)),
            ("Motor de compatibilidad", "reglas deterministas · sin LLM"),
            ("Modelo de lenguaje", f"{chain} · solo interpreta y redacta"),
            ("Datos", artifacts.source),
        ]
    else:
        tools = [("Datos", "fixtures sintéticos (agente simulado)")]
    st.markdown(
        "".join(
            f'<div class="tool"><b>{escape(name)}</b><span>{escape(value)}</span></div>'
            for name, value in tools
        ),
        unsafe_allow_html=True,
    )
    with st.expander("Cómo decide"):
        st.markdown(
            "- Interpreta la consulta y la valida contra el registro de specs.\n"
            "- Identifica la pieza en el grafo; si no está seguro, **pregunta**.\n"
            "- Estado, precio y stock salen **solo del catálogo**.\n"
            "- La compatibilidad la deciden **reglas deterministas** con evidencia; "
            "un dato faltante nunca cuenta como compatible.\n"
            "- Solo recomienda piezas **ACTIVE**; NRND va como opción con riesgo.\n"
            "- El LLM no decide: interpreta y redacta, y sus cifras se verifican."
        )

names = get_artifacts().document_names if kind == REAL else {}
known_parts = [p.part_number for p in get_artifacts().products] if kind == REAL else []

# ---------------------------------------------------------------- run the agent
pending = state.pop("pending", None)
if pending:
    shown, sent = pending
    with st.spinner("El agente está analizando: interpreta, consulta catálogo y grafo, valida…"):
        response = agent.answer(CustomerQuery(text=sent))
    trace = [str(step) for step in getattr(agent, "last_trace", [])]
    found_by = evidence_sources(agent.retriever) if isinstance(agent, AdvisorAgent) else None
    turns.append(Turn(shown, sent, response, trace, found_by))
    st.query_params["k"] = sent

# ---------------------------------------------------------------- conversation
st.markdown(
    '<div class="chat-head"><b>Agente de reemplazo de componentes</b>'
    "<span>Sustitutos ACTIVE para piezas DISCONTINUED, EOL o NRND, con compatibilidad "
    "verificada por reglas y evidencia de los datasheets</span></div>",
    unsafe_allow_html=True,
)

with st.chat_message("assistant"):
    st.markdown(
        "Hola. Dime qué pieza necesitas reemplazar (part number) o qué requisitos debe cumplir. "
        "Busco sustitutos en el catálogo, valido la compatibilidad con reglas y te muestro la "
        "evidencia; si me falta un dato, te pregunto."
    )
    if not turns:
        st.caption("Prueba con un ejemplo:")
        cols = st.columns(3)
        for i, (label, text) in enumerate(EXAMPLES.items()):
            cols[i % 3].button(
                label,
                key=f"ex-{i}",
                on_click=ask,
                args=(text,),
                kwargs={"follow_up": False},
                width="stretch",
            )
        if kind == REAL:
            risky = parts_to_replace(get_artifacts().products)
            st.caption(
                f"O elige una de las {len(risky)} piezas del catálogo que necesitan reemplazo:"
            )
            cols = st.columns(6)
            for i, product in enumerate(risky):
                with cols[i % 6], st.container(key=f"part-{product.part_number}"):
                    st.markdown(
                        image_html(product, css_class="pimg pimg-mini"), unsafe_allow_html=True
                    )
                    assert product.commercial is not None
                    status = product.commercial.status
                    color = "orange" if status is CommercialStatus.NRND else "red"
                    st.markdown(f":{color}-badge[{status.value}]")
                    st.button(
                        product.part_number,
                        key=f"pick-{product.part_number}",
                        on_click=ask,
                        args=(f"Necesito reemplazar la {product.part_number}",),
                        kwargs={"follow_up": False},
                        width="stretch",
                    )

for i, turn in enumerate(turns):
    with st.chat_message("user"):
        st.write(turn.shown)
        if turn.sent != turn.shown:
            st.caption(f"Enviado al agente con el contexto anterior: “{turn.sent}”")
    with st.chat_message("assistant"):
        retrieval = get_retrieval_status(kind) if kind == REAL else None
        steps = reasoning(turn.response, turn.trace, retrieval=retrieval, found_by=turn.found_by)
        if steps:
            reasoning_view(steps, turn.response)
        response_view(turn.response, names, turn=i)
        options = clarification_options(turn.response.clarification_question, known_parts)
        if options and i == len(turns) - 1:
            st.caption("Responde escribiendo o elige una opción:")
            cols = st.columns(4)
            for col, pn in zip(cols, options, strict=False):
                col.button(pn, key=f"opt-{i}-{pn}", on_click=ask, args=(pn,), width="stretch")
        st.caption(
            f"Redacción: {turn.response.llm_provider} · contrato {turn.response.contract_version}"
        )

placeholder = (
    "Responde a la pregunta del agente…"
    if turns and turns[-1].response.clarification_question
    else "Describe la pieza a reemplazar o lo que necesitas"
)
st.chat_input(placeholder, key="chat", on_submit=ask)
