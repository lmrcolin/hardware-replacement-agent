"""Spec extraction contract."""

from __future__ import annotations

from advisor.extraction.registry import SpecRegistry
from advisor.models import ParsedDocument, Product


def extract_product(doc: ParsedDocument, registry: SpecRegistry) -> Product:
    """Datasheet → Product with ProductSpecification + Evidence (no commercial data). B-06."""
    raise NotImplementedError("B-06 extraction.extract_product")
