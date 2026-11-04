# Module Contracts

Firmas estables (stubs con `NotImplementedError` hasta que se implementen). Cambiar una firma ⇒ PR con etiqueta `contract-change`.

| Módulo | Contrato |
|---|---|
| ingestion | `discover_documents(root: Path) -> list[DocumentRecord]` |
| parsing | `parse_document(record: DocumentRecord) -> ParsedDocument`; `parse_catalog(record) -> list[CommercialInformation]` |
| extraction | `extract_product(doc: ParsedDocument, registry: SpecRegistry) -> Product` |
| enrichment | `join_catalog(products, commercial) -> tuple[list[Product], JoinReport]` |
| chunking | `chunk_document(doc: ParsedDocument, *, max_chars, overlap) -> list[Chunk]` |
| kg (build) | `build_graph(products, chunks) -> nx.MultiDiGraph`; `save(g, path)`; `load(path)` |
| kg (query) | `resolve_part(g, text) -> list[PartMatch]`; `candidate_neighbors(g, part_number) -> list[CandidateProduct]` |
| retrieval | `Retriever.search(query, *, top_k, filters) -> list[ChunkHit]` |
| commercial | `CommercialEngine.get(part_number) -> CommercialInformation`; `.availability(part_number) -> tuple[status, price, stock]` |
| compatibility | `derive_requirements(original, query) -> list[TechnicalRequirement]`; `evaluate(original, candidate, reqs) -> CompatibilityResult` |
| recommendation | `rank(results, products) -> RankedOutput(recommendations, risky_options, unverified_options)` |
| llm | `LLMClient.complete_json(prompt, schema) -> BaseModel`; `.generate(prompt) -> str` (DatabricksFMAPI, Ollama, Template) |
| agent | `AdvisorAgent.answer(query: CustomerQuery) -> RecommendationResponse` (memoria en `query.context`; herramientas en `agent/knowledge.py`, plan en `agent/planner.py`, ADR-014) |
| repository | `ArtifactRepository` (LocalParquet, DatabricksSQL): `load_products`, `load_graph`, `load_matrix`, `save_*` |
| models | todos los Pydantic |
