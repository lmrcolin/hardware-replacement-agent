"""Streamlit UI for the replacement agent (real AdvisorAgent or mock).

Layout (design system in app/static/design.css): a thin translucent top bar (agent, new
conversation, settings), a sidebar with recent searches and trending part numbers, a centered home
screen with the parts that need replacement, and the conversation: customer bubbles on the right,
the agent's answer as plain text with result cards underneath. The agent remembers the
conversation through ``response.context`` (contract 1.2.0); the UI only sends it back.
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from components.history import (
    OUTCOME_LABEL,
    SearchLog,
    recent,
    relative_time,
    search_record,
    title,
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
from components.theme import AVATAR_PATH, AVATAR_URI, css, status_badge
from components.voice import available as voice_installed
from components.voice import message_from, speak_html, transcribe
from components.voice import status as voice_status
from components.voice import warm_up as voice_warm_up
from mock_agent import MockAdvisorAgent

from advisor.agent import Advisor, AdvisorAgent
from advisor.config import LLMChoice, get_settings
from advisor.models import CommercialStatus, CustomerQuery, RecommendationResponse
from advisor.pipeline import (
    BuiltArtifacts,
    build_agent,
    evidence_sources,
    llm_status,
    load_or_build,
    retrieval_status,
)

log = logging.getLogger("advisor.app")
REAL, MOCK = "Real (catálogo + datasheets)", "Simulado (fixtures)"
OFFICIAL = (
    "Necesito una tarjeta de red 100 Gigabit Ethernet con soporte RDMA y offload de IPsec. "
    "Usábamos la Intel E810 pero ya no la encuentro"
)
EXAMPLES = {  # natural actions for an engineer (not test names)
    "Reemplazar la Intel E810-CQDA2": OFFICIAL,
    "Alternativa a una DAQ descontinuada": "Necesito reemplazar la USB-2627",
    "Buscar por requisitos técnicos": "Necesito una NIC de 25 Gb con SR-IOV",
    "Preguntar por una especificación": "¿Cuánto consume la H100?",
}
STATUS_FILTER = {
    "Todas": None,
    "Descontinuadas": CommercialStatus.DISCONTINUED,
    "Fin de vida": CommercialStatus.EOL,
    "NRND": CommercialStatus.NRND,
}
LLM_LABEL = {"ours": "Nuestro LLM (Llama 3.3 en Databricks)", "claude": "Claude (API key)"}
PLACEHOLDER = "Describe la pieza o pega un part number"


@dataclass
class Turn:
    shown: str  # what the customer typed, clicked or dictated
    sent: str  # what was sent to the agent
    response: RecommendationResponse
    trace: list[str]
    found_by: str | None
    voice: bool = False  # the question was dictated
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@st.cache_resource(show_spinner="Cargando catálogo, datasheets y grafo…")
def get_artifacts() -> BuiltArtifacts:
    return load_or_build()


@st.cache_resource
def get_agent(kind: str, llm: LLMChoice = "ours") -> Advisor:
    """One agent per data source and LLM option (each keeps its own answer cache)."""
    if kind == MOCK:
        return MockAdvisorAgent()
    return build_agent(artifacts=get_artifacts(), llm=llm)


@st.cache_resource(show_spinner="Comprobando la búsqueda documental…")
def get_retrieval_status(kind: str) -> str:
    agent = get_agent(kind)
    return retrieval_status(agent.retriever) if isinstance(agent, AdvisorAgent) else "fixtures"


st.set_page_config(
    page_title="Agente de reemplazo · Emerson", page_icon=str(AVATAR_PATH), layout="wide"
)
st.html(css())
state = st.session_state
get_settings()  # loads .env, so ADVISOR_LLM_DEFAULT below sees the local choice
if "llm" not in state:  # "claude" in a local .env preselects Claude; the team default is our LLM
    state["llm"] = "claude" if os.environ.get("ADVISOR_LLM_DEFAULT") == "claude" else "ours"
turns: list[Turn] = state.setdefault("turns", [])
search_log = SearchLog()
if voice_installed():
    voice_warm_up()  # background download/load: the first dictation does not block the chat


def html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def chosen_llm() -> LLMChoice:
    return "claude" if state.get("llm") == "claude" else "ours"


# ---------------------------------------------------------------- voice


def voice_available() -> bool:
    """The microphone is offered only once the speech model is loaded."""
    return voice_installed() and voice_status() == "ready"


def _voice_pending() -> str:
    if not voice_installed():
        return "Para dictar instala la voz: `uv sync --extra voice`."
    current = voice_status()
    if current.startswith("error"):
        return f"Voz no disponible ({current[7:]}); puedes escribir normalmente."
    return "Preparando el reconocimiento de voz (solo la primera vez)…"


@st.fragment(run_every="3s")
def _wait_for_voice() -> None:
    """Re-render once the speech model finishes loading, so the microphone appears by itself."""
    if voice_installed() and voice_status() == "ready" and not state.get("voice_shown"):
        state["voice_shown"] = True
        st.rerun(scope="app")


def _vocabulary() -> list[str]:
    if state.get("agent", REAL) != REAL:
        return []
    return [p.part_number for p in get_artifacts().products]


def _transcriber(audio: bytes) -> str:
    try:
        return transcribe(audio, vocabulary=_vocabulary())
    except Exception as exc:  # model download or decoding problems must not break the chat
        log.exception("voice transcription failed")
        state["voice_error"] = f"No pude transcribir el audio ({str(exc)[:160]})."
        return ""


# ---------------------------------------------------------------- callbacks


def ask(text: str | None = None, *, follow_up: bool = True) -> None:
    """Queue a message (typed, clicked or dictated); the agent keeps the context."""
    value = text if text is not None else state.get("chat")
    text, by_voice = message_from(value, _transcriber if voice_available() else None)
    if not text:
        if getattr(value, "audio", None) is not None and not state.get("voice_error"):
            state["voice_error"] = "No entendí el audio; intenta de nuevo o escribe tu mensaje."
        return
    state["pending"] = (text, text, by_voice)
    state["fresh"] = not follow_up


def new_conversation() -> None:
    turns.clear()
    state.pop("pending", None)
    st.query_params.clear()


def clear_history() -> None:
    search_log.clear()  # the previous log is kept as .bak (one level undo)


def rate(turn_id: str) -> None:
    value = state.get(f"fb-{turn_id}")
    if value is not None:
        search_log.rate(turn_id, useful=value == 1)


# Only on a fresh session: later reruns keep ?k= in the URL and must not re-send it.
if "k" in st.query_params and not state.get("url_used") and not turns:
    ask(st.query_params["k"], follow_up=False)
state["url_used"] = True
kind = state.get("agent", REAL)

# ---------------------------------------------------------------- sidebar: recent and trending
history_rows = search_log.read()
with st.sidebar:
    st.button(
        "Nueva búsqueda", key="new-search", icon=":material/edit_square:",
        on_click=new_conversation, width="stretch",
    )  # fmt: skip
    html('<div class="side-title">Recientes</div>')
    latest = recent(history_rows)
    for i, record in enumerate(latest):
        with st.container(key=f"rc-{i}"):
            st.button(
                title(record),
                key=f"recent-{i}",
                on_click=ask,
                args=(record["sent"] or record["text"],),
                kwargs={"follow_up": False},
                help=record["text"],
            )
            outcome = OUTCOME_LABEL.get(record.get("outcome", ""), "")
            meta = " · ".join(x for x in (relative_time(record.get("ts", "")), outcome) if x)
            html(f'<div class="side-meta">{escape(meta)}</div>')
    if not latest:
        st.caption("Tus búsquedas aparecerán aquí.")
    trends = trending(history_rows)
    if trends:
        html('<div class="side-title">Tendencias</div>')
        for i, trend in enumerate(trends):
            with st.container(key=f"tr-{i}"):
                st.button(
                    trend.topic,
                    key=f"trend-ask-{i}",
                    on_click=ask,
                    args=(trend.example,),
                    kwargs={"follow_up": False},
                )
                count = "1 consulta" if trend.total == 1 else f"{trend.total} consultas"
                html(f'<div class="side-meta">{count} esta semana</div>')
    if history_rows:
        with st.popover("Borrar historial", icon=":material/delete:", type="tertiary"):
            st.caption("Se borran Recientes y Tendencias de este equipo (queda un respaldo .bak).")
            st.button(
                "Sí, borrar historial", key="history-clear", on_click=clear_history,
                type="primary",
            )  # fmt: skip

# ---------------------------------------------------------------- top bar
with st.container(key="topbar", horizontal=True, vertical_alignment="center", gap="small"):
    mode = " · modo simulado" if kind == MOCK else ""
    st.container(width="stretch").markdown(
        f'<div class="brand"><img src="{AVATAR_URI}" alt=""/><div><b>Agente de reemplazo</b>'
        f"<span>Emerson{mode}</span></div></div>",
        unsafe_allow_html=True,
    )
    st.button(
        "Nueva conversación", key="new-chat", icon=":material/edit_square:",
        help="Nueva conversación", on_click=new_conversation,
    )  # fmt: skip
    with st.popover("Ajustes", icon=":material/settings:", help="Ajustes"):
        html('<div class="settings-title">Ajustes</div>')
        st.selectbox(
            "Modelo de lenguaje",
            list(LLM_LABEL),
            key="llm",
            format_func=LLM_LABEL.__getitem__,
            help="Solo cambia quién interpreta, planea y redacta. La compatibilidad, el precio y "
            "el stock los deciden siempre las herramientas y el catálogo.",
        )
        status = llm_status(chosen_llm())
        if status != "ready":
            st.caption(f"Claude no está listo ({status}): se responde con plantillas.")
        kind = st.radio("Fuente de datos", [REAL, MOCK], key="agent")
        st.toggle("Leer las respuestas en voz alta", key="tts")
        st.caption(
            "Dictado local con el micrófono del campo de mensaje (faster-whisper)."
            if voice_available()
            else _voice_pending()
        )
        agent = get_agent(kind, chosen_llm())
        with st.expander("Detalles técnicos · herramientas del agente"):
            if isinstance(agent, AdvisorAgent):
                artifacts = get_artifacts()
                chain = " → ".join(c.name for c in agent.llm_chain)
                tools = [
                    ("Catálogo comercial", f"{len(artifacts.catalog)} piezas · fuente de verdad"),
                    ("Grafo de conocimiento", f"{artifacts.graph.number_of_nodes()} nodos"),
                    ("Búsqueda documental", get_retrieval_status(kind)),
                    ("Motor de compatibilidad", "reglas deterministas · sin LLM"),
                    ("Modelo de lenguaje", f"{chain} · interpreta, planea y redacta"),
                    ("Datos", artifacts.source),
                ]
            else:
                tools = [("Datos", "fixtures sintéticos (agente simulado)")]
            html(
                "".join(
                    f'<div class="tool"><b>{escape(name)}</b><span>{escape(value)}</span></div>'
                    for name, value in tools
                )
            )
            st.caption(
                "Estado, precio y stock salen solo del catálogo; la compatibilidad la deciden "
                "reglas con evidencia; solo se recomiendan piezas activas; las cifras del texto "
                "se verifican."
            )

agent = get_agent(kind, chosen_llm())
names = get_artifacts().document_names if kind == REAL else {}
known_parts = [p.part_number for p in get_artifacts().products] if kind == REAL else []
pending = state.pop("pending", None)


def chat_input(placeholder: str) -> None:
    if voice_installed() and not state.get("voice_shown"):
        _wait_for_voice()
    st.chat_input(placeholder, key="chat", on_submit=ask, accept_audio=voice_available())


# ---------------------------------------------------------------- home
def home() -> None:
    html(
        f'<div class="hero"><img src="{AVATAR_URI}" alt=""/>'
        "<h1>¿Qué pieza necesitas reemplazar?</h1>"
        "<p>Encuentro sustitutos activos y compatibles en el catálogo, con precio, stock y la "
        "evidencia de los datasheets.</p></div>"
    )
    with st.container(key="hero-input"):
        chat_input(PLACEHOLDER)
    with st.container(key="quick-examples", horizontal=True, gap="small"):
        for i, (label, text) in enumerate(EXAMPLES.items()):
            st.button(label, key=f"ex-{i}", on_click=ask, args=(text,), kwargs={"follow_up": False})
    if kind != REAL:
        return
    parts = parts_to_replace(get_artifacts().products)
    html(
        '<div class="section-head"><h2>Piezas que requieren reemplazo</h2>'
        f"<p>{len(parts)} piezas descontinuadas, en fin de vida o no recomendadas. Elige una para "
        "ver sus sustitutos.</p></div>"
    )
    with st.container(key="catalog-filters", horizontal=True, vertical_alignment="center"):
        query = st.text_input(
            "Buscar en el catálogo", key="catalog-q", label_visibility="collapsed",
            placeholder="Buscar part number o fabricante",
        )  # fmt: skip
        chosen = st.segmented_control(
            "Estado", list(STATUS_FILTER), key="catalog-status", default="Todas",
            label_visibility="collapsed",
        )  # fmt: skip
    wanted = STATUS_FILTER.get(chosen or "Todas")
    needle = (query or "").strip().casefold()
    shown = [
        p
        for p in parts
        if p.commercial is not None
        and (wanted is None or p.commercial.status is wanted)
        and (
            not needle
            or needle in p.part_number.casefold()
            or needle in p.commercial.manufacturer.casefold()
            or needle in p.commercial.description.casefold()
        )
    ]
    if not shown:
        html('<div class="empty">No hay piezas que coincidan con el filtro.</div>')
        return
    with st.container(key="catalog-grid"):
        for product in shown:
            c = product.commercial
            assert c is not None
            with st.container(key=f"part-{product.part_number}"):
                html(f'<div class="thumb">{image_html(product)}</div>')
                st.button(
                    product.part_number,
                    key=f"pick-{product.part_number}",
                    on_click=ask,
                    args=(f"Necesito reemplazar la {product.part_number}",),
                    kwargs={"follow_up": False},
                    help=f"Buscar sustitutos de {product.part_number}",
                )
                html(
                    f'<div class="part-meta"><span class="maker">{escape(c.manufacturer)}</span>'
                    f"{status_badge(c.status)}</div>"
                )


# ---------------------------------------------------------------- conversation
def user_bubble(key: str, text: str, *, voice: bool = False) -> None:
    with st.container(key=f"msg-user-{key}"):
        note = '<div class="bubble-note">Dictado por voz</div>' if voice else ""
        html(f'<div class="bubble">{escape(text)}</div>{note}')


def conversation() -> None:
    retrieval = get_retrieval_status(kind) if kind == REAL else None
    for i, turn in enumerate(turns):
        user_bubble(turn.id, turn.shown, voice=turn.voice)
        with st.container(key=f"msg-agent-{turn.id}"):
            steps = reasoning(
                turn.response, turn.trace, retrieval=retrieval, found_by=turn.found_by
            )
            if steps or turn.response.tool_calls:
                reasoning_view(steps, turn.response)
            response_view(turn.response, names, turn=i)
            options = turn.response.clarification_options or clarification_options(
                turn.response.clarification_question, known_parts
            )
            if options and i == len(turns) - 1:
                with st.container(key=f"quick-options-{i}", horizontal=True, gap="small"):
                    for option in options:
                        st.button(option, key=f"opt-{i}-{option}", on_click=ask, args=(option,))
            with st.container(
                key=f"rating-{i}", horizontal=True, vertical_alignment="center", gap="small"
            ):
                st.caption("¿Te fue útil?")
                st.feedback("thumbs", key=f"fb-{turn.id}", on_change=rate, args=(turn.id,))


THINKING = (
    '<div class="thinking"><span class="dots"><i></i><i></i><i></i></span><div>'
    "Analizando tu consulta<small>Interpreta, planea y consulta catálogo, grafo y "
    "datasheets…</small></div></div>"
    '<div class="skeleton" style="width:92%"></div><div class="skeleton" style="width:74%"></div>'
)


def run_pending(message: tuple[str, str, bool]) -> None:
    """Show the question and a thinking state while the agent works, then re-render."""
    shown, sent, by_voice = message
    memory = turns[-1].response.context if turns and not state.pop("fresh", False) else None
    user_bubble("pending", shown, voice=by_voice)
    with st.container(key="msg-agent-pending"):
        html(THINKING)
    try:
        response = agent.answer(CustomerQuery(text=sent, context=memory))
    except Exception:  # the agent degrades by itself; anything left must not show a traceback
        log.exception("agent failed")
        state["failed"] = (shown, sent, by_voice)
        st.rerun()
    state.pop("failed", None)
    trace = [str(step) for step in getattr(agent, "last_trace", [])]
    found_by = evidence_sources(agent.retriever) if isinstance(agent, AdvisorAgent) else None
    turn = Turn(shown, sent, response, trace, found_by, voice=by_voice)
    turns.append(turn)
    state["scroll_to"] = turn.id  # show the new answer from its question, not from the bottom
    search_log.append(search_record(turn.id, shown, sent, response, source=kind))
    st.query_params["k"] = sent
    st.rerun()


def failure(message: tuple[str, str, bool]) -> None:
    shown, _, by_voice = message
    user_bubble("failed", shown, voice=by_voice)
    with st.container(key="msg-agent-failed"):
        html(
            '<div class="error"><b>No pude completar la consulta</b>Hubo un problema al consultar '
            "el catálogo o el modelo de lenguaje. Tu pregunta no se perdió.</div>"
        )
        st.button("Reintentar", key="retry", icon=":material/refresh:", on_click=retry)


def retry() -> None:
    failed = state.pop("failed", None)
    if failed:
        state["pending"] = failed


if not turns and not pending and not state.get("failed"):
    home()
else:
    conversation()
    if state.get("failed") and not pending:
        failure(state["failed"])
    if pending:
        run_pending(pending)
    asking = bool(turns and turns[-1].response.clarification_question)
    chat_input("Responde a la pregunta del agente…" if asking else PLACEHOLDER)

# Streamlit keeps chat apps scrolled to the bottom; a long answer would then be read from its
# end. Once per new answer, bring the customer's question to the top of the view instead.
if (target := state.pop("scroll_to", None)) and turns and turns[-1].id == target:
    st.html(
        "<script>(function(){const sel='.st-key-msg-user-" + target + "';"
        "const go=(smooth)=>{const c=document.querySelector("
        "'[data-testid=\"stAppScrollToBottomContainer\"]');const e=document.querySelector(sel);"
        "if(!c||!e){return;}const top=e.getBoundingClientRect().top-c.getBoundingClientRect().top"
        "+c.scrollTop-72;if(Math.abs(c.scrollTop-top)>4){c.scrollTo({top:top,"
        "behavior:smooth?'smooth':'auto'});}};"
        "setTimeout(()=>go(true),150);setTimeout(()=>go(false),900);setTimeout(()=>go(false),1500);"
        "})();</script>",
        unsafe_allow_javascript=True,
    )

# Read the newest answer aloud once: always for dictated questions, or when the toggle is on.
if turns and state.get("spoken") != turns[-1].id and (turns[-1].voice or state.get("tts")):
    last = turns[-1].response
    with st.container(key="tts-player"):  # hidden; the script inside only calls speechSynthesis
        st.iframe(speak_html(last.clarification_question or last.message), height=1)
    state["spoken"] = turns[-1].id
if state.get("voice_error"):
    st.toast(state.pop("voice_error"), icon=":material/mic_off:")
