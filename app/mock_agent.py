"""MockAdvisorAgent: serves the synthetic RecommendationResponse fixtures.

Lets the UI be built before the real AdvisorAgent exists. Implements ``advisor.agent.Advisor``.
"""

from __future__ import annotations

import json
from pathlib import Path

from advisor.models import CustomerQuery, RecommendationResponse

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "responses"

ROUTES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("nic", "red", "network", "gbe", "rdma"), "replacement_found"),
    (("daq", "adquisición", "adquisicion"), "no_substitute"),
)


class MockAdvisorAgent:
    name = "mock"

    def __init__(self, fixtures_dir: Path = FIXTURES) -> None:
        self.responses = {
            path.stem: RecommendationResponse.model_validate(
                json.loads(path.read_text(encoding="utf-8"))
            )
            for path in sorted(fixtures_dir.glob("*.json"))
        }

    def answer(self, query: CustomerQuery) -> RecommendationResponse:
        text = query.text.lower()
        name = next(
            (target for keywords, target in ROUTES if any(k in text for k in keywords)),
            "clarification",
        )
        return self.responses[name].model_copy(update={"query": query})
