# TODO — reparto 50/50 (actualizado 2026-11-03)

Dos frentes que no tocan los mismos archivos. Cada bloque está pensado para pasarse tal cual a Claude Code.

**Reglas para ambos** (ver CLAUDE.md):
- Rama `feat/<tema>` desde `develop` → `git merge --no-ff` a `develop` → `main` solo con `make check` y `make eval` en verde.
- Conventional Commits en español en imperativo (`feat(databricks): agrega notebook 02`). Sin líneas de atribución a IA.
- Nunca inventar specs, estados, precios ni tarifas. El catálogo es la verdad. El LLM no decide compatibilidad.
- Cambios en `src/advisor/models/**` o en firmas de `docs/MODULE_CONTRACTS.md` ⇒ PR `contract-change` acordado por ambos.
- Archivos compartidos (avisar en el chat antes de tocarlos): `scripts/reproduce_from_scratch.sh`, `docs/TODO.md`,
  `CLAUDE.md`, `pyproject.toml`, `uv.lock`.
- Verificación ligera: no crear clones ni entornos nuevos (disco casi lleno); usar el `.venv` existente.

**Interfaz entre frentes (no cambiarla sin acuerdo):** formato de `advisor.repository.LocalParquetRepository`:
`products.parquet`, `chunks.parquet`, `compat_matrix.parquet`, `graph.json` (de `advisor.kg.save`).
Kevin los produce en Databricks; Luis los produce en local y la app los consume.

**Estado de partida:** `main` = `develop` = 201 tests verdes, 0 xfail, `make eval` con puertas en 0.
Implementado: parsing, extracción, cruce catálogo, chunks, grafo, motor de compatibilidad, ranking, agente (LLM template),
BM25, repositorio local, golden set de 22 casos.

---

## Kevin — integración con Databricks Free Edition

**Archivos propios:** `databricks/**`, `databricks.yml`, `scripts/sql/**`, `src/advisor/repository/databricks_sql.py` (nuevo),
`tests/unit/test_repository_databricks.py` (nuevo), `docs/FEATURE_MATRIX.md`, sección "Tablas Delta" de `docs/DATA_MODEL.md`.
**No tocar:** `app/**`, `src/advisor/pipeline.py`, `cost/**`, `evaluation/**`, `README.md`, `docs/DEMO_PLAN.md`.

**Contexto verificado (no repetir):**
- Volumen `/Volumes/emerson_hw/bronze/raw_files`: 33 PDFs idénticos a `data/raw` (nombres y tamaños).
- `emerson_hw.bronze.documents_parsed`: 33 filas (32 datasheet + 1 catalog), 0 nulos, 0 `error_status`.
- **ADR-012:** `ai_parse_document` leyó `H9HCNNNCPMML` como `H9HCNNCPMML` en el catálogo ⇒ el catálogo se lee con
  `advisor.parsing.parse_catalog` (capa de texto), no con `ai_parse_document`.
- Serverless: leer binarios del repo por FUSE `/Workspace` da 403 ⇒ usar la API de Workspace (como `00_setup`).
- Perfil CLI del equipo: `lmrcolin` tiene GRANT sobre `emerson_hw`. Warehouse: `Serverless Starter Warehouse` (2X-Small).

### K1. Cerrar B-02 (5 min) — rama `docs/b02-bronze`
1. En `docs/TODO.md` marca B-02 como hecho (ya verificado arriba).
2. En `docs/FEATURE_MATRIX.md` confirma la fila de `ai_parse_document` (ya tiene datos; solo revisar).
- Aceptación: `make check` verde.

### K2. Probar dependencias en serverless (30 min) — rama `feat/databricks-env`
1. En un notebook nuevo `databricks/notebooks/90_env_check.py` (no entra al job):
   `%pip install pdfplumber pymupdf rapidfuzz networkx rank-bm25 pydantic pyyaml` y luego `dbutils.library.restartPython()`.
2. Importa `advisor` desde el Git folder: `sys.path.append(os.path.abspath(os.path.join(os.getcwd(), "..", "..", "src")))`
   y ejecuta `from advisor.parsing import parse_catalog` y `from advisor.kg import build_graph`.
3. Lee el catálogo desde el volumen: construye un `DocumentRecord` con la ruta `/Volumes/emerson_hw/bronze/raw_files/
   Catalogo_Comercial_Precios_Inventario_2026.pdf` y llama `parse_catalog`; debe dar 32 filas e incluir `H9HCNNNCPMML`.
4. Anota en `FEATURE_MATRIX.md` una fila "pip install en serverless (egress)" con OK/FAIL y notas.
- Si `%pip` FALLA: plan B ⇒ K3 sube `silver.commercial` y `silver.product_specifications` desde local con
  `databricks-sdk` (Statement Execution) o desde parquet en un volumen; documenta la decisión en ADR-012.
