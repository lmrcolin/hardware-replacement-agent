"""Knowledge graph (NetworkX): build, persist, resolve parts, expand candidates."""

from advisor.kg.build import build_graph, load, save
from advisor.kg.query import candidate_neighbors, resolve_part

__all__ = ["build_graph", "candidate_neighbors", "load", "resolve_part", "save"]
