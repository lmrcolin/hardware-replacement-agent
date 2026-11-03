# TODO

Sin responsable fijo: cualquiera toma cualquier tarea y la anuncia en el chat del equipo.
Cada tarea cierra su test `xfail` en `tests/unit/test_stubs.py` (quitar el marcador al implementar).
Detalle y dependencias en [DEVELOPMENT_BACKLOG.md](DEVELOPMENT_BACKLOG.md).

## Frente: datos (skills: databricks-data-pipeline, pdf-spec-extraction, knowledge-graph)

Primer comando:
```bash
databricks auth login --host https://<workspace>.cloud.databricks.com --profile emerson
scripts/bootstrap_databricks.sh --profile emerson --dry-run   # revisar, luego sin --dry-run
# Ejecutar notebooks/00_bootstrap.sql, 01_ingest.py, 02_parse.sql en el workspace
```
- [ ] B-01 Notebook 00 + subir 33 PDFs al volumen
- [ ] B-02 Notebooks 01–02 (`ai_parse_document`); anotar resultado en FEATURE_MATRIX.md
- [ ] B-03 `parse_catalog` → 32 filas (21/6/2/3)
- [ ] B-04 `discover_documents` + `parse_document`
- [ ] B-05 Completar `config/spec_registry.yaml` con claves reales
- [ ] B-06 `extract_product` con Evidence
- [ ] B-07 `join_catalog` + JoinReport
- [ ] B-08 `chunk_document`
- [ ] B-09 `build_graph` / `save` / `load`
- [ ] B-10 Notebooks 03–07 + `make pipeline-local`

## Frente: inteligencia (skills: compatibility-matching, agentic-rag, knowledge-graph)

Primer comando:
```bash
make setup
uv run pytest tests/unit/test_stubs.py -k "compat or category or missing or rank" -rxX
```
- [ ] B-15 `compat_rules.yaml` + `evaluate` (empezar por R-CAT, R-MUST-PROTO, R-MISSING)
- [ ] B-16 `derive_requirements`
- [ ] B-17 `rank`
- [ ] B-14 `CommercialEngine`
- [ ] B-11 `resolve_part` · B-12 `candidate_neighbors`
- [ ] B-13 BM25 + FAISS
- [ ] B-18 LLM clients (Template primero) · B-19 `AdvisorAgent.answer` + VERIFY

## Frente: producto (skills: streamlit-product, integration-check)

Primer comando:
```bash
make setup
uv run streamlit run app/streamlit_app.py   # MockAdvisorAgent
```
- [ ] B-20 `LocalParquetRepository` (luego `DatabricksSQLRepository`)
- [ ] B-21 UI final sobre `RecommendationResponse`
- [ ] B-22 `gold_set.yaml` con casos reales verificados + scoring en `run_eval.py`
- [ ] B-23 `build_tco_excel.py`
- [ ] B-24 Probar `scripts/reproduce_from_scratch.sh` en clon limpio
- [ ] B-25 DEMO_PLAN + ensayo; `/integration-check` antes de merge a `main`