- Aceptación: fila en FEATURE_MATRIX con resultado real.

### K3. Notebook 02_extract_enrich (B-10) — rama `feat/databricks-silver`
1. Widget `catalog` (default `emerson_hw`). Igual de fino que 00/01: la lógica viene de `src/advisor`.
2. Pasos en el notebook:
   - `discover_documents(Path("/Volumes/<catalog>/bronze/raw_files"))` → `parse_catalog` (catálogo) y `parse_document`
     + `extract_product` (datasheets, con `load_spec_registry` del repo) → `join_catalog`.
   - **Cruce de seguridad (ADR-012):** lee `bronze.documents_parsed` y comprueba que cada part number del catálogo
     aparezca literalmente en su datasheet parseado; si `JoinReport.unmatched_catalog` o `status_conflicts` no están
     vacíos ⇒ `raise` (el job debe fallar).
   - Escribe con `CREATE OR REPLACE TABLE` (o `MERGE`): `silver.commercial` (1 fila por CommercialInformation),
     `silver.products` (part_number, manufacturer, category, description, document_ids), `silver.product_specifications`
     (part_number, key, value como string JSON, unit, raw_value, evidence JSON) y `gold.products` (producto + comercial).
   - Columnas `is_synthetic` y `_ingested_at` en todas; `COMMENT` en tablas.
3. Asserts finales: 32 filas en `silver.commercial` con estados 21/6/2/3; 32 en `gold.products`.
4. Actualiza la sección "Tablas Delta" de `docs/DATA_MODEL.md` con los esquemas reales.
- Aceptación: correr dos veces seguidas no duplica filas; asserts verdes.

### K4. Notebooks 03_chunk_index y 04_build_kg (B-10) — misma rama o `feat/databricks-gold`
1. 03: `chunk_document` por datasheet → `gold.document_chunks` (chunk_id, document_id, page_start, page_end, section,
   text, part_numbers). `ALTER TABLE ... SET TBLPROPERTIES (delta.enableChangeDataFeed = true)`.
   Assert: 126 chunks (valor local actual); chunk_ids únicos.
2. AI Search (opcional, solo si sobra tiempo): 1 endpoint, índice Delta Sync sobre `gold.document_chunks`; anotar en FEATURE_MATRIX.
3. 04: `build_graph(products, chunks)` → `gold.kg_nodes` (node_id, node_type, label, properties JSON) y `gold.kg_edges`
   (source, target, edge_type, weight, evidence JSON). Asserts: 4 aristas `MIGRATES_TO`
   (E810→MCX75310AAS-NEAT, E810→BCM57508, USB-2627→USB-2633, A100-SXM4-80GB→H100-SXM5).
- Aceptación: asserts verdes y conteos iguales a los locales (`tests/data/test_knowledge_graph.py`).

### K5. Notebook 05_compat_matrix (B-10)
1. Para cada producto no ACTIVE: `derive_requirements(original, ParsedQuery(original_text=pn))` y `evaluate` contra
   cada producto de su categoría → `gold.compat_matrix` (original, candidate, level, coverage, score, conditions JSON,
   missing JSON, rule_results JSON).
2. Asserts que replican `tests/data/test_recommendations.py`: USB-2627 → solo USB-2633 compatible-con-condiciones;
   MPU-6050, WUS4C6464DSP3X5, IR3555MTRPBF y A100-SXM4-80GB sin candidato confirmado.
- Aceptación: asserts verdes.

### K6. Notebook 06_export_artifacts (B-10)
1. `CREATE VOLUME IF NOT EXISTS <catalog>.gold.artifacts`.
2. Lo más simple: `advisor.pipeline.export_artifacts(artifacts_dir=Path("/Volumes/<catalog>/gold/artifacts"))`
   (ya implementado en L1: escribe `products.parquet`, `chunks.parquet`, `compat_matrix.parquet`, `graph.json` y
   `documents.json` = document_id → nombre de PDF, para las citas). Si se escribe a mano: `LocalParquetRepository`
   (`save_products`, `save_chunks`, `save_compat_matrix`) + `advisor.kg.save` + `documents.json`.
3. Documenta en el notebook cómo bajarlos: `databricks fs cp -r dbfs:/Volumes/emerson_hw/gold/artifacts ./artifacts --profile lmrcolin`.
- Aceptación: en local, `LocalParquetRepository(Path("artifacts")).load_products()` devuelve 32 productos tras copiar.

