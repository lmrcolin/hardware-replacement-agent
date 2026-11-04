"""Streamlit UI: chat widget for the replacement agent (real AdvisorAgent or mock).

Widget pattern: header with avatar, name, online status and settings menu; bot and customer
bubbles; quick-reply buttons; "was this helpful?" rating; input at the bottom; minimize button.
Each answer shows what the agent did (its trace, explained) and the structured result behind it.
The sidebar keeps the search history and the most searched topics (components/history.py).
When the agent asks for clarification, the customer's reply is combined with the previous
question before it is sent, because the agent itself is stateless per query.
"""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parent))

from components.history import (
    OUTCOME_LABEL,
    SearchLog,
    recent,
    satisfaction,
    search_record,
    trending,
)
from components.images import image_html
from components.render import (
    clarification_options,
    parts_to_replace,
    reasoning,
    reasoning_view,
    response_view,
)
from components.theme import CSS
from components.voice import available as voice_installed
from components.voice import message_from, speak_html, transcribe
from components.voice import status as voice_status
from components.voice import warm_up as voice_warm_up
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
ARROW = {"up": "↑", "down": "↓", "flat": "→"}


@dataclass
class Turn:
    shown: str  # what the customer typed or clicked
    sent: str  # what was sent to the agent (shown + context when answering a clarification)
    response: RecommendationResponse
    trace: list[str]
    found_by: str | None
    voice: bool = False  # the question was dictated
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


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
if voice_installed():
    voice_warm_up()  # background download/load: the first dictation does not block the chat


def voice_available() -> bool:
    """The microphone is offered only once the speech model is loaded."""
    return voice_installed() and voice_status() == "ready"


def _voice_pending() -> str:
    if not voice_installed():
        return "Para hablarle al agente instala la voz: `uv sync --extra voice`."
    current = voice_status()
    if current.startswith("error"):
        return f"Voz no disponible ({current[7:]}); puedes escribir normalmente."
    return "Voz: preparando el modelo de reconocimiento (solo la primera vez)…"


@st.fragment(run_every="3s")
def _wait_for_voice() -> None:
    """Re-render once the speech model finishes loading, so the microphone appears by itself."""
    if voice_installed() and voice_status() == "ready" and not state.get("voice_shown"):
        state["voice_shown"] = True
        st.rerun(scope="app")


turns: list[Turn] = state.setdefault("turns", [])
search_log = SearchLog()


def _vocabulary() -> list[str]:
    if state.get("agent", REAL) != REAL:
        return []
    return [p.part_number for p in get_artifacts().products]


def _transcriber(audio: bytes) -> str:
    try:
        return transcribe(audio, vocabulary=_vocabulary())
    except Exception as exc:  # model download or decoding problems must not break the chat
        state["voice_error"] = f"No pude transcribir el audio ({str(exc)[:160]})."
        return ""


def ask(text: str | None = None, *, follow_up: bool = True) -> None:
    """Callback: queue a message (typed, clicked or dictated); the agent keeps the context."""
    value = text if text is not None else state.get("chat")
    text, by_voice = message_from(value, _transcriber if voice_available() else None)
    if not text:
        if getattr(value, "audio", None) is not None and not state.get("voice_error"):
            state["voice_error"] = "No entendí el audio; intenta de nuevo o escribe tu mensaje."
        return
    # The agent remembers the conversation through response.context (contract 1.2.0).
    state["pending"] = (text, text, by_voice)
    state["fresh"] = not follow_up
    state["minimized"] = False


def new_conversation() -> None:
    turns.clear()
    st.query_params.clear()


def toggle_widget() -> None:
    state["minimized"] = not state.get("minimized", False)


def rate(turn_id: str) -> None:
    value = state.get(f"fb-{turn_id}")
    if value is not None:
        search_log.rate(turn_id, useful=value == 1)


# Only on a fresh session: later reruns keep ?k= in the URL and must not re-send it.
if "k" in st.query_params and not state.get("url_used") and not turns:
    ask(st.query_params["k"], follow_up=False)
state["url_used"] = True

