# Hardware Replacement Agent

Asistente agéntico que, dado un componente industrial descontinuado (por part number o por requisitos),
propone sustitutos **vendibles** y justifica su compatibilidad con citas a datasheet y página.

- Datos: catálogo comercial con precios e inventario + 32 datasheets (33 PDFs sintéticos en `data/raw/`).
- Plataforma: Databricks Free Edition (Unity Catalog, serverless, `ai_parse_document`, Vector Search).
- Agente: LangGraph con herramientas de catálogo, retrieval y un motor de compatibilidad determinista.

## Requisitos

- [uv](https://docs.astral.sh/uv/) y Python 3.12
- [Databricks CLI](https://docs.databricks.com/dev-tools/cli/install.html) ≥ 0.250
- Una cuenta de Databricks Free Edition

## Uso local

```bash
make install     # crea el entorno
make test        # pruebas
make lint        # ruff + mypy
make app         # interfaz Streamlit
```

Copia `.env.example` a `.env` y ajusta los valores (por defecto: retrieval BM25 local y sin LLM).

## Despliegue en Databricks

```bash
databricks auth login --host https://<tu-workspace>.cloud.databricks.com
databricks bundle validate
databricks bundle deploy -t dev
databricks bundle run run_all -t dev
```

El job `run_all` ejecuta:

1. `00_setup` — crea `emerson_hw` con esquemas `bronze`/`silver`/`gold` y el volumen `bronze.raw_files`,
   y copia los 33 PDFs al volumen.
2. `01_parse` — parsea los PDFs con `ai_parse_document` a `emerson_hw.bronze.documents_parsed`.

Comprobación:

```sql
SELECT count(*) FROM emerson_hw.bronze.documents_parsed;  -- 33
```

Si tu cuenta no permite crear catálogos, usa uno existente:
`databricks bundle deploy -t dev --var catalog=<catalogo>`.

## Estructura

```
src/emerson_agent/     lógica (datos, retrieval, compatibilidad, agente, evaluación)
databricks/notebooks/  notebooks del pipeline
databricks.yml         bundle y job run_all
app/                   interfaz Streamlit
tests/                 pytest
data/raw/              PDFs fuente
```

Guía para colaboradores y para Claude Code: [CLAUDE.md](CLAUDE.md).
