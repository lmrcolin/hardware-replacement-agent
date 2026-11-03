"""Graph construction and persistence (see docs/KNOWLEDGE_GRAPH_DESIGN.md)."""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

import networkx as nx

from advisor.kg.aliases import alias_map, find_mentions
from advisor.models import (
    Chunk,
    EdgeType,
    Evidence,
    GraphEdge,
    GraphNode,
    NodeType,
    Product,
)

log = logging.getLogger(__name__)

# Spec keys that become shared nodes (so products connect through them).
INTERFACE_KEYS = {"host_interface", "interface", "interfaces"}
PROTOCOL_KEYS = {"rdma", "wireless"}
FEATURE_KEYS = {"offloads", "interconnect", "measurands", "form_factor"}

MIGRATION_SECTIONS = re.compile(r"Notice|Migration|Ordering|Replacement")
MIGRATION_WORDS = re.compile(
    r"replac|migrat|supersed|consider|phased out|in favor of|alternativ|successor", re.I
)
# "<this product> is a replacement for <mentioned>" reverses the direction.
REPLACES = re.compile(r"replacement for|replaces|replacing", re.I)
SIMILARITY_MIN = 0.2


def product_id(part_number: str) -> str:
    return f"product:{part_number}"


def _slug(text: str) -> str:
    return re.sub(r"\s+", "_", text.strip())


class _Builder:
    def __init__(self) -> None:
        self.graph = nx.MultiDiGraph()

    def node(self, node: GraphNode) -> str:
        if node.node_id not in self.graph:
            self.graph.add_node(node.node_id, **node.model_dump(mode="json", exclude={"node_id"}))
        return node.node_id

    def edge(self, edge: GraphEdge) -> None:
        key = edge.edge_type.value
        if self.graph.has_edge(edge.source, edge.target, key=key):  # merge evidence
            data = self.graph.edges[edge.source, edge.target, key]
            known = {json.dumps(e, sort_keys=True) for e in data["evidence"]}
            for ev in edge.model_dump(mode="json")["evidence"]:
                if json.dumps(ev, sort_keys=True) not in known:
                    data["evidence"].append(ev)
            return
        attrs = edge.model_dump(mode="json", exclude={"source", "target"})
        self.graph.add_edge(edge.source, edge.target, key=key, **attrs)

    def shared(self, pid: str, node_type: NodeType, prefix: str, value: str, edge: EdgeType,
               evidence: list[Evidence]) -> None:  # fmt: skip
        target = self.node(
            GraphNode(node_id=f"{prefix}:{_slug(value)}", node_type=node_type, label=value)
        )
        self.edge(GraphEdge(source=pid, target=target, edge_type=edge, evidence=evidence))


def _add_product(b: _Builder, p: Product) -> None:
    status = p.commercial.status.value if p.commercial else None
    pid = b.node(
        GraphNode(
            node_id=product_id(p.part_number),
            node_type=NodeType.PRODUCT,
            label=p.part_number,
            properties={
                "description": p.description,
                "manufacturer": p.manufacturer,
                "category": p.category.value,
                "status": status,
            },
        )
    )
    b.shared(pid, NodeType.MANUFACTURER, "manufacturer", p.manufacturer, EdgeType.MADE_BY, [])
    b.shared(pid, NodeType.CATEGORY, "category", p.category.value, EdgeType.IN_CATEGORY, [])
    if status:
        b.shared(pid, NodeType.STATUS, "status", status, EdgeType.HAS_STATUS, [])
    for doc_id in p.document_ids:
        b.node(GraphNode(node_id=f"doc:{doc_id[:12]}", node_type=NodeType.DOCUMENT, label=doc_id,
                         properties={"document_id": doc_id}))  # fmt: skip
        b.edge(GraphEdge(source=pid, target=f"doc:{doc_id[:12]}", edge_type=EdgeType.DESCRIBED_IN))
    for spec in p.specifications:
        values = spec.value if isinstance(spec.value, list) else [spec.value]
        if spec.key == "subcategory" and isinstance(spec.value, str):
            b.shared(pid, NodeType.FAMILY, "family", spec.value, EdgeType.IN_FAMILY, spec.evidence)
        elif spec.key in INTERFACE_KEYS:
            for v in values:
                b.shared(
                    pid,
                    NodeType.INTERFACE,
                    "interface",
                    str(v),
                    EdgeType.HAS_INTERFACE,
                    spec.evidence,
                )
        elif spec.key in PROTOCOL_KEYS:
            for v in values:
                b.shared(
                    pid,
                    NodeType.PROTOCOL,
                    "protocol",
                    str(v),
                    EdgeType.SUPPORTS_PROTOCOL,
                    spec.evidence,
                )
        elif spec.key in FEATURE_KEYS:
            for v in values:
                b.shared(
                    pid, NodeType.FEATURE, "feature", str(v), EdgeType.HAS_FEATURE, spec.evidence
                )
        else:
            sid = b.node(
                GraphNode(
                    node_id=f"spec:{p.part_number}:{spec.key}",
                    node_type=NodeType.SPEC,
                    label=spec.key,
                    properties={"key": spec.key, "value": spec.value, "unit": spec.unit},
                )
            )
            b.edge(
                GraphEdge(
                    source=pid, target=sid, edge_type=EdgeType.HAS_SPEC, evidence=spec.evidence
                )
            )


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=\.)\s+", text) if s]