# ---------------------------------------------------------------- sidebar: history and trends
history_rows = search_log.read()
with st.sidebar:
    st.markdown("### Historial de búsqueda")
    trends = trending(history_rows)
    st.markdown("**Más buscadas · últimos 7 días**")
    if trends:
        top = trends[0].total
        for i, trend in enumerate(trends):
            with st.container(key=f"trend-{i}"):
                st.button(
                    f"{trend.topic}",
                    key=f"trend-ask-{i}",
                    on_click=ask,
                    args=(trend.example,),
                    kwargs={"follow_up": False},
                    type="tertiary",
                )
                st.markdown(
                    f'<div class="trend"><div class="bar" style="width:{trend.total / top:.0%}">'
                    f"</div><span>{trend.total} {'búsqueda' if trend.total == 1 else 'búsquedas'} "
                    f'<b class="{trend.direction}">{ARROW[trend.direction]}</b> '
                    f"vs. 7 días previos ({trend.previous})</span></div>",
                    unsafe_allow_html=True,
                )
    else:
        st.caption("Aún no hay búsquedas registradas.")
    st.markdown("**Búsquedas recientes**")
    latest = recent(history_rows)
    if latest:
        for i, record in enumerate(latest):
            label = record["text"] if len(record["text"]) <= 46 else record["text"][:45] + "…"
            st.button(
                label,
                key=f"recent-{i}",
                on_click=ask,
                args=(record["sent"] or record["text"],),
                kwargs={"follow_up": False},
                type="tertiary",
                help=f"{record['ts'][:16].replace('T', ' ')} UTC · "
                f"{OUTCOME_LABEL.get(record.get('outcome', ''), '')}",
            )
    else:
        st.caption("Tus búsquedas aparecerán aquí.")
    useful, rated = satisfaction(history_rows)
    if rated:
        st.caption(f"Respuestas valoradas como útiles: {useful} de {rated}")

# ---------------------------------------------------------------- widget header
minimized = state.get("minimized", False)
kind = state.get("agent", REAL)
with st.container(key="widget-head"):
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        who = st.container(width="stretch")
        menu = st.container(width=48)
        fold = st.container(width=48)
    online = "En línea" if kind == REAL else "Modo simulado"
    who.markdown(
        '<div class="head-id"><div class="avatar">AI</div><div><small>Chat con</small><br>'
        "<b>Agente de reemplazo Emerson</b></div></div>"
        f'<div class="head-status"><span class="dot"></span>{online} · responde en segundos con '
        "evidencia de los datasheets</div>",
        unsafe_allow_html=True,
    )
    with menu.popover("", icon=":material/more_vert:", help="Ajustes del agente"):
        kind = st.radio("Fuente de datos", [REAL, MOCK], key="agent")
        st.button(
            "Nueva conversación", key="new-chat", on_click=new_conversation,
            icon=":material/add_comment:",
        )  # fmt: skip
        agent = get_agent(kind)
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
        st.markdown("**Voz**")
        st.toggle("Responder con voz", key="tts", help="Lee en voz alta cada respuesta.")
        st.caption(
            "Micrófono en el campo de mensaje: transcripción local con faster-whisper; las "
            "respuestas a preguntas dictadas se leen en voz alta."
            if voice_available()
            else _voice_pending()
        )
        st.caption(
            "Cómo decide: estado, precio y stock salen solo del catálogo; la compatibilidad la "
            "deciden reglas deterministas con evidencia; solo recomienda piezas ACTIVE; el LLM "
            "interpreta y redacta, y sus cifras se verifican."
        )
    fold.button(
        "", key="minimize", on_click=toggle_widget,
        icon=":material/expand_more:" if not minimized else ":material/expand_less:",
        help="Minimizar el chat" if not minimized else "Abrir el chat",
    )  # fmt: skip

agent = get_agent(kind)
names = get_artifacts().document_names if kind == REAL else {}
known_parts = [p.part_number for p in get_artifacts().products] if kind == REAL else []

