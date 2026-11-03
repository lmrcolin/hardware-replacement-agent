"""Local end-to-end build: PDFs → products/chunks → KG → compatibility matrix → artifacts.

Skeleton only. Each step delegates to its module contract; fill them in per backlog item.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from advisor.agent import AdvisorAgent
from advisor.chunking import chunk_document
from advisor.commercial import CommercialEngine
from advisor.config import REPO_ROOT, Settings, get_settings
from advisor.enrichment import join_catalog
from advisor.extraction import extract_product, load_spec_registry
from advisor.ingestion import discover_documents
from advisor.kg import build_graph
from advisor.llm import build_llm_chain
from advisor.models import Chunk, CommercialInformation, DocumentType, JoinReport, Product
from advisor.parsing import parse_catalog, parse_document
from advisor.retrieval import BM25Retriever

log = logging.getLogger(__name__)

STEPS: tuple[str, ...] = (
    "discover",  # ingestion.discover_documents
    "parse",  # parsing.parse_document / parse_catalog
    "extract",  # extraction.extract_product
    "enrich",  # enrichment.join_catalog
    "chunk",  # chunking.chunk_document
    "kg",  # kg.build_graph + kg.save
    "compat_matrix",  # compatibility.evaluate over every (discontinued, active) pair
    "export",  # repository.ArtifactRepository
)


def _not_implemented(step: str) -> Callable[[Settings], None]:
    def run(_: Settings) -> None:
        raise NotImplementedError(f"pipeline step '{step}' is not implemented yet")

    return run


RUNNERS: dict[str, Callable[[Settings], None]] = {step: _not_implemented(step) for step in STEPS}


@dataclass(frozen=True)
class BuiltArtifacts:
    catalog: list[CommercialInformation]
    products: list[Product]
    chunks: list[Chunk]
    graph: nx.MultiDiGraph
    join_report: JoinReport
    document_names: dict[str, str]  # document_id -> PDF filename (for citations in the UI)


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def build_in_memory(settings: Settings | None = None) -> BuiltArtifacts:
    """discover → parse → extract → enrich → chunk → kg, entirely in memory from data/raw."""
    settings = settings or get_settings()
    registry = load_spec_registry(_resolve(settings.paths.spec_registry))
    records = discover_documents(_resolve(settings.paths.pdf_dir))
    catalog_records = [r for r in records if r.doc_type is DocumentType.CATALOG]
    if len(catalog_records) != 1:
        raise ValueError(f"expected exactly one catalog PDF, found {len(catalog_records)}")
    catalog = parse_catalog(catalog_records[0])
    docs = [parse_document(r) for r in records if r.doc_type is DocumentType.DATASHEET]
    products, report = join_catalog([extract_product(d, registry) for d in docs], catalog)
    chunks = [c for d in docs for c in chunk_document(d)]
    names = {r.document_id: r.filename for r in records}
    return BuiltArtifacts(catalog, products, chunks, build_graph(products, chunks), report, names)


def build_agent(
    settings: Settings | None = None, artifacts: BuiltArtifacts | None = None
) -> AdvisorAgent:
    """Composition root: real AdvisorAgent with the configured LLM chain (template always last)."""
    settings = settings or get_settings()
    artifacts = artifacts or build_in_memory(settings)
    return AdvisorAgent(
        graph=artifacts.graph,
        products=artifacts.products,
        commercial=CommercialEngine(artifacts.catalog),
        retriever=BM25Retriever(artifacts.chunks),
        llm_chain=build_llm_chain(settings),
        registry=load_spec_registry(_resolve(settings.paths.spec_registry)),
    )


def run(steps: tuple[str, ...] = STEPS, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    for step in steps:
        log.info("pipeline step", extra={"step": step})
        RUNNERS[step](settings)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", nargs="*", choices=STEPS, default=list(STEPS))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    run(tuple(args.steps))


if __name__ == "__main__":
    main()