def _add_migrations(b: _Builder, products: Sequence[Product], chunks: Sequence[Chunk]) -> None:
    """MIGRATES_TO from explicit successor/replacement statements; the sentence is the evidence."""
    owner = {doc: p.part_number for p in products for doc in p.document_ids}
    aliases = alias_map(p.part_number for p in products)
    for chunk in chunks:
        this = owner.get(chunk.document_id)
        if this is None:
            continue
        in_section = bool(chunk.section and MIGRATION_SECTIONS.search(chunk.section))
        for sentence in _sentences(chunk.text):
            if not (in_section or MIGRATION_WORDS.search(sentence)):
                continue
            replaces = REPLACES.search(sentence)
            for other, pos in find_mentions(sentence, aliases):
                if other == this:
                    continue
                old, new = (other, this) if replaces and pos > replaces.start() else (this, other)
                evidence = Evidence(
                    document_id=chunk.document_id,
                    page=chunk.page_start,
                    chunk_id=chunk.chunk_id,
                    quote=sentence,
                )
                b.edge(GraphEdge(source=product_id(old), target=product_id(new),
                                 edge_type=EdgeType.MIGRATES_TO, evidence=[evidence]))  # fmt: skip


def _add_chunks(b: _Builder, chunks: Sequence[Chunk]) -> None:
    for chunk in chunks:
        doc = f"doc:{chunk.document_id[:12]}"
        if doc not in b.graph:
            continue
        cid = b.node(
            GraphNode(
                node_id=f"chunk:{chunk.chunk_id}",
                node_type=NodeType.CHUNK,
                label=chunk.section or "header",
                properties={"chunk_id": chunk.chunk_id, "page": chunk.page_start},
            )
        )
        b.edge(GraphEdge(source=doc, target=cid, edge_type=EdgeType.HAS_CHUNK))


SHARED_EDGES = {
    EdgeType.IN_FAMILY,
    EdgeType.HAS_INTERFACE,
    EdgeType.SUPPORTS_PROTOCOL,
    EdgeType.HAS_FEATURE,
}


def _add_similarity(b: _Builder, products: Sequence[Product]) -> None:
    """SIMILAR_TO (same category, Jaccard over shared family/interface/protocol/feature nodes).

    Discovery signal only: it never implies compatibility.
    """
    traits: dict[str, set[str]] = defaultdict(set)
    for p in products:
        pid = product_id(p.part_number)
        for _, target, key in b.graph.out_edges(pid, keys=True):
            if EdgeType(key) in SHARED_EDGES:
                traits[pid].add(target)
    for i, a in enumerate(products):
        for c in products[i + 1 :]:
            if a.category is not c.category:
                continue
            pa, pc = product_id(a.part_number), product_id(c.part_number)
            union = traits[pa] | traits[pc]
            score = len(traits[pa] & traits[pc]) / len(union) if union else 0.0
            if score >= SIMILARITY_MIN:
                for s, t in ((pa, pc), (pc, pa)):
                    b.edge(
                        GraphEdge(
                            source=s,
                            target=t,
                            edge_type=EdgeType.SIMILAR_TO,
                            weight=round(score, 3),
                        )
                    )


def build_graph(products: Sequence[Product], chunks: Sequence[Chunk]) -> nx.MultiDiGraph:
    """Nodes/edges per docs/KNOWLEDGE_GRAPH_DESIGN.md, each validated by the contracts."""
    b = _Builder()
    for p in sorted(products, key=lambda p: p.part_number):
        _add_product(b, p)
    _add_chunks(b, chunks)
    _add_migrations(b, products, chunks)
    _add_similarity(b, sorted(products, key=lambda p: p.part_number))
    log.info(
        "built graph",
        extra={"nodes": b.graph.number_of_nodes(), "edges": b.graph.number_of_edges()},
    )
    return b.graph


def save(graph: nx.MultiDiGraph, path: Path) -> None:
    """Node-link JSON (artifacts/graph.json), deterministic for the same graph."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = nx.node_link_data(graph, edges="edges")
    path.write_text(
        json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def load(path: Path) -> nx.MultiDiGraph:
    data = json.loads(path.read_text(encoding="utf-8"))
    graph = nx.node_link_graph(data, directed=True, multigraph=True, edges="edges")
    assert isinstance(graph, nx.MultiDiGraph)
    return graph
