---
name: databricks-data-pipeline
description: Builds and reviews Databricks Free Edition notebooks, SQL, Unity Catalog objects and Delta tables (bronze/silver/gold, kg, compat matrix). Use when touching databricks.yml, databricks/notebooks/, scripts/sql/ or repository.DatabricksSQL.
---

# Databricks data pipeline (Free Edition)

## Alcance
`databricks.yml` (bundle, job `run_all`), `databricks/notebooks/00–06`, `scripts/sql/`, `scripts/reproduce_from_scratch.sh`, `src/advisor/repository/databricks_sql.py`.

## Plataforma (verifica en docs/FEATURE_MATRIX.md antes de usar algo)
- Solo serverless; cuota diaria que apaga el cómputo; 1 SQL warehouse 2X-Small.
- Python y SQL; sin Scala/R, sin RDD/`sparkContext`, sin `cache()`, sin `dbfs:/` root → usar `/Volumes/emerson_hw/bronze/raw_files/`.
- 1 endpoint AI Search (1 unidad, sin Direct Vector Access → índice Delta Sync con Change Data Feed).
- ≤3 Apps (se paran a las 24 h). Egress restringido: no descargar modelos HF desde serverless.
- LLM: `databricks-meta-llama-3-3-70b-instruct` vía `ai_query`; Claude/GPT tienen rate limit 0.

## Convenciones
- Objetos: `emerson_hw.<capa>.<tabla>` (`bronze.documents_parsed`, `silver.products`, `silver.product_specifications`, `silver.commercial`, `gold.products`, `gold.document_chunks`, `gold.kg_nodes`, `gold.kg_edges`, `gold.compat_matrix`). El catálogo es la variable `catalog` del bundle.
- Bronze lleva `_source_file`, `_ingested_at`, `_ingest_run_id`, `is_synthetic` (como `01_parse.py`).
- Parsear cuesta cuota: `01_parse` no re-parsea si ya hay 33 filas (`force=true` para rehacer).
- Idempotencia: `CREATE ... IF NOT EXISTS`, `CREATE OR REPLACE TABLE`, `MERGE`. Re-ejecutar no duplica.
- Consultas acotadas: `LIMIT` en exploración, filtros por `path`/`part_number`, nunca `SELECT *` sobre binarios sin límite.
- Notebooks finos: la lógica reutilizable vive en `src/advisor/`; el notebook hace I/O y llama a contratos.
- Notebooks como `.py` (`# Databricks notebook source`, `# COMMAND ----------`), parámetros por widget (`catalog`, `force`) que el job pasa con el mismo nombre.
- Despliegue: `databricks bundle validate && databricks bundle deploy -t dev && databricks bundle run run_all -t dev`.
- Autenticación: `databricks auth login` (OAuth → `~/.databrickscfg`); con varios perfiles, `--profile` o `DATABRICKS_CONFIG_PROFILE`.

## Contratos
Las columnas Delta = campos de los modelos de `advisor.models` (DATA_MODEL.md). `ai_parse_document` produce `ParsedDocument`.

## Pruebas
- Ejecutar el notebook de arriba abajo dos veces: mismo conteo de filas.
- `SELECT count(*) FROM emerson_hw.bronze.documents_parsed` → 33; catálogo → 32 filas.
- Registrar resultado de cada capacidad en FEATURE_MATRIX.md.

## Prohibido
Tokens en notebooks; clusters/GPU/online tables; `overwrite` sin filtro sobre tablas compartidas; asumir que lo que corre en Spark local corre en serverless; modificar los PDFs originales.
