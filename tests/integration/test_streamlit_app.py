from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.integration
APP = Path(__file__).resolve().parents[2] / "app" / "streamlit_app.py"


def run_app(agent: str) -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert not at.exception
    at.sidebar.radio[0].set_value(agent).run()
    at.button[0].click().run()
    assert not at.exception
    return at


def test_real_agent_answers_official_case() -> None:
    at = run_app("Real (catálogo + datasheets)")
    titles = [s.value for s in at.subheader]
    assert titles[:2] == ["1. MCX75310AAS-NEAT", "2. BCM57508"]


def test_mock_agent_still_available() -> None:
    at = run_app("Simulado (fixtures)")
    assert any("SYN-NIC-200" in s.value for s in at.subheader)
