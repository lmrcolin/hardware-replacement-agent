# Module Contracts

Firmas estables (stubs con `NotImplementedError` hasta que el dueño implemente). Cambiar una firma ⇒ PR con etiqueta `contract-change`.

| Módulo | Contrato | Dueño |
|---|---|---|
| ingestion | `discover_documents(root: Path) -> list[DocumentRecord]` | Dev1 |
| parsing | `parse_document(record: DocumentRecord) -> ParsedDocument`; `parse_catalog(record) -> list[CommercialInformation]` | Dev1 |
| extraction | `extract_product(doc: ParsedDocument, registry: SpecRegistry) -> Product` | Dev1 |
| enrichment | `join_catalog(products, commercial) -> tuple[list[Product], JoinReport]` | Dev1 |
| chunking | `chunk_document(doc: ParsedDocument, *, max_chars, overlap) -> list[Chunk]` | Dev1 |
| kg (build) | `build_graph(products, chunks) -> nx.MultiDiGraph`; `save(g, path)`; `load(path)` | Dev1 |
| kg (query) | `resolve_part(g, text) -> list[PartMatch]`; `candidate_neighbors(g, part_number) -> list[CandidateProduct]` | Dev2 |
| retrieval | `Retriever.search(query, *, top_k, filters) -> list[ChunkHit]` | Dev2 |
| commercial | `CommercialEngine.get(part_number) -> CommercialInformation`; `.availability(part_number) -> tuple[status, price, stock]` | Dev2 |
| compatibility | `derive_requirements(original, query) -> list[TechnicalRequirement]`; `evaluate(original, candidate, reqs) -> CompatibilityResult` | Dev2 |
| recommendation | `rank(results, products) -> RankedOutput(recommendations, risky_options)` | Dev2 |
| llm | `LLMClient.complete_json(prompt, schema) -> BaseModel`; `.generate(prompt) -> str` (DatabricksFMAPI, Ollama, Template) | Dev2 |
| agent | `AdvisorAgent.answer(query: CustomerQuery) -> RecommendationResponse` | Dev2 |
| repository | `ArtifactRepository` (LocalParquet, DatabricksSQL): `load_products`, `load_graph`, `load_matrix`, `save_*` | Dev3 |
| models | todos los Pydantic | Dev3 |
