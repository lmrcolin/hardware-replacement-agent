---
name: databricks-data-pipeline
description: Builds and reviews Databricks Free Edition notebooks, SQL, Unity Catalog objects and Delta tables (bronze/silver/gold, kg, compat matrix). Use when touching notebooks/, scripts/sql/, scripts/bootstrap_databricks.sh or repository.DatabricksSQL.
---

# Databricks data pipeline (Free Edition)

## Alcance
Notebooks `notebooks/00–07`, `scripts/sql/`, `scripts/bootstrap_databricks.sh`, `scripts/reproduce_from_scratch.sh`, `src/advisor/repository/databricks_sql.py`.

## Plataforma (verifica en docs/FEATURE_MATRIX.md antes de usar algo)
- Solo serverless; cuota diaria que apaga el cómputo; 1 SQL warehouse 2X-Small.
- Python y SQL; sin Scala/R, sin RDD/`sparkContext`, sin `cache()`, sin `dbfs:/` root → usar `/Volumes/datathon/emerson/raw/pdfs`.
- 1 endpoint AI Search (1 unidad, sin Direct Vector Access → índice Delta Sync con Change Data Feed).
- ≤3 Apps (se paran a las 24 h). Egress restringido: no descargar modelos HF desde serverless.
- LLM: `databricks-meta-llama-3-3-70b-instruct` vía `ai_query`; Claude/GPT tienen rate limit 0.

## Convenciones
- Objetos: `datathon.emerson.<capa>_<tabla>` (`bronze_documents`, `silver_products`, `gold_chunks`, `kg_nodes`, `kg_edges`, `compat_matrix`).
- Idempotencia: `CREATE ... IF NOT EXISTS`, `CREATE OR REPLACE TABLE`, `MERGE`. Re-ejecutar no duplica.
- Consultas acotadas: `LIMIT` en exploración, filtros por `path`/`part_number`, nunca `SELECT *` sobre binarios sin límite.
- Notebooks finos: la lógica reutilizable vive en `src/advisor/`; el notebook hace I/O y llama a contratos.
- Notebooks como `.py` (`# Databricks notebook source`, `# COMMAND ----------`) o `.sql`.
- Autenticación: `databricks auth login --profile emerson`; CLI siempre con `--profile`.

## Contratos
Las columnas Delta = campos de los modelos de `advisor.models` (DATA_MODEL.md). `ai_parse_document` produce `ParsedDocument`.

## Pruebas
- Ejecutar el notebook de arriba abajo dos veces: mismo conteo de filas.
- `SELECT count(*)` esperado: 33 documentos, 32 filas de catálogo.
- Registrar resultado de cada capacidad en FEATURE_MATRIX.md.

## Prohibido
Tokens en notebooks; clusters/GPU/online tables; `overwrite` sin filtro sobre tablas compartidas; asumir que lo que corre en Spark local corre en serverless; modificar los PDFs originales.
