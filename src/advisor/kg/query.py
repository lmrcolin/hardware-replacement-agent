"""Graph queries: part-number resolution and candidate discovery."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Literal

import networkx as nx
from rapidfuzz import fuzz

from advisor.kg.aliases import (
    alias_map,
    find_mentions,
    is_technical_term,
    normalize_part,
    part_root,
)
from advisor.models import CandidateProduct, DiscoveryPath, EdgeType, NodeType, PartMatch

MatchMethod = Literal["exact", "normalized", "fuzzy", "kg"]
FUZZY_MIN = 80.0
# Discovery weights: explicit migration notices dominate, then family, similarity, category.
PATH_WEIGHT = {
    DiscoveryPath.MIGRATES_TO: 1.0,
    DiscoveryPath.SAME_FAMILY: 0.5,
    DiscoveryPath.SIMILAR_TO: 0.4,
    DiscoveryPath.SAME_CATEGORY: 0.2,
}


def _products(graph: nx.MultiDiGraph) -> dict[str, dict[str, object]]:
    return {
        data["label"]: data
        for _, data in graph.nodes(data=True)
        if data.get("node_type") == NodeType.PRODUCT.value
    }


PREFIX_SCORE = 0.7  # below the agent's confidence threshold: suggest, don't act
_QUANTITY = re.compile(r"^\d+(?:\.\d+)?[A-Z/]+$")


def _description_aliases(parts: dict[str, dict[str, object]]) -> dict[str, str]:
    """Model names in catalog descriptions ('SN860', 'MI300X') that identify one product."""
    owners: dict[str, set[str]] = defaultdict(set)
    for part, data in parts.items():
        props = data.get("properties")
        description = str(props.get("description") or "") if isinstance(props, dict) else ""
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9-]{2,}", description):
            upper = token.upper()
            has_both = re.search(r"[A-Z]", upper) and re.search(r"\d", upper)
            technical = _QUANTITY.match(upper) or is_technical_term(upper)
            if has_both and len(upper) >= 4 and not technical:
                owners[upper].add(part)
    return {token: next(iter(ps)) for token, ps in owners.items() if len(ps) == 1}


def resolve_part(graph: nx.MultiDiGraph, text: str, *, limit: int = 5) -> list[PartMatch]:
    """Exact → normalized → root alias → fuzzy, best first (one entry per part number)."""
    parts = _products(graph)
    best: dict[str, PartMatch] = {}

    def offer(part: str, score: float, method: MatchMethod) -> None:
        if part not in best or score > best[part].score:
            best[part] = PartMatch(part_number=part, score=round(score, 3), method=method)

    for part, _ in find_mentions(text, {p: p for p in parts}):
        offer(part, 1.0, "exact")
    norm_text = normalize_part(text)
    for part in parts:
        if len(normalize_part(part)) >= 4 and normalize_part(part) in norm_text:
            offer(part, 0.95, "normalized")
    aliases = alias_map(parts)
    for part, _ in find_mentions(text.upper(), {a.upper(): p for a, p in aliases.items()}):
        offer(part, 0.9, "normalized")
    for part, _ in find_mentions(text.upper(), _description_aliases(parts)):
        offer(part, 0.9, "kg")
    # Only part-number-like tokens (letters and digits) are fuzzy-matched: "100" in "100 Gigabit"
    # must not resemble "A100".
    tokens = [
        normalize_part(t)
        for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9-]{2,}", text)
        if re.search(r"[A-Za-z]", t) and re.search(r"\d", t)
    ]
    for part in parts:
        targets = [normalize_part(part)] + ([normalize_part(r)] if (r := part_root(part)) else [])
        ratio = max((fuzz.ratio(tok, tgt) for tok in tokens for tgt in targets), default=0.0)
        if ratio >= FUZZY_MIN:
            offer(part, 0.85 * ratio / 100, "fuzzy")
    # A truncated part number ("WUS4C6464") is offered back as a suggestion, never assumed.
    for tok in tokens:
        prefixed = [p for p in parts if len(tok) >= 5 and normalize_part(p).startswith(tok)]
        if len(prefixed) == 1:
            offer(prefixed[0], PREFIX_SCORE, "fuzzy")
    return sorted(best.values(), key=lambda m: (-m.score, m.part_number))[:limit]


def _neighbors_via(graph: nx.MultiDiGraph, pid: str, edge: EdgeType) -> set[str]:
    """Products sharing a node reached through ``edge`` (category, family)."""
    out: set[str] = set()
    for _, shared, key in graph.out_edges(pid, keys=True):
        if key == edge.value:
            out.update(src for src, _, k in graph.in_edges(shared, keys=True) if k == edge.value)
    out.discard(pid)
    return out


def candidate_neighbors(
    graph: nx.MultiDiGraph, part_number: str, *, max_candidates: int = 10
) -> list[CandidateProduct]:
    """Candidates via MIGRATES_TO, family, SIMILAR_TO and category; never the product itself.

    Discovery only: compatibility is decided later by the deterministic engine.
    """
    pid = f"product:{part_number}"
    if pid not in graph:
        raise KeyError(part_number)
    paths: dict[str, set[DiscoveryPath]] = defaultdict(set)
    score: dict[str, float] = defaultdict(float)

    def add(target: str, path: DiscoveryPath, weight: float = 1.0) -> None:
        if target != pid and path not in paths[target]:
            paths[target].add(path)
            score[target] += PATH_WEIGHT[path] * weight

    for _, target, key in graph.out_edges(pid, keys=True):
        if key == EdgeType.MIGRATES_TO.value:
            add(target, DiscoveryPath.MIGRATES_TO)
    for _, target, key, data in graph.out_edges(pid, keys=True, data=True):
        if key == EdgeType.SIMILAR_TO.value:
            add(target, DiscoveryPath.SIMILAR_TO, float(data.get("weight", 1.0)))
    for target in _neighbors_via(graph, pid, EdgeType.IN_FAMILY):
        add(target, DiscoveryPath.SAME_FAMILY)
    for target in _neighbors_via(graph, pid, EdgeType.IN_CATEGORY):
        add(target, DiscoveryPath.SAME_CATEGORY)

    ranked = sorted(score, key=lambda t: (-score[t], t))[:max_candidates]
    return [
        CandidateProduct(
            part_number=graph.nodes[t]["label"],
            discovery_paths=sorted(paths[t]),
            discovery_score=round(score[t], 3),
        )
        for t in ranked
    ]
