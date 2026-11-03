# Hardware Replacement Agent — Emerson Replacement Advisor

Asistente agéntico (Datathon MICAI 2026, Reto 1 Emerson) que, dado un componente **DISCONTINUED / EOL / NRND** (por
part number o por requisitos), propone sustitutos **vendibles (ACTIVE)** del catálogo con nivel de compatibilidad,
precio, stock, condiciones de instalación y **citas a datasheet y página**.

> Caso oficial — *"Necesito una tarjeta de red 100 Gigabit Ethernet con soporte RDMA y offload de IPsec. Usábamos la
> Intel E810 pero ya no la encuentro"* → E810-CQDA2 está DISCONTINUED; 1. **MCX75310AAS-NEAT** (1,250.00 USD, 120 u.),
> 2. **BCM57508** (890.00 USD, 75 u.), ambos *compatibles con condiciones* (más velocidad: ópticas/switch o breakout).

## Cómo funciona

```
33 PDFs (data/raw) ─► parsing ─► extracción de specs con cita literal ─► cruce con catálogo (catálogo = verdad)
                                                    │
                     chunks + BM25 ◄────────────────┼────────────► grafo (NetworkX): familia, protocolos,
                                                    │               avisos de migración (MIGRATES_TO)
                                                    ▼
      agente: PARSE → RESOLVE → CLARIFY | STATUS → DISCOVER → VALIDATE → RANK → COMPOSE → VERIFY
                       │                                        │                         │
              LLM solo interpreta                 motor de reglas determinista     LLM solo reformula;
              (JSON validado y saneado)           (YAML; crítica ⇒ INCOMPATIBLE,   VERIFY rechaza cifras
                                                   falta dato ⇒ UNKNOWN)            no verificadas
```

- **Solo ACTIVE** se recomienda; NRND aparece aparte como opción con riesgo; DISCONTINUED/EOL nunca.
- **Ranking:** nivel > requisitos obligatorios cubiertos > puntuación; el stock solo desempata.
- **Búsqueda:** BM25 local (sin red, por defecto) o **híbrida BM25 + AI Search** (índice vectorial Delta Sync en
  Databricks, embeddings `databricks-gte-large-en`, fusión RRF); si AI Search no responde, degrada a BM25.
- **0 USD en APIs:** LLM `template` determinista por defecto; Llama 3.3 (Databricks FMAPI) u Ollama opcionales.

## Requisitos

- [uv](https://docs.astral.sh/uv/) (gestiona Python 3.12) — `pipx install uv` o `sudo pacman -S uv`
- [Databricks CLI](https://docs.databricks.com/dev-tools/cli/install.html) ≥ 0.250 y una cuenta de Databricks Free Edition (solo para la parte Databricks)
- LibreOffice (opcional, para el test que recalcula el Excel)

## Uso local

```bash
make setup            # .venv + dependencias + hooks (alias: make install)
cp .env.example .env  # opcional; por defecto LLM = template
make check            # ruff + mypy + import-linter + tests
make pipeline-local   # artifacts/: products, chunks, grafo, matriz de compatibilidad (≈3 s)
make app              # chat en http://localhost:8501 (sin red)
make eval             # evaluación sobre el golden set → evaluation/report.md
make excel            # cost/emerson_advisor_tco.xlsx (TCO con supuestos editables)
```

Reproducción completa local: `scripts/reproduce_from_scratch.sh --local-only`.

### Todo en Databricks

```bash
databricks bundle deploy -t dev --profile lmrcolin
databricks bundle run run_all -t dev --profile lmrcolin   # 00 → 07: bronze, silver, gold, grafo, matriz, AI Search
make app-databricks PROFILE=lmrcolin    # datos en vivo de emerson_hw.gold.* (SQL warehouse) + AI Search + Llama
make eval-databricks PROFILE=lmrcolin   # la misma evaluación, todo pasando por Databricks
```

La barra lateral de la app muestra **Fuentes en uso** (comprobadas, no solo configuradas): origen de los datos,
estado real de AI Search y cadena de LLM; cada respuesta indica qué motor aportó la evidencia y quién redactó.

Búsqueda híbrida con AI Search (requiere `databricks auth login`):
`ADVISOR_RETRIEVAL_BACKEND=hybrid ADVISOR_DATABRICKS_PROFILE=<perfil> make app` · comparar motores:
`uv run python -m evaluation.run_eval --retriever bm25|ai_search|hybrid`.

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

## Resultados

`make eval` (22 casos verificados contra los PDFs, LLM `template`): resolución, estado, aclaración, hit@1, MRR y nivel
= 1.00; recuperación BM25 Recall@5 = 1.00, MRR = 1.00; **puertas de seguridad = 0** (ninguna recomendación prohibida o no
ACTIVE, ningún precio/stock distinto del catálogo, ninguna cifra no verificada). Detalle y limitaciones en
[evaluation/report.md](evaluation/report.md): el conjunto es pequeño y propio; falta un conjunto ciego
(`evaluation/blind_set.yaml`, `make eval-blind`).

Búsqueda (32 casos, incluidos 10 descriptivos en español sin part number): Recall@5 BM25 0.88 · AI Search 0.95 ·
**híbrida 1.00**; MRR 0.83 · 0.73 · **0.86** ([evaluation/report_hybrid.md](evaluation/report_hybrid.md)).

Costos: [docs/COST_MODEL.md](docs/COST_MODEL.md) — TCO año 1 ≈ 14.4 k USD con supuestos editables (precios de
plataforma POR CONFIRMAR).

## Limitaciones conocidas

- 4 datasheets se contradicen entre prosa y resumen (SN860, IR3555, Agilex 7, BCM57508); se usa el resumen citado
  ([docs/DATA_INVENTORY.md](docs/DATA_INVENTORY.md)).
- `ai_parse_document` leyó mal un part number del catálogo; el catálogo se lee con parser determinista (ADR-012).
- A100 → H100: el datasheet lo llama sucesor, pero los SKU difieren en factor de forma; no se recomienda como directo.
- Candidatos con datos críticos faltantes (UNKNOWN) no se recomiendan: se listan aparte como "posibles, sin datos
  suficientes" (ADR-013).
- Clientes Llama/Ollama implementados; su validación real está en `docs/FEATURE_MATRIX.md`.

## Estructura

```
src/advisor/           lógica por capas (models, parsing, extraction, kg, compatibility, agent, ...)
config/                settings, spec_registry (specs por categoría), compat_rules
app/                   chat Streamlit (components/ = presentación)
evaluation/            golden set, conjunto ciego, métricas, report.md
databricks/notebooks/  notebooks del pipeline · databricks.yml: bundle y job run_all
cost/                  Excel TCO (generado con make excel)
tests/                 contratos, unit, data (PDFs reales), integration (app, pipeline, Excel)
data/raw/              33 PDFs fuente
docs/                  arquitectura, ADRs, contratos, diseño del motor, demo, TODO
```

Guía para colaboradores y para Claude Code: [CLAUDE.md](CLAUDE.md) · Tareas: [docs/TODO.md](docs/TODO.md) · Demo:
[docs/DEMO_PLAN.md](docs/DEMO_PLAN.md).
