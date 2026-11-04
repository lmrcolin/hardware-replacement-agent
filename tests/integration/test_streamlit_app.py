from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from streamlit.testing.v1 import AppTest

from advisor.models import Category, RecommendationResponse

pytestmark = pytest.mark.integration
APP_DIR = Path(__file__).resolve().parents[2] / "app"
APP = APP_DIR / "streamlit_app.py"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "responses"
OFFICIAL = (
    "Necesito una tarjeta de red 100 Gigabit Ethernet con soporte RDMA y offload de IPsec. "
    "Usábamos la Intel E810 pero ya no la encuentro"
)
REAL = "Real (catálogo + datasheets)"


@pytest.fixture(autouse=True)
def _isolated_search_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Never write the real history: every test gets its own search log."""
    log = tmp_path / "searches.jsonl"
    monkeypatch.setenv("ADVISOR_SEARCH_LOG", str(log))
    return log


def _component(name: str) -> ModuleType:
    sys.path.insert(0, str(APP_DIR))
    module = __import__(f"components.{name}", fromlist=[name])
    return module


def chat(at: AppTest, text: str) -> AppTest:
    at.chat_input(key="chat").set_value(text).run()
    assert not at.exception
    return at


def ask(text: str, agent: str = REAL) -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert not at.exception
    at.radio(key="agent").set_value(agent).run()
    return chat(at, text)


def markdown(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown)


# ---------------------------------------------------------------- conversation


def test_official_case_shows_reasoning_answer_and_ranked_substitutes() -> None:
    at = ask(OFFICIAL)
    assert [s.value for s in at.subheader][:2] == ["1. MCX75310AAS-NEAT", "2. BCM57508"]
    page = markdown(at)
    assert "Pieza original" in page and ">E810-CQDA2<" in page and ">Descontinuada<" in page
    assert page.count('<table class="specs">') == 2  # spec comparison per recommendation
    assert 'title="El fabricante dejó de producirla' in page  # badges explain themselves
    reasoning = [e for e in at.expander if e.label.startswith("Cómo lo resolvió el agente")]
    assert len(reasoning) == 1
    steps = markdown(at)
    for key in ("PARSE", "RESOLVE", "STATUS", "DISCOVER", "VALIDATE", "RANK", "COMPOSE", "VERIFY"):
        assert f'<span class="step-key">{key}</span>' in steps
    assert "Coincidencia segura en el catálogo: E810-CQDA2" in steps


def test_clarification_offers_options_and_keeps_context() -> None:
    at = ask("Reemplazo para la E81O-CQDA2")
    assert '<div class="ask">' in markdown(at) and "E810-CQDA2" in markdown(at)
    assert not at.subheader
    assert "Responde a la pregunta del agente" in at.chat_input(key="chat").placeholder
    option = "E810-CQDA2"
    at.button(key=f"opt-0-{option}").click().run()
    assert not at.exception
    assert next(s.value for s in at.subheader) == "1. MCX75310AAS-NEAT"


def test_free_text_follow_up_uses_the_conversation_memory() -> None:
    at = ask("Necesito reemplazar la E810-CQDA2")
    chat(at, "¿y la más barata?")  # no part number: the agent remembers it (contract 1.2.0)
    turns = at.session_state["turns"]
    assert turns[-1].response.original.part_number == "E810-CQDA2"
    assert turns[-1].response.recommendations[0].product.part_number == "BCM57508"


def test_a100_explains_blocked_successor() -> None:
    at = ask("Necesito reemplazar la A100")
    assert "H100-SXM5 como sucesor" in markdown(at)
    assert "Sustitutos recomendados" not in markdown(at)
    # Not a recommendation: offered only "if you can do without" the SXM4 form factor.
    assert any(e.label.startswith("Si puedes prescindir de un requisito") for e in at.expander)
    assert [s.value for s in at.subheader] == ["1. H100-SXM5"]


def test_example_and_part_shortcuts_start_new_questions() -> None:
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    at.button(key="ex-1").click().run()  # "DAQ descontinuada"
    assert not at.exception
    assert next(s.value for s in at.subheader) == "1. USB-2633"
    chat(at, "Busco una GPU de 80GB")
    assert len(at.session_state["turns"]) == 2
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    part = "E810-CQDA2"
    at.button(key=f"pick-{part}").click().run()
    assert next(s.value for s in at.subheader) == "1. MCX75310AAS-NEAT"


def test_new_conversation_clears_the_chat() -> None:
    at = ask("Necesito reemplazar la USB-2627")
    at.button(key="new-chat").click().run()
    assert not at.session_state["turns"] and not at.subheader
    assert "¿Qué pieza necesitas reemplazar?" in markdown(at)  # back to the home screen


def test_mock_agent_still_available() -> None:
    at = ask("Necesito una NIC 100GbE con RDMA", agent="Simulado (fixtures)")
    assert any("SYN-NIC-200" in s.value for s in at.subheader)


def test_unknown_candidates_have_their_own_section() -> None:
    at = ask("Necesito reemplazar el Arm Cortex-A78")
    labels = [e.label for e in at.expander]
    assert any(label.startswith("Posibles, sin datos suficientes") for label in labels)
    assert "Sustitutos recomendados" not in markdown(at)
    assert [s.value for s in at.subheader] == ["1. w9-3595X"]


def test_settings_menu_lists_the_agent_tools() -> None:
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    tools = markdown(at)
    for tool in ("Catálogo comercial", "Grafo de conocimiento", "Búsqueda documental"):
        assert tool in tools
    assert "Motor de compatibilidad" in tools and "Modelo de lenguaje" in tools


# ---------------------------------------------------------------- pure components


def test_reasoning_explains_each_step_from_the_response() -> None:
    render = _component("render")
    response = RecommendationResponse.model_validate_json(
        (FIXTURES / "replacement_found.json").read_text(encoding="utf-8")
    )
    trace = ["PARSE", "RESOLVE", "STATUS", "DISCOVER", "VALIDATE", "RANK", "COMPOSE", "VERIFY"]
    steps = render.reasoning(response, trace, retrieval="BM25 local", found_by="bm25 3")
    assert [s.key for s in steps] == trace
    by_key = {s.key: s.detail for s in steps}
    assert f"{len(response.recommendations)} recomendado(s)" in by_key["VALIDATE"]
    assert "BM25 local" in by_key["DISCOVER"] and "bm25 3" in by_key["DISCOVER"]
    nlu, nlg = render.providers(response)
    assert nlu in by_key["PARSE"] and nlg in by_key["COMPOSE"]


def test_clarification_options_are_catalog_parts_in_mention_order() -> None:
    render = _component("render")
    known = ["E810-CQDA2", "E810", "USB-2627", "USB-2633"]
    question = "No encontré ese part number exacto. ¿Te refieres a USB-2633 o E810-CQDA2?"
    assert render.clarification_options(question, known) == ["USB-2633", "E810-CQDA2"]
    assert render.clarification_options(None, known) == []


# ---------------------------------------------------------------- images


def test_every_product_gets_an_illustration_matching_its_form_factor() -> None:
    import base64
    import xml.etree.ElementTree as ET

    from advisor.pipeline import load_or_build

    images = _component("images")
    products = {p.part_number: p for p in load_or_build().products}
    expected = {
        "A100-SXM4-80GB": "gpu_module",
        "RTX-4090": "gpu_card",
        "WUS4C6464DSP3X5": "ssd_u2",
        "MZ-V9P2T0": "ssd_m2",
        "Cortex-A78": "ip_die",
        "USB-2627": "daq",
        "AD7606": "qfp",
        "E810-CQDA2": "nic",
        "H3A8G32AMR": "hbm",
    }
    assert {pn: images.kind(products[pn]) for pn in expected} == expected
    for product in products.values():
        svg = images.illustration_svg(product)
        ET.fromstring(svg)  # well-formed
        assert product.part_number[:13] in svg
        src, is_photo = images.image_source(product)
        if is_photo:  # every bundled photo carries its attribution
            assert images.photo_credit(product.part_number) is not None
        else:
            assert base64.b64decode(src.split(",", 1)[1]).decode() == svg


def test_bundled_photos_are_free_licensed_and_attributed() -> None:
    images = _component("images")
    credits = json.loads((images.PHOTOS / "sources.json").read_text(encoding="utf-8"))
    assert credits, "expected bundled photos"
    for part_number, credit in credits.items():
        assert (images.PHOTOS / credit["file"]).is_file()
        assert credit["file"].startswith(part_number)
        assert credit["license"].startswith(("CC BY", "CC0", "Public domain"))
        assert credit["author"] and credit["source_url"].startswith(
            "https://commons.wikimedia.org/"
        )
    # PCIe photos must not stand in for SXM modules (form factor is a critical rule)
    assert not {"A100-SXM4-80GB", "H100-SXM5"} & credits.keys()


def test_real_photo_replaces_the_illustration(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from advisor.models import Product

    images = _component("images")
    product = Product(part_number="SYN-PHOTO-1", manufacturer="Synthetic", category=Category.GPU)
    (tmp_path / "SYN-PHOTO-1.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setattr(images, "PHOTOS", tmp_path)
    monkeypatch.setattr(images, "_CACHE", {})
    src, is_photo = images.image_source(product)
    assert is_photo and src.startswith("data:image/png;base64,")
    assert "Ilustración" not in images.image_html(product)


def test_images_show_in_shortcuts_and_answers() -> None:
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert markdown(at).count('<div class="thumb"><div class="pimg">') == 11  # catalog cards
    chat(at, OFFICIAL)
    # original + 2 recommended substitutes
    assert markdown(at).count('<div class="thumb"><div class="pimg"><img src="data:image/svg') == 3


def test_shared_link_opens_once_and_does_not_replay() -> None:
    at = AppTest.from_file(str(APP), default_timeout=120)
    at.query_params["k"] = "Necesito reemplazar la USB-2627"
    at.run()
    assert next(s.value for s in at.subheader) == "1. USB-2633"
    chat(at, "Busco una GPU de 80GB")
    assert [t.shown for t in at.session_state["turns"]] == [
        "Necesito reemplazar la USB-2627",
        "Busco una GPU de 80GB",
    ]


# ---------------------------------------------------------------- history, trends, rating


def test_searches_are_logged_and_trend_in_the_sidebar(_isolated_search_log: Path) -> None:
    at = ask("Necesito reemplazar la USB-2627")
    chat(at, "Necesito reemplazar la E810-CQDA2")
    chat(at, "Reemplazo para la Intel E810-CQDA2")
    rows = [
        json.loads(line) for line in _isolated_search_log.read_text(encoding="utf-8").splitlines()
    ]
    assert [r["part"] for r in rows] == ["USB-2627", "E810-CQDA2", "E810-CQDA2"]
    assert {r["outcome"] for r in rows} == {"recommended"}
    at = AppTest.from_file(str(APP), default_timeout=120).run()  # a new session sees the history
    trends = [b.label for b in at.sidebar.button if b.key and b.key.startswith("trend-ask-")]
    assert trends[:2] == ["E810-CQDA2", "USB-2627"]  # grouped by resolved part, most searched first
    at.button(key="trend-ask-0").click().run()
    assert next(s.value for s in at.subheader) == "1. MCX75310AAS-NEAT"


def test_settings_panel_holds_the_technical_options() -> None:
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert at.selectbox(key="llm").value == "ours"  # model choice lives in Ajustes, not the chat
    assert at.toggle(key="tts").value is False
    assert at.radio(key="agent").value.startswith("Real")


def test_catalog_filters_by_status_and_text() -> None:
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    at.segmented_control(key="catalog-status").set_value("NRND").run()
    assert {b.key for b in at.button if b.key and b.key.startswith("pick-")} == {
        "pick-Cortex-A78", "pick-XC7A200T", "pick-A100-SXM4-80GB",
    }  # fmt: skip
    at.text_input(key="catalog-q").set_value("nvidia").run()
    assert [b.key for b in at.button if b.key and b.key.startswith("pick-")] == [
        "pick-A100-SXM4-80GB"
    ]


def test_history_helpers(tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta

    history = _component("history")
    now = datetime(2026, 11, 3, tzinfo=UTC)

    def row(days_ago: float, text: str, part: str | None, category: str | None = None) -> dict:  # type: ignore[type-arg]
        ts = (now - timedelta(days=days_ago)).isoformat()
        return {
            "type": "search",
            "ts": ts,
            "text": text,
            "sent": text,
            "part": part,
            "category": category,
        }

    rows = [
        row(10, "Necesito reemplazar la A100", "A100-SXM4-80GB"),
        row(9, "Necesito reemplazar la A100", "A100-SXM4-80GB"),
        row(3, "Necesito reemplazar la A100", "A100-SXM4-80GB"),
        row(2, "Intel E810", "E810-CQDA2"),
        row(1, "e810 por favor", "E810-CQDA2"),
        row(0.5, "Busco una GPU de 80GB", None, "GPU"),
        {"type": "feedback", "id": "a", "useful": True},
        "not json",
    ]
    trends = history.trending([r for r in rows if isinstance(r, dict)], now=now)
    assert [(t.topic, t.total, t.previous, t.direction) for t in trends] == [
        ("E810-CQDA2", 2, 0, "new"),
        ("A100-SXM4-80GB", 1, 2, "down"),
    ]  # only real part numbers trend; a search by category is not a trend
    log = history.SearchLog(tmp_path / "log.jsonl")
    for r in rows[:6]:
        log.append(r)
    log.path.open("a", encoding="utf-8").write("{broken\n")
    log.rate("t1", useful=True)
    log.rate("t2", useful=False)
    log.rate("t2", useful=True)  # latest rating wins
    read = log.read()
    assert len(read) == 9  # the broken line is skipped
    assert history.satisfaction(read) == (2, 2)
    latest = history.recent(read, limit=3)
    assert [history.title(r) for r in latest] == [
        "Buscar GPU",
        "Reemplazo de E810-CQDA2",  # "Intel E810" is the same search: one entry
        "Reemplazo de A100-SXM4-80GB",
    ]
    assert history.relative_time(latest[0]["ts"], now=now) == "hace 12 h"
    assert history.title({"text": "  ¿necesito algo para medir la presión del aire hoy?"}) == (
        "Necesito algo para medir la presión"
    )


def test_history_time_unidentified_and_clear(tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta

    history = _component("history")
    now = datetime(2026, 11, 3, 18, 0, tzinfo=UTC)

    def ago(**delta: float) -> str:
        return (now - timedelta(**delta)).isoformat()

    assert [
        history.relative_time(ago(seconds=20), now),
        history.relative_time(ago(minutes=5), now),
        history.relative_time(ago(hours=3), now),
        history.relative_time(ago(hours=30), now),
        history.relative_time(ago(days=4), now),
        history.relative_time(ago(days=22), now),
        history.relative_time(ago(days=400), now),
        history.relative_time(ago(minutes=-3), now),  # clock skew: never "in the future"
        history.relative_time("not a date", now),
    ] == [
        "hace un momento",
        "hace 5 min",
        "hace 3 h",
        "ayer",
        "hace 4 días",
        "12 oct",
        "29 sep 2025",
        "hace un momento",
        "",
    ]
    trend = history.Trend
    assert [
        trend("X", 3, 1, "x").change,
        trend("X", 2, 2, "x").change,
        trend("X", 1, 4, "x").change,
    ] == ["+2 vs. semana previa", "igual que la semana previa", "\u22123 vs. semana previa"]

    def row(days_ago: float, text: str, part: str | None, category: str | None) -> dict:  # type: ignore[type-arg]
        return {"type": "search", "ts": ago(days=days_ago), "text": text, "sent": text,
                "part": part, "category": category, "outcome": "clarify"}  # fmt: skip

    rows = [
        row(1, "Hola, uno, dos, tres, probando", None, None),
        row(1, "Reemplazo para la E81O-CQDA2", None, None),
        row(9, "hola de nuevo", None, None),  # outside the window
        row(1, "Necesito reemplazar la USB-2627", "USB-2627", "DAQ"),
    ]
    assert [t.topic for t in history.trending(rows, now=now)] == ["USB-2627"]
    assert history.unidentified(rows, now=now) == 2
    assert len(history.recent(rows)) == 4  # recent keeps every question, recognised or not

    log = history.SearchLog(tmp_path / "log.jsonl")
    log.clear()  # nothing to clear: no error, no backup
    assert not log.path.with_name("log.jsonl.bak").exists()
    for r in rows:
        log.append(r)
    log.clear()
    assert log.read() == []
    assert len(history.SearchLog(tmp_path / "log.jsonl.bak").read()) == 4  # one level of undo


def test_sidebar_lists_recent_and_trending_and_can_be_cleared(_isolated_search_log: Path) -> None:
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    seeded = [
        ("Necesito reemplazar la E810-CQDA2", "E810-CQDA2", "Network", "recommended", 30),
        ("Busco una GPU de 80GB", None, "GPU", "recommended", 20),
        ("Hola, hola, uno, dos, tres, probando", None, None, "clarify", 10),
    ]
    _isolated_search_log.write_text(
        "".join(
            json.dumps(
                {
                    "type": "search", "id": f"t{i}", "text": text, "sent": text, "part": part,
                    "category": cat, "outcome": result, "source": REAL,
                    "ts": (now - timedelta(minutes=minutes)).isoformat(),
                }
            )
            + "\n"
            for i, (text, part, cat, result, minutes) in enumerate(seeded)
        ),
        encoding="utf-8",
    )  # fmt: skip
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert not at.exception
    labels = {b.key: b.label for b in at.sidebar.button}
    assert labels["trend-ask-0"] == "E810-CQDA2" and "trend-ask-1" not in labels  # parts only
    assert [labels[f"recent-{i}"] for i in range(3)] == [
        "Hola, hola, uno, dos, tres, probando",  # first words, never cut mid-word
        "Buscar GPU",
        "Reemplazo de E810-CQDA2",
    ]
    side = " ".join(m.value for m in at.sidebar.markdown)
    assert "hace 30 min · con sustituto" in side and "1 consulta esta semana" in side
    assert "vs." not in side  # no "vs. 7 días previos" noise
    at.button(key="history-clear").click().run()
    assert not at.exception
    assert not [b for b in at.sidebar.button if b.key and b.key.startswith(("trend-", "recent-"))]
    assert _isolated_search_log.with_name(_isolated_search_log.name + ".bak").is_file()


def test_agent_failure_shows_a_designed_error_with_retry(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from advisor.agent import AdvisorAgent

    def boom(self, query):  # type: ignore[no-untyped-def]
        raise RuntimeError("catálogo caído")

    at = AppTest.from_file(str(APP), default_timeout=120).run()
    with monkeypatch.context() as patch:
        patch.setattr(AdvisorAgent, "answer", boom)
        chat(at, "Necesito reemplazar la USB-2627")
        assert "No pude completar la consulta" in markdown(at)
        assert not at.exception  # no traceback for the customer
    at.button(key="retry").click().run()
    assert next(s.value for s in at.subheader) == "1. USB-2633"
