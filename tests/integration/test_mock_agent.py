from __future__ import annotations

import sys
from pathlib import Path

import pytest

from advisor.agent import Advisor
from advisor.models import CommercialStatus, CustomerQuery

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))
from mock_agent import MockAdvisorAgent

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def agent() -> Advisor:
    return MockAdvisorAgent()


@pytest.mark.parametrize(
    ("text", "expect_recs", "expect_clarify"),
    [
        ("Necesito una NIC 100GbE con RDMA", True, False),
        ("Reemplazo para la DAQ", False, False),
        ("Necesito un reemplazo", False, True),
    ],
)
def test_mock_routes(agent: Advisor, text: str, expect_recs: bool, expect_clarify: bool) -> None:
    resp = agent.answer(CustomerQuery(text=text))
    assert resp.query.text == text
    assert bool(resp.recommendations) is expect_recs
    assert bool(resp.clarification_question) is expect_clarify
    assert all(r.commercial.status is CommercialStatus.ACTIVE for r in resp.recommendations)
