"""Enumerations shared by every contract."""

from __future__ import annotations

from enum import StrEnum


class CommercialStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISCONTINUED = "DISCONTINUED"
    EOL = "EOL"
    NRND = "NRND"


class Category(StrEnum):
    """Canonical values as written in the commercial catalog."""

    CPU = "CPU"
    DAQ = "DAQ"
    FPGA = "FPGA"
    GPU = "GPU"
    MEMORY = "Memory"
    MICROCONTROLLER = "Microcontroller"
    NETWORK = "Network"
    POWER = "Power"
    SENSOR = "Sensor"
    STORAGE = "Storage"


class CompatibilityLevel(StrEnum):
    COMPATIBLE = "COMPATIBLE"
    COMPATIBLE_WITH_CONDITIONS = "COMPATIBLE_WITH_CONDITIONS"
    UNKNOWN = "UNKNOWN"
    INCOMPATIBLE = "INCOMPATIBLE"


# Best first. Ranking and aggregation must respect this order.
COMPATIBILITY_ORDER: tuple[CompatibilityLevel, ...] = (
    CompatibilityLevel.COMPATIBLE,
    CompatibilityLevel.COMPATIBLE_WITH_CONDITIONS,
    CompatibilityLevel.UNKNOWN,
    CompatibilityLevel.INCOMPATIBLE,
)


class Priority(StrEnum):
    MUST = "MUST"
    SHOULD = "SHOULD"
    NICE = "NICE"


class RequirementOrigin(StrEnum):
    QUERY = "QUERY"
    ORIGINAL_SPEC = "ORIGINAL_SPEC"
    CATEGORY_DEFAULT = "CATEGORY_DEFAULT"


class Operator(StrEnum):
    EQ = "EQ"
    GTE = "GTE"
    LTE = "LTE"
    IN = "IN"
    HAS = "HAS"


class DiscoveryPath(StrEnum):
    SAME_CATEGORY = "SAME_CATEGORY"
    SAME_FAMILY = "SAME_FAMILY"
    MIGRATES_TO = "MIGRATES_TO"
    SIMILAR_TO = "SIMILAR_TO"
    RETRIEVAL = "RETRIEVAL"


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"


class RuleOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    MISSING = "MISSING"
    CONDITIONAL = "CONDITIONAL"


class EvidenceScope(StrEnum):
    PRODUCT = "PRODUCT"
    FAMILY = "FAMILY"


class DocumentType(StrEnum):
    CATALOG = "CATALOG"
    DATASHEET = "DATASHEET"


class NodeType(StrEnum):
    PRODUCT = "Product"
    MANUFACTURER = "Manufacturer"
    CATEGORY = "Category"
    FAMILY = "Family"
    INTERFACE = "Interface"
    PROTOCOL = "Protocol"
    FEATURE = "Feature"
    SPEC = "Spec"
    DOCUMENT = "Document"
    CHUNK = "Chunk"
    STATUS = "Status"


class EdgeType(StrEnum):
    MADE_BY = "MADE_BY"
    IN_CATEGORY = "IN_CATEGORY"
    IN_FAMILY = "IN_FAMILY"
    HAS_INTERFACE = "HAS_INTERFACE"
    SUPPORTS_PROTOCOL = "SUPPORTS_PROTOCOL"
    HAS_FEATURE = "HAS_FEATURE"
    HAS_SPEC = "HAS_SPEC"
    DESCRIBED_IN = "DESCRIBED_IN"
    HAS_CHUNK = "HAS_CHUNK"
    HAS_STATUS = "HAS_STATUS"
    MIGRATES_TO = "MIGRATES_TO"
    SIMILAR_TO = "SIMILAR_TO"
    SUBSTITUTE_CANDIDATE = "SUBSTITUTE_CANDIDATE"
