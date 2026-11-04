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

El menú ⋮ del chat muestra las **herramientas del agente** (comprobadas, no solo configuradas): origen de los
datos, estado real de AI Search y cadena de LLM; cada respuesta muestra el razonamiento del agente, qué motor aportó
la evidencia y quién redactó. La barra lateral guarda el **historial y las más buscadas** (últimos 7 días, en
`.cache/advisor/searches.jsonl`, ignorado por git; `ADVISOR_SEARCH_LOG` lo cambia).

**Voz.** `make app` instala el extra `voice`: el campo de mensaje tiene micrófono, la transcripción es local con
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) (modelo `small`, ~460 MB la primera vez;
`ADVISOR_WHISPER_MODEL=base` para uno más ligero) con los part numbers del catálogo como vocabulario, y las
respuestas a preguntas dictadas se leen con la voz del navegador (`speechSynthesis`; "Responder con voz" en ⋮ lo
activa siempre). Gratis y sin servicios externos; el audio no sale del equipo.

Búsqueda híbrida con AI Search (requiere `databricks auth login`):
`ADVISOR_RETRIEVAL_BACKEND=hybrid ADVISOR_DATABRICKS_PROFILE=<perfil> make app` · comparar motores:
`uv run python -m evaluation.run_eval --retriever bm25|ai_search|hybrid`.

## Despliegue en Databricks

Requisitos: Databricks CLI autenticada (`databricks auth login`), `uv` en el PATH (el deploy construye el wheel de
`advisor`) y permiso `CREATE CATALOG` en el metastore (o un catálogo existente con `--var catalog=<catalogo>`).

```bash
databricks auth login --host https://<tu-workspace>.cloud.databricks.com --profile <perfil>
databricks bundle validate
databricks bundle deploy -t dev        # construye dist/*.whl con uv y sincroniza el repo
databricks bundle run run_all -t dev   # ~5 min (+~20 min la primera vez que se provisiona AI Search)
```

El job `run_all` corre en serverless (02–07 en el entorno versión 4, Python 3.12) y es idempotente:

| Tarea | Qué hace | Salida |
|---|---|---|
| `00_setup` | catálogo, esquemas, volúmenes; copia los 33 PDFs y el wheel + `config/*.yaml` | `bronze.raw_files`, `bronze.libs` |
| `01_parse` | `ai_parse_document` (no re-parsea si ya hay 33; `force=true` para rehacer) | `bronze.documents_parsed` |
| `02_extract_enrich` | catálogo (capa de texto, ADR-012) + specs + cruce; falla si el cruce no es seguro | `silver.commercial`, `silver.products`, `silver.product_specifications`, `gold.products` |
| `03_chunk_index` | chunks por sección, Change Data Feed | `gold.document_chunks` |
| `04_build_kg` | grafo de conocimiento | `gold.kg_nodes`, `gold.kg_edges` |
| `05_compat_matrix` | piezas no ACTIVE contra su categoría | `gold.compat_matrix` |
| `06_export_artifacts` | mismos archivos que `make pipeline-local` | `/Volumes/<catalog>/gold/artifacts` |
| `07_ai_search` | crea (si falta) o re-sincroniza el endpoint `emerson-vs` y el índice Delta Sync; `ai_search=false` la omite | `gold.document_chunks_index` |

Comprobación (la hace `scripts/reproduce_from_scratch.sh`): `bronze.documents_parsed` 33 · `silver.commercial` 32
(ACTIVE 21 · DISCONTINUED 6 · EOL 2 · NRND 3) · `silver.product_specifications` 272 · `gold.products` 32 ·
`gold.document_chunks` 126 · `gold.compat_matrix` 30 · `gold.kg_nodes` 501 · `gold.kg_edges` 586.
Esquemas en `docs/DATA_MODEL.md`; capacidades probadas en `docs/FEATURE_MATRIX.md`.

Usar Databricks desde local:

- Artefactos del job: `scripts/reproduce_from_scratch.sh --pull-artifacts` (o
  `databricks fs cp -r dbfs:/Volumes/emerson_hw/gold/artifacts ./artifacts`).
- Leer las tablas `gold` directamente: `ADVISOR_REPOSITORY_BACKEND=databricks_sql
  ADVISOR_DATABRICKS_WAREHOUSE_ID=<id> ADVISOR_DATABRICKS_PROFILE=<perfil>` (`DatabricksSQLRepository`).

Notas de Free Edition: importar código o leer binarios del repo por FUSE `/Workspace` falla en serverless (por eso el
wheel va en el volumen `bronze.libs`); solo se permite un endpoint de AI Search; los usuarios necesitan `GRANT` sobre
`emerson_hw` para leer las tablas. Para que cualquiera pueda correr `run_all`, el dueño del índice debe dar
`GRANT ALL PRIVILEGES ON TABLE emerson_hw.gold.document_chunks_index TO account users` y `CAN_MANAGE` al grupo
`users` sobre el endpoint `emerson-vs` (si no, `07_ai_search` falla para quien no es dueño).

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
