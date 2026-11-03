# CLAUDE.md

Asistente agéntico que encuentra y justifica reemplazos para hardware industrial descontinuado.
Corre sobre **Databricks Free Edition** (serverless, Python/SQL) con un catálogo comercial y 32 datasheets
sintéticos (33 PDFs en `data/raw/`). Responde siempre en español salvo que se pida otro idioma.

## Estructura

| Ruta | Qué hay |
|---|---|
| `src/emerson_agent/` | lógica pura y testeable: `data/`, `domain/`, `retrieval/`, `compatibility/`, `agent/`, `evaluation/`, `config.py` |
| `databricks/notebooks/NN_*.py` | notebooks finos (formato `# Databricks notebook source`); solo leen/escriben Spark |
| `databricks.yml` | bundle con el job `run_all` (00_setup → 01_parse → …) |
| `app/streamlit_app.py` | interfaz; solo llama al agente y lee tablas |
| `tests/unit`, `tests/integration` | pytest; marcadores `integration`, `spark`, `safety` |
| `data/raw/` | 33 PDFs fuente (versionados) |
| `.claude/skills/` | skills del proyecto · `.claude/agents/` subagentes del equipo |

## Comandos

```bash
make install        # uv sync (Python 3.12)
make test           # pytest
make lint           # ruff check + ruff format --check + mypy (strict)
make format         # autoformato
make app            # Streamlit local

databricks auth login                     # una vez; OAuth -> ~/.databrickscfg
databricks bundle validate
databricks bundle deploy -t dev
databricks bundle run run_all -t dev      # setup + parsing bronze
```

Comprobación tras `run_all`: `emerson_hw.bronze.documents_parsed` tiene **33 filas**.

## Datos en Databricks

- Catálogo `emerson_hw` (variable de bundle `catalog`), esquemas `bronze`, `silver`, `gold`.
- Volumen fuente: `/Volumes/emerson_hw/bronze/raw_files/`.
- Bronze: `documents_parsed` (salida de `ai_parse_document`). Parsear cuesta cuota: 01_parse no re-parsea
  si ya hay 33 filas (parámetro `force=true` para rehacerlo).
- Silver/Gold: ver subagente `datos` y skill `databricks-engineering`.

## Reglas que no se negocian

- Free Edition: solo serverless; sin RDDs, `sparkContext`, `.cache()`, `dbfs:/`; 1 endpoint de Vector Search
  (solo Delta Sync). Verifica antes de asumir que algo existe.
- Escrituras idempotentes (`MERGE`, `CREATE OR REPLACE`); `is_synthetic` en todas las capas; auditoría
  `_source_file`, `_ingested_at`, `_ingest_run_id` en bronze.
- La compatibilidad la decide el motor determinista (`compatibility/`), nunca el LLM ni la similitud semántica.
  Veredictos: CONFIRMED / CONDITIONAL / UNKNOWN / INCOMPATIBLE.
- Precio, stock y status siempre desde la herramienta de catálogo. Nunca recomendar como principal algo
  DISCONTINUED, EOL o sin stock; NRND solo con advertencia.
- Toda cifra técnica citada con documento y página.
- Con `EMERSON_LLM_PROVIDER=none` el flujo funciona de punta a punta.
- Sin secretos, hosts ni rutas personales en el repo (`.env` está ignorado; usa `.env.example`).
- Cada cambio de lógica va con su test; `make test` y `make lint` en verde antes de un PR.

## Equipo (subagentes en `.claude/agents/`)

- `datos` — ingesta, parsing, bronze/silver/gold de catálogo y specs.
- `ia` — chunks, retrieval (BM25 / Vector Search), motor de compatibilidad, grafo LangGraph.
- `evaluador` — reglas de compatibilidad, golden set, métricas, TCO; revisión en frío antes del PR.
- `app` — Streamlit, Databricks App, README y demo.

## Git

Ramas por tarea desde `main`; PR a `main`. Mensajes de commit en español, en imperativo.