### K7. Job `run_all` completo
1. En `databricks.yml` añade tareas `extract_enrich`, `chunk_index`, `build_kg`, `compat_matrix`, `export_artifacts`
   (02→06) con `depends_on` en cadena tras `parse`; mismos parámetros `catalog`/`force`.
2. `databricks bundle validate` y `databricks bundle deploy -t dev` + `databricks bundle run run_all -t dev`.
3. Si `%pip` es necesario, declara las dependencias como `environment` del job serverless (o `%pip` en cada notebook).
- Aceptación: job verde de punta a punta; captura del run para la demo.

### K8. DatabricksSQLRepository (segunda mitad de B-20) — rama `feat/repository-databricks`
1. Implementa en `src/advisor/repository/databricks_sql.py` (mueve la clase desde `base.py` si hace falta, sin cambiar
   la firma pública) usando `WorkspaceClient(profile=...).statement_execution.execute_statement` sobre `gold.*`.
2. `load_products`, `load_chunks`, `load_compat_matrix` leen tablas gold y validan con los modelos; `load_graph` desde
   `gold.kg_nodes/kg_edges`. Consultas acotadas.
3. Tests unitarios con un `WorkspaceClient` falso (sin red), en `tests/unit/test_repository_databricks.py`.
- Aceptación: `make check` verde (import-linter incluido).

### K9. Llama por FMAPI (FEATURE_MATRIX)
1. `ADVISOR_DATABRICKS_PROFILE=lmrcolin ADVISOR_LLM_PROVIDERS=databricks,template uv run python -m evaluation.run_eval --llm configured --no-report`.
2. Anota en `FEATURE_MATRIX.md`: OK/FAIL, latencia aproximada, si las puertas `gate_*` siguen en 0 y si VERIFY tuvo que
   volver al borrador (warnings "no verificados").
- Aceptación: fila con resultado real. Si hay rate limit, anotarlo; el sistema debe caer a `template` sin error.

### K10. Reproducibilidad (parte Databricks de B-24) — archivo compartido, avisar antes
1. En `scripts/reproduce_from_scratch.sh` completa la sección del bundle: validate → deploy → run → verificar conteos
   (`SELECT count(*)` de `bronze.documents_parsed`=33, `gold.products`=32) con `databricks api post /api/2.0/sql/statements`.
2. Paso final opcional: copiar artefactos del volumen a `./artifacts`.
- Aceptación: el script corre sin intervención salvo `databricks auth login`.

---

## Luis — producto local y entregables

**Archivos propios:** `app/**`, `src/advisor/pipeline.py`, `cost/**`, `scripts/build_tco_excel.py`, `evaluation/**`,
`README.md`, `docs/DEMO_PLAN.md`, `docs/COST_MODEL.md`, `tests/integration/**`, `scripts/smoke_tests.md`.
**No tocar:** `databricks/**`, `databricks.yml`, `scripts/sql/**`, `src/advisor/repository/databricks_sql.py`, `docs/FEATURE_MATRIX.md`.

### L1. ✅ `make pipeline-local` real — rama `feat/pipeline-local`
1. En `src/advisor/pipeline.py` reemplaza los runners `NotImplementedError` por una ejecución real:
   `build_in_memory()` → matriz de compatibilidad (para cada no ACTIVE: `derive_requirements` + `evaluate` contra su
   categoría) → `LocalParquetRepository(artifacts_dir)`: `save_products`, `save_chunks`, `save_compat_matrix` y
   `kg.save(graph, artifacts_dir / "graph.json")`.
2. Mantén `--steps` funcionando (al menos `all`); imprime un resumen (32 productos, 126 chunks, 4 MIGRATES_TO, filas de matriz).
3. Añade `load_artifacts(settings) -> BuiltArtifacts | None` que lea `artifacts/` con el repositorio; `build_agent` usa
   los artefactos si existen y si no construye en memoria.
4. Tests en `tests/integration/test_pipeline_local.py` usando `tmp_path` como `artifacts_dir` (round-trip: lo que se
   guarda se vuelve a cargar idéntico; el agente construido desde artefactos responde el caso E810 igual).
- Aceptación: `make pipeline-local` crea los 4 archivos; `make check` y `make eval` verdes.

