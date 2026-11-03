"""Pydantic v2 data contracts shared by every module (data + validators only)."""

from advisor.models.base import Contract, DataConsistencyWarning
from advisor.models.compatibility import CandidateProduct, CompatibilityResult, RuleResult
from advisor.models.documents import (
    Chunk,
    ChunkHit,
    DocumentRecord,
    Evidence,
    ParsedDocument,
    ParsedPage,
)
from advisor.models.enums import (
    COMPATIBILITY_ORDER,
    Category,
    CommercialStatus,
    CompatibilityLevel,
    DiscoveryPath,
    DocumentType,
    EdgeType,
    EvidenceScope,
    NodeType,
    Operator,
    Priority,
    RequirementOrigin,
    RuleOutcome,
    Severity,
)
from advisor.models.graph import GraphEdge, GraphNode
from advisor.models.products import (
    CommercialInformation,
    JoinReport,
    PartMatch,
    Product,
    ProductSpecification,
    SpecValue,
)
from advisor.models.query import CustomerQuery, ParsedQuery, TechnicalRequirement
from advisor.models.recommendation import Recommendation, RecommendationResponse
from advisor.models.version import CONTRACT_VERSION

__all__ = [
    "COMPATIBILITY_ORDER",
    "CONTRACT_VERSION",
    "CandidateProduct",
    "Category",
    "Chunk",
    "ChunkHit",
    "CommercialInformation",
    "CommercialStatus",
    "CompatibilityLevel",
    "CompatibilityResult",
    "Contract",
    "CustomerQuery",
    "DataConsistencyWarning",
    "DiscoveryPath",
    "DocumentRecord",
    "DocumentType",
    "EdgeType",
    "Evidence",
    "EvidenceScope",
    "GraphEdge",
    "GraphNode",
    "JoinReport",
    "NodeType",
    "Operator",
    "ParsedDocument",
    "ParsedPage",
    "ParsedQuery",
    "PartMatch",
    "Priority",
    "Product",
    "ProductSpecification",
    "Recommendation",
    "RecommendationResponse",
    "RequirementOrigin",
    "RuleOutcome",
    "RuleResult",
    "Severity",
    "SpecValue",
    "TechnicalRequirement",
]
