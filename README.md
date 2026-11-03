# Hardware Replacement Agent — Emerson Replacement Advisor

Asistente agéntico que, dado un componente descontinuado (por part number o por requisitos), propone sustitutos
**vendibles** (ACTIVE) del catálogo y justifica su compatibilidad con citas a datasheet y página.

- Datos: catálogo comercial con precios e inventario + 32 datasheets (33 PDFs en `data/raw/`).
- Plataforma: Databricks Free Edition (Unity Catalog, serverless, `ai_parse_document`, AI Search).
- Agente controlado con herramientas de catálogo, grafo de conocimiento, retrieval y un motor de compatibilidad
  determinista. El LLM solo interpreta la consulta y redacta con cifras verificadas.

## Requisitos

- [uv](https://docs.astral.sh/uv/) (gestiona Python 3.12) — `pipx install uv` o `sudo pacman -S uv`
- [Databricks CLI](https://docs.databricks.com/dev-tools/cli/install.html) ≥ 0.250
- Una cuenta de Databricks Free Edition

## Uso local

```bash
make setup       # crea el entorno + hooks (alias: make install)
cp .env.example .env
make check       # lint + mypy + import-linter + tests
make app         # interfaz Streamlit (agente simulado hasta que exista el real)
```

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

Los notebooks `02–06` (extracción, chunks, grafo, matriz de compatibilidad, export) están como esqueletos y se
añadirán al job a medida que se implementen.

Comprobación:

```sql
SELECT count(*) FROM emerson_hw.bronze.documents_parsed;  -- 33
```

Si tu cuenta no permite crear catálogos, usa uno existente:
`databricks bundle deploy -t dev --var catalog=<catalogo>`.

Reproducción completa desde un clon limpio: `scripts/reproduce_from_scratch.sh`.

## Estructura

```
src/advisor/           lógica por capas (models, parsing, kg, compatibility, agent, ...)
config/                settings, spec_registry, compat_rules
databricks/notebooks/  notebooks del pipeline
databricks.yml         bundle y job run_all
app/                   interfaz Streamlit
evaluation/            golden set y evaluación
tests/                 pytest (contratos, unit, data, integration, fixtures)
data/raw/              PDFs fuente
docs/                  arquitectura, contratos, backlog, roadmap
```

Guía para colaboradores y para Claude Code: [CLAUDE.md](CLAUDE.md).
