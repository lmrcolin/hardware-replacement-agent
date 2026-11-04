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
    assert "Pieza original: E810-CQDA2" in markdown(at) and "DISCONTINUED" in markdown(at)
    assert len(at.dataframe) == 2  # spec comparison per recommendation
    status = [s for s in at.status if s.label.startswith("Razonamiento del agente")]
    assert len(status) == 1
    steps = markdown(at)
    for key in ("PARSE", "RESOLVE", "STATUS", "DISCOVER", "VALIDATE", "RANK", "COMPOSE", "VERIFY"):
        assert f'<span class="step-key">{key}</span>' in steps
    assert "Coincidencia segura en el catálogo: E810-CQDA2" in steps


def test_clarification_offers_options_and_keeps_context() -> None:
    at = ask("Reemplazo para la E81O-CQDA2")
    assert any("E810-CQDA2" in i.value for i in at.info)
    assert not at.subheader
    assert "Responde a la pregunta del agente" in at.chat_input(key="chat").placeholder
    option = "E810-CQDA2"
    at.button(key=f"opt-0-{option}").click().run()
    assert not at.exception
    assert any("contexto anterior" in c.value for c in at.caption)
    assert next(s.value for s in at.subheader) == "1. MCX75310AAS-NEAT"


def test_free_text_answer_to_a_clarification_is_sent_with_the_question() -> None:
    at = ask("Reemplazo para la E81O-CQDA2")
    chat(at, "E810-CQDA2")
    sent = [c.value for c in at.caption if "contexto anterior" in c.value]
    assert sent and "Reemplazo para la E81O-CQDA2 E810-CQDA2" in sent[0]


def test_a100_explains_blocked_successor() -> None:
    at = ask("Necesito reemplazar la A100")
    assert "H100-SXM5 como sucesor" in markdown(at) and not at.subheader


def test_example_and_part_shortcuts_start_new_questions() -> None:
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    at.button(key="ex-1").click().run()  # "DAQ descontinuada"
    assert not at.exception
    assert next(s.value for s in at.subheader) == "1. USB-2633"
    chat(at, "Busco una GPU de 80GB")
    assert len(at.chat_message) == 5  # greeting + two questions + two answers
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    part = "E810-CQDA2"
    at.button(key=f"pick-{part}").click().run()
    assert next(s.value for s in at.subheader) == "1. MCX75310AAS-NEAT"


def test_new_conversation_clears_the_chat() -> None:
    at = ask("Necesito reemplazar la USB-2627")
    at.button(key="new-chat").click().run()
    assert len(at.chat_message) == 1 and not at.subheader


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
    assert markdown(at).count('class="pimg pimg-mini"') == 11
    chat(at, OFFICIAL)
    # original + 2 recommended substitutes
    assert markdown(at).count('<div class="pimg"><img src="data:image/svg+xml') == 3


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


def test_minimize_hides_the_conversation() -> None:
    at = ask("Necesito reemplazar la USB-2627")
    at.button(key="minimize").click().run()
    assert not at.chat_input and not at.subheader
    at.button(key="minimize").click().run()
    assert at.chat_input and at.subheader


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
        ("E810-CQDA2", 2, 0, "up"),
        ("A100-SXM4-80GB", 1, 2, "down"),
        ("GPU", 1, 0, "up"),
    ]
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
    assert [r["text"] for r in history.recent(read, limit=3)] == [
        "Busco una GPU de 80GB",
        "e810 por favor",
        "Intel E810",
    ]