### L2. ✅ Excel de costes (B-23) — rama `feat/tco-excel`
1. `scripts/build_tco_excel.py` con `openpyxl`, salida `cost/emerson_advisor_tco.xlsx`, 4 hojas:
   - **Supuestos:** cada tarifa/horas/volumen en una celda con nombre, unidad, fuente y la marca "SUPUESTO EDITABLE"
     (horas por rol del hackathon y de mantenimiento, tarifa por hora, DBU/hora y precio por DBU de un plan de pago,
     consultas/mes, tokens/consulta y precio por token si se usa un LLM de pago, almacenamiento). **No inventar precios
     como si fueran oficiales**: dejar la fuente vacía o "por confirmar" si no hay una real.
   - **Desarrollo:** horas × tarifa por rol (fórmulas que referencian Supuestos).
   - **Mantenimiento_1_anio:** actualización del catálogo, reentrenamiento/re-indexado, soporte, infraestructura.
   - **TCO_anual:** suma con fórmulas + comparación con el objetivo de mover 4 M USD de inventario (valor del inventario
     de piezas no ACTIVE calculado desde el catálogo vía `CommercialInformation.inventory_value_usd`, que es dato real).
2. `make excel` lo genera; añade test que abre el archivo y verifica hojas y que las celdas de totales son fórmulas.
3. Actualiza `docs/COST_MODEL.md` con la tabla de supuestos y cómo cambiarlos.
- Aceptación: el Excel se abre en LibreOffice y recalcula al cambiar un supuesto.

### L3. ✅ UI final (B-21) — rama `feat/ui-final`
1. Diseño de chat (`st.chat_input` / `st.chat_message`) con historial en `st.session_state`; mantener selector Real/Simulado.
2. Ficha de la pieza original: estado (badge por estado), fechas de descontinuación/última compra, stock; precio solo si ACTIVE.
3. Por recomendación: badge de nivel, precio y stock del catálogo, condiciones, **tabla comparativa de specs**
   original vs sustituto (clave, valor original, valor sustituto, unidad, resultado de la regla ✓/✗/?/condición),
   evidencia con nombre de archivo y página.
4. Sección "Opciones con riesgo (NRND)" y explicación del sucesor bloqueado (caso A100).
5. Botón "Escalar a experto" que solo muestra un resumen copiable (sin enviar nada fuera).
6. Barra lateral: ejemplos, proveedor LLM usado, traza de pasos del agente (`AdvisorAgent.last_trace`).
7. Tests con `streamlit.testing.v1.AppTest`: caso oficial (orden MCX75310AAS-NEAT, BCM57508), aclaración, A100.
- Aceptación: `make app` funciona sin red y con LLM template; tests verdes.

### L4. Evaluación ciega y decisión UNKNOWN — rama `feat/eval-blind`
1. Pide a alguien del equipo 10 consultas nuevas sin ver el sistema; añádelas como `GS-B01..B10` con `notes` y fuente.
2. Corre `make eval`; documenta fallos en `evaluation/report.md` (no ajustar el sistema para "pasar" sin justificarlo).
3. Propuesta para candidatos UNKNOWN (hoy al final de `recommendations`): o mantener, o moverlos a una lista nueva
   `unverified_options` (requiere PR `contract-change` y acuerdo con Kevin). Redacta la propuesta en
   `docs/ARCHITECTURE_DECISIONS.md` como ADR-013 "Propuesto".
- Aceptación: `make eval` con puertas en 0 y report actualizado.

### L5. Demo y documentación (B-25) — rama `docs/demo`
1. `docs/DEMO_PLAN.md`: guion minuto a minuto (problema y 4 M USD → caso oficial → USB-2627 → A100 sucesor bloqueado →
   consulta vaga → reproducibilidad con `make check`/`make eval` y job `run_all` de Kevin → Excel TCO), con frases
   exactas y plan B sin red (LLM template + artefactos locales).
2. `README.md` final: qué resuelve, arquitectura en un diagrama, instalación, `make setup/check/eval/app/excel/pipeline-local`,
   despliegue Databricks (sección de Kevin), resultados de evaluación, limitaciones.
3. `scripts/smoke_tests.md`: actualizar comandos y valores esperados reales.
- Aceptación: alguien que no conoce el repo sigue el README y llega a la demo.

### L6. Reproducibilidad local (parte local de B-24) — archivo compartido, avisar antes
1. En `scripts/reproduce_from_scratch.sh` sección local: `make setup` → `make check` → `make pipeline-local` → `make eval`
   → `make excel`; flag `--local-only` ya existe.
- Aceptación: `scripts/reproduce_from_scratch.sh --local-only` termina en verde.

---

## Hecho (historial)

B-02 `bronze.documents_parsed` 33/33 (Kevin) · B-03, B-04 parsing · B-05..B-08 registro, extracción, cruce, chunks · B-09, B-11, B-12 grafo · B-13 BM25 (FAISS pendiente,
opcional) · B-14..B-17 motor de compatibilidad y ranking · B-18, B-19 LLM y agente · B-20 repositorio local (Kevin) ·
B-22 golden set y evaluación. Detalle en `docs/DEVELOPMENT_BACKLOG.md` y en el historial de git.
