# Development Backlog

| ID | Tarea | Dueño | Dep. |
|---|---|---|---|
| B-01 | Notebook 00: catálogo/esquema/volumen + subir PDFs | Dev1 | — |
| B-02 | Notebook 01–02: read_files binaryFile + ai_parse_document a Delta | Dev1 | B-01 |
| B-03 | `parse_catalog`: 32 filas, celdas multilínea | Dev1 | — |
| B-04 | `parse_document` local (pdfplumber/pymupdf) | Dev1 | — |
| B-05 | spec_registry completo por categoría | Dev1 | — |
| B-06 | `extract_product` con Evidence | Dev1 | B-04, B-05 |
| B-07 | `join_catalog` + JoinReport | Dev1 | B-03, B-06 |
| B-08 | `chunk_document` con metadata | Dev1 | B-04 |
| B-09 | `build_graph`/`save`/`load` | Dev1 | B-07, B-08 |
| B-10 | Notebooks 03–07 + export de artefactos | Dev1 | B-09 |
| B-11 | `resolve_part` (rapidfuzz) | Dev2 | B-09 |
| B-12 | `candidate_neighbors` (+ PPR opcional) | Dev2 | B-09 |
| B-13 | Retriever BM25 + FAISS | Dev2 | B-08 |
| B-14 | CommercialEngine | Dev2 | B-03 |
| B-15 | compat_rules.yaml con lógica + `evaluate` | Dev2 | — |
| B-16 | `derive_requirements` | Dev2 | B-15 |
| B-17 | `rank` lexicográfico | Dev2 | B-15 |
| B-18 | LLM clients + fallback | Dev2 | — |
| B-19 | AdvisorAgent end-to-end + VERIFY | Dev2 | B-11..B-18 |
| B-20 | Repository LocalParquet + DatabricksSQL | Dev3 | — |
| B-21 | Streamlit final | Dev3 | B-20 |
| B-22 | gold_set real verificado + run_eval | Dev3 | B-19 |
| B-23 | Excel TCO | Dev3 | — |
| B-24 | reproduce_from_scratch.sh probado | Dev3 | B-10 |
| B-25 | DEMO_PLAN + ensayo | Dev3 | B-21 |
