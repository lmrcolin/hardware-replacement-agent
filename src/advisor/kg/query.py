"""Graph query contracts (owner: Dev2)."""

from __future__ import annotations

import networkx as nx

from advisor.models import CandidateProduct, PartMatch


def resolve_part(graph: nx.MultiDiGraph, text: str, *, limit: int = 5) -> list[PartMatch]:
    """Exact → normalized → fuzzy (rapidfuzz) match, best first. B-11."""
    raise NotImplementedError("B-11 kg.resolve_part")


def candidate_neighbors(
    graph: nx.MultiDiGraph, part_number: str, *, max_candidates: int = 10
) -> list[CandidateProduct]:
    """Candidates via category/family/MIGRATES_TO/SIMILAR_TO; never the product itself. B-12."""
    raise NotImplementedError("B-12 kg.candidate_neighbors")