# ---------------------------------------------------------------- run the agent
pending = state.pop("pending", None)
if pending:
    shown, sent, by_voice = pending
    memory = turns[-1].response.context if turns and not state.pop("fresh", False) else None
    with st.spinner("El agente está planeando y usando sus herramientas…"):
        response = agent.answer(CustomerQuery(text=sent, context=memory))
    trace = [str(step) for step in getattr(agent, "last_trace", [])]
    found_by = evidence_sources(agent.retriever) if isinstance(agent, AdvisorAgent) else None
    turn = Turn(shown, sent, response, trace, found_by, voice=by_voice)
    turns.append(turn)
    search_log.append(search_record(turn.id, shown, sent, response, source=kind))
    st.query_params["k"] = sent

if minimized:
    st.caption(f"Chat minimizado · {len(turns)} mensaje(s) en esta conversación.")
    st.stop()

# ---------------------------------------------------------------- conversation
with st.chat_message("assistant"):
    st.markdown(
        "¡Hola! Soy el agente de reemplazo. Dime qué pieza necesitas sustituir (part number) o "
        "qué requisitos debe cumplir: busco en el catálogo, valido la compatibilidad con reglas "
        "y te muestro la evidencia. Si me falta un dato, te pregunto."
    )
    if not turns:
        with st.container(key="quick-examples", horizontal=True, gap="small"):
            for i, (label, text) in enumerate(EXAMPLES.items()):
                st.button(
                    label, key=f"ex-{i}", on_click=ask, args=(text,), kwargs={"follow_up": False}
                )
        if kind == REAL:
            risky = parts_to_replace(get_artifacts().products)
            st.caption(f"O elige una de las {len(risky)} piezas que necesitan reemplazo:")
            with st.container(key="parts-grid", horizontal=True, gap="small"):
                for product in risky:
                    assert product.commercial is not None
                    status = product.commercial.status
                    color = "orange" if status is CommercialStatus.NRND else "red"
                    with st.container(key=f"part-{product.part_number}", width=150):
                        st.markdown(
                            image_html(product, css_class="pimg pimg-mini"),
                            unsafe_allow_html=True,
                        )
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
        if turn.voice:
            st.caption("🎙️ Dictado por voz")
        if turn.sent != turn.shown:
            st.caption(f"Enviado al agente con el contexto anterior: “{turn.sent}”")
    with st.chat_message("assistant"):
        retrieval = get_retrieval_status(kind) if kind == REAL else None
        steps = reasoning(turn.response, turn.trace, retrieval=retrieval, found_by=turn.found_by)
        if steps:
            reasoning_view(steps, turn.response)
        response_view(turn.response, names, turn=i)
        options = turn.response.clarification_options or clarification_options(
            turn.response.clarification_question, known_parts
        )
        if options and i == len(turns) - 1:
            with st.container(key=f"quick-options-{i}", horizontal=True, gap="small"):
                for pn in options:
                    st.button(pn, key=f"opt-{i}-{pn}", on_click=ask, args=(pn,))
        with st.container(
            key=f"rating-{i}", horizontal=True, horizontal_alignment="distribute",
            vertical_alignment="center",
        ):  # fmt: skip
            st.caption(
                f"Redacción: {turn.response.llm_provider} · contrato "
                f"{turn.response.contract_version}"
            )
            with st.container(horizontal=True, gap="small", width="content",
                              vertical_alignment="center"):  # fmt: skip
                st.caption("¿Te fue útil?")
                st.feedback("thumbs", key=f"fb-{turn.id}", on_change=rate, args=(turn.id,))

# Read the newest answer aloud once: always for dictated questions, or when the toggle is on.
if turns and state.get("spoken") != turns[-1].id and (turns[-1].voice or state.get("tts")):
    last = turns[-1].response
    components.html(speak_html(last.clarification_question or last.message), height=0)
    state["spoken"] = turns[-1].id
if state.get("voice_error"):
    st.warning(state.pop("voice_error"))

placeholder = (
    "Responde a la pregunta del agente…"
    if turns and turns[-1].response.clarification_question
    else "Escribe tu mensaje…"
)
if voice_installed() and not state.get("voice_shown"):
    _wait_for_voice()
st.chat_input(placeholder, key="chat", on_submit=ask, accept_audio=voice_available())
