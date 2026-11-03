"""Knowledge-graph nodes and edges."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from advisor.models.base import Contract
from advisor.models.documents import Evidence
from advisor.models.enums import EdgeType, NodeType


class GraphNode(Contract):
    node_id: str = Field(pattern=r"^[a-z_]+:.+$")  # "<type>:<key>", e.g. "product:E810-CQDA2"
    node_type: NodeType
    label: str
    properties: dict[str, Any] = {}


class GraphEdge(Contract):
    source: str
    target: str
    edge_type: EdgeType
    weight: float = Field(default=1.0, ge=0.0)
    evidence: list[Evidence] = []

    @model_validator(mode="after")
    def _no_self_loops(self) -> GraphEdge:
        if self.source == self.target:
            raise ValueError("self-loops are not allowed")
        return self

    @model_validator(mode="after")
    def _migration_needs_evidence(self) -> GraphEdge:
        if self.edge_type is EdgeType.MIGRATES_TO and not self.evidence:
            raise ValueError("MIGRATES_TO edges require document evidence")
        return self
