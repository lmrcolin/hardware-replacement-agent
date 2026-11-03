from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.integration
APP = Path(__file__).resolve().parents[2] / "app" / "streamlit_app.py"


def test_app_renders_mock_recommendation() -> None:
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not at.exception
    at.button[0].click().run()
    assert not at.exception
    assert any("SYN-NIC-200" in s.value for s in at.subheader)
