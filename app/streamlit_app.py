"""Streamlit UI (marketplace layout) over the real AdvisorAgent; mock agent selectable.

Top bar with category + search box, quick-links strip with example queries, left rail with the data
source, display filters and recent searches, results with product cards. Ranking and sections come
from the agent untouched.
"""

from __future__ import annotations

import sys
from html import escape
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from components.render import (
    CATEGORY_LABEL,
    LEVEL_LABEL,
    Filters,
    all_options,
    replacement_tiles,
    response_view,
)
from components.theme import CSS
from mock_agent import MockAdvisorAgent

from advisor.agent import Advisor, AdvisorAgent
from advisor.models import Category, CustomerQuery, RecommendationResponse
from advisor.pipeline import (
    BuiltArtifacts,
    build_agent,
    evidence_sources,
    load_or_build,
    retrieval_status,
)

REAL, MOCK = "Real (catálogo + datasheets)", "Simulado (fixtures)"
ALL = "Todas"
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


@st.cache_resource(show_spinner="Comprobando la búsqueda…")
def get_retrieval_status(kind: str) -> str:
    agent = get_agent(kind)
    return retrieval_status(agent.retriever) if isinstance(agent, AdvisorAgent) else "fixtures"


st.set_page_config(page_title="Emerson Replacement Advisor", page_icon="🔧", layout="wide")
st.html(CSS)
state = st.session_state
# (consulta, respuesta, origen de la evidencia: "bm25 8, ai_search 8" o None)
history: list[tuple[str, RecommendationResponse, str | None]] = state.setdefault("history", [])


def ask(text: str | None = None) -> None:
    """Callback: queue a query (from the search box, an example or a tile) for this run."""
    text = (text or state.get("q") or "").strip()
    if text:
        state["q"] = text
        state["pending"] = text


def show(index: int) -> None:
    state["active"] = index


def clear() -> None:
    history.clear()
    state["active"] = None
    state["q"] = ""
    st.query_params.clear()


# Shareable searches: ?k=<consulta> opens the app with that search (once per session).
if "k" in st.query_params and not state.get("url_used"):
    state["url_used"] = True
    ask(st.query_params["k"])


# ---------------------------------------------------------------- top bar
with st.container(key="topbar"), st.form("search_form", border=False):
    brand, category, query, button, account = st.columns([1.8, 1.2, 5.2, 1.0, 1.7])
    brand.markdown(
        '<div class="brand" id="top"><b>Emerson<span>·</span>Advisor</b><br>'
        "<small>Sustitutos para piezas descontinuadas</small></div>",
        unsafe_allow_html=True,
    )
    category.selectbox(
        "Categoría",
        [ALL, *Category],
        key="category",
        format_func=lambda c: ALL if c == ALL else CATEGORY_LABEL[c],
        label_visibility="collapsed",
    )
    query.text_input(
        "Buscar",
        key="q",
        placeholder="Part number o lo que necesitas (p. ej. NIC 100GbE con RDMA)",
        label_visibility="collapsed",
    )
    button.form_submit_button("Buscar", key="search", on_click=ask, icon=":material/search:")
    account.markdown(
        f'<div class="account">Fuente de datos<br><b>{escape(state.get("agent", REAL))}</b></div>',
        unsafe_allow_html=True,
    )

with st.container(key="subnav"):
    cols = st.columns(len(EXAMPLES) + 1)
    for col, (label, text) in zip(cols, EXAMPLES.items(), strict=False):
        col.button(label, key=f"ex-{label}", on_click=ask, args=(text,))
    cols[-1].button("Limpiar búsquedas", key="clear", on_click=clear, icon=":material/delete:")

# ---------------------------------------------------------------- layout
rail, main = st.columns([1.15, 4.85], gap="medium")
with rail, st.container(key="rail"):
    kind = st.radio("Fuente de datos", [REAL, MOCK], key="agent")

agent = get_agent(kind)
names = get_artifacts().document_names if kind == REAL else {}

