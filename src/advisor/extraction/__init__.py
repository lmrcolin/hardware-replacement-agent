"""Extract ProductSpecification values from parsed datasheets using config/spec_registry.yaml."""

from advisor.extraction.extract import (
    ExtractionError,
    Segment,
    document_part_number,
    extract_product,
    normalize,
    own_segments,
    segments,
)
from advisor.extraction.registry import SpecDefinition, SpecRegistry, load_spec_registry

__all__ = [
    "ExtractionError",
    "Segment",
    "SpecDefinition",
    "SpecRegistry",
    "document_part_number",
    "extract_product",
    "load_spec_registry",
    "normalize",
    "own_segments",
    "segments",
]
