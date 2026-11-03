# Development Backlog

Sin responsable fijo: quien empieza una tarea la anuncia en el chat del equipo.

| ID | Tarea | Dep. |
|---|---|---|
| B-01 | Notebook 00: catálogo/esquema/volumen + subir PDFs | — |
| B-02 | Notebook 01–02: read_files binaryFile + ai_parse_document a Delta | B-01 |
| B-03 | `parse_catalog`: 32 filas, celdas multilínea | — |
| B-04 | `parse_document` local (pdfplumber/pymupdf) | — |
| B-05 | spec_registry completo por categoría | — |
| B-06 | `extract_product` con Evidence | B-04, B-05 |
| B-07 | `join_catalog` + JoinReport | B-03, B-06 |
| B-08 | `chunk_document` con metadata | B-04 |
| B-09 | `build_graph`/`save`/`load` | B-07, B-08 |
| B-10 | Notebooks 03–07 + export de artefactos | B-09 |
| B-11 | `resolve_part` (rapidfuzz) | B-09 |
| B-12 | `candidate_neighbors` (+ PPR opcional) | B-09 |
| B-13 | Retriever BM25 + FAISS | B-08 |
| B-14 | CommercialEngine | B-03 |
| B-15 | compat_rules.yaml con lógica + `evaluate` | — |
| B-16 | `derive_requirements` | B-15 |
| B-17 | `rank` lexicográfico | B-15 |
| B-18 | LLM clients + fallback | — |
| B-19 | AdvisorAgent end-to-end + VERIFY | B-11..B-18 |
| B-20 | Repository LocalParquet + DatabricksSQL | — |
| B-21 | Streamlit final | B-20 |
| B-22 | gold_set real verificado + run_eval | B-19 |
| B-23 | Excel TCO | — |
| B-24 | reproduce_from_scratch.sh probado | B-10 |
| B-25 | DEMO_PLAN + ensayo | B-21 |
