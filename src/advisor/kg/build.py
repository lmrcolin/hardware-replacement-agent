"""Graph construction and persistence contracts (owner: Dev1)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import networkx as nx

from advisor.models import Chunk, Product


def build_graph(products: Sequence[Product], chunks: Sequence[Chunk]) -> nx.MultiDiGraph:
    """Nodes/edges per docs/KNOWLEDGE_GRAPH_DESIGN.md. B-09."""
    raise NotImplementedError("B-09 kg.build_graph")


def save(graph: nx.MultiDiGraph, path: Path) -> None:
    """Persist as node-link JSON (artifacts/graph.json). B-09."""
    raise NotImplementedError("B-09 kg.save")


def load(path: Path) -> nx.MultiDiGraph:
    """Inverse of ``save``. B-09."""
    raise NotImplementedError("B-09 kg.load")
