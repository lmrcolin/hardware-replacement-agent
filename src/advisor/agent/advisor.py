"""Controlled advisor agent contract."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol

import networkx as nx

from advisor.commercial import CommercialEngine
from advisor.llm import LLMClient
from advisor.models import CustomerQuery, Product, RecommendationResponse
from advisor.retrieval import Retriever


class AgentStep(StrEnum):
    PARSE = "PARSE"
    RESOLVE = "RESOLVE"
    CLARIFY = "CLARIFY"
    STATUS = "STATUS"
    DISCOVER = "DISCOVER"
    VALIDATE = "VALIDATE"
    RANK = "RANK"
    COMPOSE = "COMPOSE"
    VERIFY = "VERIFY"


class Advisor(Protocol):
    """What the UI depends on. Implemented by AdvisorAgent and app.mock_agent.MockAdvisorAgent."""

    def answer(self, query: CustomerQuery) -> RecommendationResponse: ...


class AdvisorAgent:
    def __init__(
        self,
        *,
        graph: nx.MultiDiGraph,
        products: Sequence[Product],
        commercial: CommercialEngine,
        retriever: Retriever,
        llm_chain: Sequence[LLMClient],
    ) -> None:
        self.graph = graph
        self.products = {p.part_number: p for p in products}
        self.commercial = commercial
        self.retriever = retriever
        self.llm_chain = list(llm_chain)

    def answer(self, query: CustomerQuery) -> RecommendationResponse:
        """PARSE→RESOLVE→CLARIFY|STATUS→DISCOVER→VALIDATE→RANK→COMPOSE→VERIFY. B-19."""
        raise NotImplementedError("B-19 agent.AdvisorAgent.answer")
