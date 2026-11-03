# CLAUDE.md — Emerson Replacement Advisor

Asistente agéntico (Datathon MICAI 2026, Reto 1 Emerson) que, ante una pieza DISCONTINUED/EOL/NRND, recomienda
sustitutos ACTIVE del catálogo con compatibilidad, precio, stock y evidencia. Corre sobre **Databricks Free Edition**
(serverless, Python/SQL) con un catálogo comercial y 32 datasheets (33 PDFs en `data/raw/`). Equipo de 3, hackathon
de 24 h. Responde siempre en español salvo que se pida otro idioma.

@docs/ARCHITECTURE.md
@docs/MODULE_CONTRACTS.md
@docs/COMPATIBILITY_ENGINE_DESIGN.md
@docs/TEAM_WORKFLOW.md

## 10 reglas duras

1. **El catálogo es la verdad** para estado, precio y stock. Los datasheets nunca lo sobrescriben.
2. **El LLM no decide ni inventa.** Solo NLU (JSON validado por Pydantic) y NLG con cifras ya presentes en la respuesta estructurada.
3. **Regla crítica fallida ⇒ INCOMPATIBLE.** Dato faltante ⇒ UNKNOWN, nunca COMPATIBLE. Similitud semántica nunca concede compatibilidad.
4. **Solo ACTIVE se recomienda.** NRND va a `risky_options` con advertencia; DISCONTINUED/EOL nunca son sustitutos.
5. **0 USD en APIs.** Llama vía Databricks FMAPI, Ollama local o plantillas. Sin claves de pago.
6. **Contratos** (`src/advisor/models/`, firmas en MODULE_CONTRACTS) solo cambian con acuerdo del equipo, vía PR con etiqueta `contract-change`.
7. **Sin dueños por módulo:** cualquiera puede editar cualquier archivo; avisar en el chat del equipo antes de tocar un archivo que otro esté editando.
8. **Dependencias sin ciclos** y en la dirección de capas (import-linter + `tests/contracts/test_imports.py`).
9. **Databricks Free Edition:** solo serverless; sin RDDs, `sparkContext`, `.cache()`, `dbfs:/`; 1 endpoint AI Search (solo Delta Sync).
   Consultas acotadas e idempotentes (`IF NOT EXISTS`, `MERGE`, `CREATE OR REPLACE`); respetar la cuota diaria.
10. **Sin secretos**, hosts ni rutas personales en código, notebooks, commits ni chat (`.env` ignorado; usa `.env.example`).

Además: toda cifra técnica citada con documento y página; `is_synthetic` en todas las capas y auditoría
`_source_file`, `_ingested_at`, `_ingest_run_id` en bronze; con `ADVISOR_LLM_PROVIDERS=template` el flujo funciona
de punta a punta; cada cambio de lógica va con su test. No inventar specs, estados ni precios; los fixtures son
sintéticos (`SYN-*`) y están marcados como tales.

## Comandos

| Comando | Qué hace |
|---|---|
| `make setup` (alias `make install`) | `.venv` (Python 3.12, uv) + dependencias + hooks pre-commit |
| `make check` | ruff + mypy + import-linter + pytest |
| `make lint` / `make format` | ruff check + format --check + mypy / autoformato |
| `make test` / `make test-contracts` | pytest completo / solo contratos |
| `make pipeline-local` | construye `artifacts/` (productos, chunks, grafo, matriz) desde `data/raw/` |
| `make eval` / `make eval-blind` | evaluación sobre `evaluation/gold_set.yaml` / conjunto ciego |
| `make app` | chat Streamlit sobre el agente real (artifacts/ o construcción en memoria) |
| `make excel` | Excel TCO en `cost/` |

```bash
databricks auth login                     # una vez; OAuth -> ~/.databrickscfg
databricks bundle validate
databricks bundle deploy -t dev
databricks bundle run run_all -t dev      # 00_setup + 01_parse
```

Comprobación tras `run_all`: `emerson_hw.bronze.documents_parsed` tiene **33 filas**.

## Datos en Databricks

- Catálogo `emerson_hw` (variable de bundle `catalog`), esquemas `bronze`, `silver`, `gold`.
- Volumen fuente: `/Volumes/emerson_hw/bronze/raw_files/` (lo llena `00_setup` desde `data/raw/`).
- Bronze: `documents_parsed` (salida de `ai_parse_document`). Parsear cuesta cuota: `01_parse` no re-parsea
  si ya hay 33 filas (parámetro `force=true` para rehacerlo).
- Silver/Gold y notebooks `02–06`: ver skill `databricks-data-pipeline` y docs/DATA_MODEL.md.

## Mapa rápido

| Ruta | Qué hay |
|---|---|
| `data/raw/` | 33 PDFs fuente (versionados; no modificar) |
| `src/advisor/*` | lógica por capas: models, ingestion, parsing, extraction, enrichment, chunking, kg, retrieval, commercial, compatibility, recommendation, llm, agent, repository |
| `config/*.yaml` | settings, spec_registry, compat_rules |
| `databricks.yml` | bundle con el job `run_all` (00_setup → 01_parse → …) |
| `databricks/notebooks/NN_*.py` | notebooks finos (`# Databricks notebook source`); solo leen/escriben Spark |
| `app/` | Streamlit + `MockAdvisorAgent`; solo consume `RecommendationResponse` |
| `tests/{contracts,unit,data,integration,fixtures}` | pytest; fixtures sintéticos |
| `evaluation/`, `scripts/`, `cost/`, `artifacts/` (generado) | evaluación, utilidades, Excel, artefactos |

## Skills y subagentes

- Skills (`.claude/skills/`): databricks-data-pipeline, pdf-spec-extraction, knowledge-graph, compatibility-matching,
  agentic-rag, streamlit-product, integration-check.
- Subagentes especializados (`.claude/agents/`), disponibles para cualquiera del equipo:
  `datos` (ingesta, parsing, bronze/silver/gold), `ia` (chunks, retrieval, KG, compatibilidad, agente),
  `evaluador` (reglas, golden set, métricas, TCO, revisión en frío), `app` (Streamlit, Databricks App, README, demo).

## Flujo Git

`feat/<tema>` → PR a `develop` → `main` solo con `make check` verde. Conventional Commits con descripción en
español en imperativo (`feat(compatibility): agrega regla R-CAT`). Sin líneas de atribución a herramientas de IA.
