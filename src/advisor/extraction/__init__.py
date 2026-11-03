"""Extract ProductSpecification values from parsed datasheets using config/spec_registry.yaml."""

from advisor.extraction.extract import extract_product
from advisor.extraction.registry import SpecDefinition, SpecRegistry, load_spec_registry

__all__ = ["SpecDefinition", "SpecRegistry", "extract_product", "load_spec_registry"]
