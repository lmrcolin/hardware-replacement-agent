"""Composition root and local pipeline: PDFs → products, chunks, KG, compat matrix → artifacts.

`make pipeline-local` writes artifacts/ in the LocalParquetRepository format (the same files the
Databricks job exports); the app and `build_agent()` load them when present.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import networkx as nx
from databricks.sdk import WorkspaceClient

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
from advisor.repository import DatabricksSQLRepository, LocalParquetRepository
from advisor.retrieval import (
    AISearchRetriever,
    BM25Retriever,
    HybridRetriever,
    RetrievalUnavailableError,
    Retriever,
)

log = logging.getLogger(__name__)

# document_id -> PDF filename for citations; additive to the LocalParquetRepository format.
DOCUMENTS_FILE = "documents.json"
# Provenance of an artifacts/ folder: {"source": "local" | "databricks", "generated_at": ISO, ...}.
MANIFEST_FILE = "manifest.json"
SOURCE_LABEL = {
    "local": "artefactos locales (make pipeline-local)",
    "databricks": "artefactos exportados por el job run_all de Databricks",
}


@dataclass(frozen=True)
class BuiltArtifacts:
    catalog: list[CommercialInformation]
    products: list[Product]
    chunks: list[Chunk]
    graph: nx.MultiDiGraph
    join_report: JoinReport
    document_names: dict[str, str]  # document_id -> PDF filename (for citations in the UI)
    source: str = "construido en memoria desde data/raw"  # shown in the UI ("Fuentes en uso")


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
    write_manifest(root, "local", products=len(built.products), chunks=len(built.chunks))
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


def write_manifest(root: Path, source: str, **counts: int) -> None:
    manifest = {
        "source": source,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        **counts,
    }
    (root / MANIFEST_FILE).write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")


def _display_path(root: Path) -> str:
    """Path shown in the UI: relative to the repo, never the user's home (CLAUDE.md rule 10)."""
    try:
        return root.resolve().relative_to(REPO_ROOT.resolve()).as_posix() + "/"
    except ValueError:
        return f"{root.name}/"


def _source_label(root: Path) -> str:
    path = root / MANIFEST_FILE
    if not path.exists():
        return f"artefactos en {_display_path(root)} (sin manifiesto de origen)"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    label = SOURCE_LABEL.get(manifest.get("source", ""), f"artefactos ({manifest.get('source')})")
    return f"{label}, generados {manifest.get('generated_at', '?')}"


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
        catalog,
        products,
        repo.load_chunks(),
        repo.load_graph(),
        JoinReport(),
        names,
        _source_label(root),
    )


def _workspace(settings: Settings) -> WorkspaceClient:
    return WorkspaceClient(profile=settings.databricks.profile)


def _warehouse_id(settings: Settings, ws: WorkspaceClient) -> str:
    """Configured warehouse, or the only one in the workspace (Free Edition has one)."""
    if settings.databricks.warehouse_id:
        return settings.databricks.warehouse_id
    ids = [w.id for w in ws.warehouses.list() if w.id]
    if len(ids) != 1:
        raise ValueError(f"define ADVISOR_DATABRICKS_WAREHOUSE_ID (hay {len(ids)} warehouses)")
    return ids[0]


def _document_names_from_volume(settings: Settings, ws: WorkspaceClient) -> dict[str, str]:
    path = f"/Volumes/{settings.databricks.catalog}/gold/artifacts/{DOCUMENTS_FILE}"
    try:
        contents = ws.files.download(path).contents
        return dict(json.loads(contents.read())) if contents else {}
    except Exception as exc:  # citations degrade to document ids; data still comes from Delta
        log.warning("document names unavailable", extra={"path": path, "error": str(exc)[:200]})
        return {}


def load_databricks(settings: Settings | None = None) -> BuiltArtifacts:
    """Read gold tables live from Unity Catalog through the SQL warehouse (repository_backend)."""
    settings = settings or get_settings()
    ws = _workspace(settings)
    warehouse = _warehouse_id(settings, ws)
    repo = DatabricksSQLRepository(
        settings.databricks.profile or "", warehouse, settings.databricks.catalog
    )
    products = repo.load_products()
    catalog = [p.commercial for p in products if p.commercial is not None]
    chunks = repo.load_chunks()
    source = (
        f"Databricks en vivo: {settings.databricks.catalog}.gold.* vía SQL warehouse {warehouse} "
        f"({len(products)} productos, {len(chunks)} chunks)"
    )
    names = _document_names_from_volume(settings, ws)
    return BuiltArtifacts(catalog, products, chunks, repo.load_graph(), JoinReport(), names, source)


def load_or_build(settings: Settings | None = None) -> BuiltArtifacts:
    """repository_backend=databricks_sql → live Delta tables; otherwise artifacts/ or in-memory."""
    settings = settings or get_settings()
    if settings.repository_backend == "databricks_sql":
        return load_databricks(settings)
    return load_artifacts(settings) or build_in_memory(settings)


def build_retriever(settings: Settings, chunks: list[Chunk]) -> Retriever:
    """bm25 (default, offline) | ai_search | hybrid (BM25 + AI Search fused with RRF)."""
    bm25 = BM25Retriever(chunks)
    backend = settings.retrieval.backend
    if backend not in ("ai_search", "hybrid"):
        return bm25
    ai_search = AISearchRetriever(
        settings.retrieval.ai_search_endpoint,
        settings.retrieval.ai_search_index,
        settings.databricks.profile,
    )
    return ai_search if backend == "ai_search" else HybridRetriever([bm25, ai_search])


def retrieval_status(retriever: Retriever) -> str:
    """Human-readable search backend; AI Search is probed with a real query (not just config)."""
    if isinstance(retriever, BM25Retriever):
        return "BM25 local (sin red)"
    members = retriever.retrievers if isinstance(retriever, HybridRetriever) else [retriever]
    parts: list[str] = []
    for member in members:
        if isinstance(member, AISearchRetriever):
            try:
                member.search("estado del índice", top_k=1)
                parts.append(f"AI Search ✓ en línea ({member.index})")
            except RetrievalUnavailableError as exc:
                parts.append(f"AI Search ✗ no disponible ({str(exc)[:100]})")
        else:
            parts.append(f"{member.name.upper()} ✓")
    prefix = "híbrida RRF: " if isinstance(retriever, HybridRetriever) else ""
    return prefix + " + ".join(parts)


def evidence_sources(retriever: Retriever) -> str | None:
    """Which search backends contributed to the last query's hits (hybrid only)."""
    sources: dict[str, int] = getattr(retriever, "last_sources", {})
    if not sources:
        return None
    return ", ".join(f"{name} {count}" for name, count in sources.items())


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
        retriever=build_retriever(settings, artifacts.chunks),
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
