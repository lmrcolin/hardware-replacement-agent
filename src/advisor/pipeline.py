"""Composition root and local pipeline: PDFs → products, chunks, KG, compat matrix → artifacts.

`make pipeline-local` writes artifacts/ in the LocalParquetRepository format (the same files the
Databricks job exports); the app and `build_agent()` load them when present.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from advisor.agent import AdvisorAgent
from advisor.chunking import chunk_document
from advisor.commercial import CommercialEngine
from advisor.compatibility import derive_requirements, evaluate
from advisor.config import REPO_ROOT, Settings, get_settings
from advisor.enrichment import join_catalog
from advisor.extraction import extract_product, load_spec_registry
from advisor.ingestion import discover_documents
from advisor.kg import build_graph
from advisor.kg import save as save_graph
from advisor.llm import build_llm_chain
from advisor.models import (
    Chunk,
    CommercialInformation,
    CommercialStatus,
    CompatibilityResult,
    DocumentType,
    EdgeType,
    JoinReport,
    ParsedQuery,
    Product,
)
from advisor.parsing import parse_catalog, parse_document
from advisor.repository import LocalParquetRepository
from advisor.retrieval import BM25Retriever

log = logging.getLogger(__name__)

# document_id -> PDF filename for citations; additive to the LocalParquetRepository format.
DOCUMENTS_FILE = "documents.json"


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


def compat_matrix(
    products: list[Product], settings: Settings | None = None
) -> list[CompatibilityResult]:
    """Every non-ACTIVE product against the rest of its category (requirements from its specs)."""
    settings = settings or get_settings()
    registry = load_spec_registry(_resolve(settings.paths.spec_registry))
    results: list[CompatibilityResult] = []
    for original in products:
        if original.commercial is None or original.commercial.status is CommercialStatus.ACTIVE:
            continue
        query = ParsedQuery(original_text=original.part_number)
        reqs = derive_requirements(original, query, registry=registry)
        results.extend(
            evaluate(original, candidate, reqs, registry=registry)
            for candidate in products
            if candidate.category is original.category
            and candidate.part_number != original.part_number
        )
    return results


def export_artifacts(
    settings: Settings | None = None, artifacts_dir: Path | None = None
) -> dict[str, int]:
    """Build everything and write the LocalParquetRepository files + graph.json + documents.json."""
    settings = settings or get_settings()
    root = artifacts_dir or _resolve(settings.paths.artifacts_dir)
    built = build_in_memory(settings)
    matrix = compat_matrix(built.products, settings)
    repo = LocalParquetRepository(root)
    repo.save_products(built.products)
    repo.save_chunks(built.chunks)
    repo.save_compat_matrix(matrix)
    save_graph(built.graph, root / LocalParquetRepository.GRAPH)
    names = json.dumps(built.document_names, indent=1, sort_keys=True, ensure_ascii=False)
    (root / DOCUMENTS_FILE).write_text(names + "\n", encoding="utf-8")
    edges = built.graph.edges(keys=True)
    summary = {
        "products": len(built.products),
        "chunks": len(built.chunks),
        "graph_nodes": built.graph.number_of_nodes(),
        "graph_edges": built.graph.number_of_edges(),
        "migrates_to": sum(k == EdgeType.MIGRATES_TO.value for _, _, k in edges),
        "compat_matrix_rows": len(matrix),
    }
    log.info("artifacts exported", extra={"root": str(root), **summary})
    return summary


def load_artifacts(
    settings: Settings | None = None, artifacts_dir: Path | None = None
) -> BuiltArtifacts | None:
    """Artifacts from disk (local export or copied from the Databricks volume); None if absent."""
    settings = settings or get_settings()
    root = artifacts_dir or _resolve(settings.paths.artifacts_dir)
    repo = LocalParquetRepository(root)
    if not all((root / name).exists() for name in (repo.PRODUCTS, repo.CHUNKS, repo.GRAPH)):
        return None
    products = repo.load_products()
    catalog = [p.commercial for p in products if p.commercial is not None]
    names_path = root / DOCUMENTS_FILE
    names = json.loads(names_path.read_text(encoding="utf-8")) if names_path.exists() else {}
    return BuiltArtifacts(
        catalog, products, repo.load_chunks(), repo.load_graph(), JoinReport(), names
    )


def load_or_build(settings: Settings | None = None) -> BuiltArtifacts:
    return load_artifacts(settings) or build_in_memory(settings)


def build_agent(
    settings: Settings | None = None, artifacts: BuiltArtifacts | None = None
) -> AdvisorAgent:
    """Composition root: real AdvisorAgent with the configured LLM chain (template always last)."""
    settings = settings or get_settings()
    artifacts = artifacts or load_or_build(settings)
    return AdvisorAgent(
        graph=artifacts.graph,
        products=artifacts.products,
        commercial=CommercialEngine(artifacts.catalog),
        retriever=BM25Retriever(artifacts.chunks),
        llm_chain=build_llm_chain(settings),
        registry=load_spec_registry(_resolve(settings.paths.spec_registry)),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifacts-dir", type=Path, default=None, help="default: settings.paths.artifacts_dir"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    root = args.artifacts_dir or _resolve(get_settings().paths.artifacts_dir)
    summary = export_artifacts(artifacts_dir=root)
    print(f"Artefactos en {root}:")
    for key, value in summary.items():
        print(f"  {key:20} {value}")


if __name__ == "__main__":
    main()
