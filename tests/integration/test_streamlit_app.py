from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.integration
APP = Path(__file__).resolve().parents[2] / "app" / "streamlit_app.py"
OFFICIAL = (
    "Necesito una tarjeta de red 100 Gigabit Ethernet con soporte RDMA y offload de IPsec. "
    "Usábamos la Intel E810 pero ya no la encuentro"
)


def ask(text: str, agent: str = "Real (catálogo + datasheets)") -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert not at.exception
    at.sidebar.radio[0].set_value(agent).run()
    at.chat_input[0].set_value(text).run()
    assert not at.exception
    return at


def test_official_case_shows_ranked_substitutes_and_original_card() -> None:
    at = ask(OFFICIAL)
    assert [s.value for s in at.subheader][:2] == ["1. MCX75310AAS-NEAT", "2. BCM57508"]
    markdown = " ".join(m.value for m in at.markdown)
    assert "Pieza original: E810-CQDA2" in markdown and "DISCONTINUED" in markdown
    assert len(at.dataframe) == 2  # spec comparison per recommendation


def test_clarification_suggests_part_for_typo() -> None:
    at = ask("Reemplazo para la E81O-CQDA2")
    assert any("E810-CQDA2" in i.value for i in at.info)
    assert not at.subheader


def test_a100_explains_blocked_successor() -> None:
    at = ask("Necesito reemplazar la A100")
    markdown = " ".join(m.value for m in at.markdown)
    assert "H100-SXM5 como sucesor" in markdown and not at.subheader


def test_example_button_and_history() -> None:
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    at.sidebar.button[1].click().run()  # "DAQ descontinuada"
    at.chat_input[0].set_value("Busco una GPU de 80GB").run()
    assert not at.exception
    assert len(at.chat_message) == 4  # two questions + two answers
    assert any(s.value == "1. USB-2633" for s in at.subheader)


def test_mock_agent_still_available() -> None:
    at = ask("Necesito una NIC 100GbE con RDMA", agent="Simulado (fixtures)")
    assert any("SYN-NIC-200" in s.value for s in at.subheader)


def test_unknown_candidates_have_their_own_section() -> None:
    at = ask("Necesito reemplazar el Arm Cortex-A78")
    markdown = " ".join(m.value for m in at.markdown)
    assert "### Posibles, sin datos suficientes" in markdown
    assert "### Sustitutos recomendados" not in markdown
    assert [s.value for s in at.subheader] == ["1. w9-3595X"]
