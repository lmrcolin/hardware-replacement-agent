"""Shared fixtures. Everything under tests/fixtures is SYNTHETIC (SYN-* part numbers)."""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pytest

from advisor.models import CommercialInformation, Product, RecommendationResponse

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
PDF_DIR = ROOT / "data" / "raw"


def _load(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def products() -> dict[str, Product]:
    items = [Product.model_validate(p) for p in _load("products.json")]  # type: ignore[attr-defined]
    return {p.part_number: p for p in items}


@pytest.fixture(scope="session")
def commercial_rows() -> list[CommercialInformation]:
    return [CommercialInformation.model_validate(r) for r in _load("commercial.json")]  # type: ignore[attr-defined]


@pytest.fixture(scope="session")
def mock_graph() -> nx.MultiDiGraph:
    return nx.node_link_graph(
        _load("mock_graph.json"), directed=True, multigraph=True, edges="edges"
    )


@pytest.fixture(scope="session")
def responses() -> dict[str, RecommendationResponse]:
    return {
        p.stem: RecommendationResponse.model_validate(json.loads(p.read_text(encoding="utf-8")))
        for p in sorted((FIXTURES / "responses").glob("*.json"))
    }