pending = state.pop("pending", None)
if pending:
    with main, st.spinner("Analizando compatibilidad…"):
        response = agent.answer(CustomerQuery(text=pending))
        found_by = evidence_sources(agent.retriever) if isinstance(agent, AdvisorAgent) else None
        history.append((pending, response, found_by))
    state["active"] = len(history) - 1
    st.query_params["k"] = pending

active = state.get("active")
current = history[active] if active is not None and active < len(history) else None

filters = Filters()
with rail:
    if current is not None:
        options = all_options(current[1])
        if options:
            st.markdown('<div class="rail-title">Compatibilidad</div>', unsafe_allow_html=True)
            levels = st.pills(
                "Compatibilidad",
                sorted({o.compatibility.level for o in options}, key=list(LEVEL_LABEL).index),
                format_func=LEVEL_LABEL.__getitem__,
                selection_mode="multi",
                key=f"f-level-{active}",
                label_visibility="collapsed",
            )
            st.markdown('<div class="rail-title">Fabricante</div>', unsafe_allow_html=True)
            makers = st.pills(
                "Fabricante",
                sorted({o.commercial.manufacturer for o in options}),
                selection_mode="multi",
                key=f"f-maker-{active}",
                label_visibility="collapsed",
            )
            chosen = state.get("category", ALL)
            filters = Filters(
                category=None if chosen == ALL else Category(chosen),
                levels=frozenset(levels or ()),
                manufacturers=frozenset(makers or ()),
            )
    if history:
        st.markdown('<div class="rail-title">Búsquedas recientes</div>', unsafe_allow_html=True)
        for i in reversed(range(len(history))):
            st.button(
                history[i][0][:48] + ("…" if len(history[i][0]) > 48 else ""),
                key=f"hist-{i}",
                on_click=show,
                args=(i,),
                type="tertiary",
                disabled=i == active,
            )
    st.markdown('<div class="rail-title">Fuentes en uso</div>', unsafe_allow_html=True)
    if isinstance(agent, AdvisorAgent):
        st.caption(f"Datos: {get_artifacts().source}")
        st.caption(f"Búsqueda: {get_retrieval_status(kind)}")
        st.caption(f"LLM: {' → '.join(c.name for c in agent.llm_chain)}")
    else:
        st.caption("Datos: fixtures sintéticos (agente simulado)")

# ---------------------------------------------------------------- results
with main:
    if current is None:
        st.markdown(
            '<div class="band">Encuentra un sustituto ACTIVE, con evidencia</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            "El catálogo es la fuente de verdad para estado, precio y stock; la compatibilidad la "
            "deciden reglas deterministas con citas de los datasheets. Escribe una consulta arriba "
            "o elige un ejemplo."
        )
        if kind == REAL:
            replacement_tiles(get_artifacts().products, ask)
    else:
        question, response, _ = current
        total = len(all_options(response))
        st.markdown(
            f'<div class="results-bar">{total} resultado{"s" * (total != 1)} para '
            f'<span class="term">"{escape(question)}"</span> · orden: compatibilidad → cobertura '
            "→ puntuación (el stock solo desempata)</div>",
            unsafe_allow_html=True,
        )
        response_view(response, names, filters)

# ---------------------------------------------------------------- footer
trace = " → ".join(step.value for step in getattr(agent, "last_trace", []))
provider = f"{current[1].llm_provider} · contrato {current[1].contract_version}" if current else "—"
if current and current[2]:
    provider += f" · evidencia recuperada por: {current[2]}"
st.markdown(
    '<div class="backtop"><a href="#top">Volver arriba</a></div>'
    '<div class="footer"><b>Emerson Replacement Advisor</b> · Datathon MICAI 2026<br>'
    "Solo se recomiendan piezas ACTIVE · NRND aparece como opción con riesgo · un dato faltante "
    "nunca cuenta como compatible<br>"
    f"Redacción: {escape(provider)}"
    + (f"<br>Pasos del último análisis: {escape(trace)}" if trace else "")
    + "</div>",
    unsafe_allow_html=True,
)
