from __future__ import annotations

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from advisor.models import Category, CompatibilityLevel, RecommendationResponse

pytestmark = pytest.mark.integration
APP_DIR = Path(__file__).resolve().parents[2] / "app"
APP = APP_DIR / "streamlit_app.py"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "responses"
OFFICIAL = (
    "Necesito una tarjeta de red 100 Gigabit Ethernet con soporte RDMA y offload de IPsec. "
    "Usábamos la Intel E810 pero ya no la encuentro"
)


def search(at: AppTest, text: str) -> AppTest:
    at.text_input(key="q").set_value(text)
    at.button(key="search").click().run()
    assert not at.exception
    return at


def ask(text: str, agent: str = "Real (catálogo + datasheets)") -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert not at.exception
    at.radio(key="agent").set_value(agent).run()
    return search(at, text)


def markdown(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown)


def test_official_case_shows_ranked_substitutes_and_original_card() -> None:
    at = ask(OFFICIAL)
    assert [s.value for s in at.subheader][:2] == ["1. MCX75310AAS-NEAT", "2. BCM57508"]
    assert "Pieza original: E810-CQDA2" in markdown(at) and "DISCONTINUED" in markdown(at)
    assert "Mejor <span>compatibilidad</span>" in markdown(at)  # only on the first card
    assert markdown(at).count('class="choice"') == 1
    assert len(at.dataframe) == 2  # spec comparison per recommendation


def test_clarification_suggests_part_for_typo() -> None:
    at = ask("Reemplazo para la E81O-CQDA2")
    assert any("E810-CQDA2" in i.value for i in at.info)
    assert not at.subheader


def test_a100_explains_blocked_successor() -> None:
    at = ask("Necesito reemplazar la A100")
    assert "H100-SXM5 como sucesor" in markdown(at) and not at.subheader


def test_example_link_and_recent_searches() -> None:
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    at.button(key="ex-DAQ descontinuada").click().run()
    assert at.text_input(key="q").value == "Necesito reemplazar la USB-2627"
    search(at, "Busco una GPU de 80GB")
    assert at.button(key="hist-0") and at.button(key="hist-1")  # both searches kept
    at.button(key="hist-0").click().run()  # back to the DAQ search
    assert not at.exception
    assert next(s.value for s in at.subheader) == "1. USB-2633"


def test_landing_tiles_search_a_replacement() -> None:
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert "Piezas del catálogo que necesitan reemplazo" in markdown(at)
    part = "E810-CQDA2"
    at.button(key=f"pick-{part}").click().run()
    assert not at.exception
    assert next(s.value for s in at.subheader) == "1. MCX75310AAS-NEAT"


def test_mock_agent_still_available() -> None:
    at = ask("Necesito una NIC 100GbE con RDMA", agent="Simulado (fixtures)")
    assert any("SYN-NIC-200" in s.value for s in at.subheader)


def test_unknown_candidates_have_their_own_section() -> None:
    at = ask("Necesito reemplazar el Arm Cortex-A78")
    assert "Posibles, sin datos suficientes" in markdown(at)
    assert "Sustitutos recomendados" not in markdown(at)
    assert [s.value for s in at.subheader] == ["1. w9-3595X"]


def test_filters_only_hide_never_rerank() -> None:
    sys.path.insert(0, str(APP_DIR))
    from components.render import Filters, all_options

    response = RecommendationResponse.model_validate_json(
        (FIXTURES / "replacement_found.json").read_text(encoding="utf-8")
    )
    options = all_options(response)
    assert all(Filters().keep(o) for o in options)
    first = options[0]
    by_level = Filters(levels=frozenset({first.compatibility.level}))
    kept = [o for o in options if by_level.keep(o)]
    assert kept[0] is first and [o.rank for o in kept] == sorted(o.rank for o in kept)
    other = next(c for c in Category if c is not first.commercial.category)
    assert not Filters(category=other).keep(first)
    assert not Filters(levels=frozenset({CompatibilityLevel.INCOMPATIBLE})).keep(first)
