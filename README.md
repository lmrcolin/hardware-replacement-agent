# Hardware Replacement Agent — Emerson Replacement Advisor

Asistente agéntico (Datathon MICAI 2026, Reto 1 Emerson) que, dado un componente **DISCONTINUED / EOL / NRND** (por
part number o por requisitos), propone sustitutos **vendibles (ACTIVE)** del catálogo con nivel de compatibilidad,
precio, stock, condiciones de instalación y **citas a datasheet y página**.

> Caso oficial — *"Necesito una tarjeta de red 100 Gigabit Ethernet con soporte RDMA y offload de IPsec. Usábamos la
> Intel E810 pero ya no la encuentro"* → E810-CQDA2 está DISCONTINUED; 1. **MCX75310AAS-NEAT** (1,250.00 USD, 120 u.),
> 2. **BCM57508** (890.00 USD, 75 u.), ambos *compatibles con condiciones* (más velocidad: ópticas/switch o breakout).

## Por qué importa (obsoleto → sustituto → venta)

Cuando un cliente pide una pieza que ya no se vende, la venta se pierde salvo que alguien encuentre a tiempo un
sustituto activo, compatible y en stock; hoy eso depende de expertos. El catálogo tiene 11 piezas no vendibles
(6 DISCONTINUED, 2 EOL, 3 NRND) frente a 21 ACTIVE con 12,814,325.00 USD de inventario a precio de catálogo
(precio × stock), y la meta es mover ~4 M USD/año. El asistente convierte cada consulta por una pieza obsoleta
en una oferta vendible en segundos: sustituto ACTIVE, precio, unidades disponibles, condiciones de instalación y
evidencia citada; cuando no hay sustituto lo dice y explica qué se descartó y por qué (evita devoluciones por
incompatibilidad). La app muestra por respuesta el inventario y su valor que la recomendación pone a la venta; el
costo de operarlo frente a esa meta está en `cost/emerson_advisor_tco.xlsx`.

## Cómo funciona

```
33 PDFs (data/raw) ─► parsing ─► extracción de specs con cita literal ─► cruce con catálogo (catálogo = verdad)
                                                    │
                     chunks + BM25 ◄────────────────┼────────────► grafo (NetworkX): familia, protocolos,
                                                    │               avisos de migración (MIGRATES_TO)
                                                    ▼
      agente: NLU → memoria → PLAN → herramientas (con guardián) → COMPOSE → NLG → VERIFY
                │                 │            │                                    │
        JSON validado      Llama propone   identificar pieza · buscar sustitutos ·  VERIFY rechaza cifras
        y saneado          el plan; sin    buscar en catálogo · negociar requisitos · no verificadas
                           LLM, reglas     consultar datasheets · comparar · preguntar
                                           (motor de reglas: crítica ⇒ INCOMPATIBLE, falta dato ⇒ UNKNOWN)
```

**Un agente, no un formulario.** Llama decide qué herramientas usar y en qué orden; las herramientas son
deterministas y el guardián corrige cualquier paso inválido (queda visible en "Razonamiento del agente"). Recuerda la
conversación y entiende seguimientos ("¿y la más barata?", "compárala con la BCM57508", "ya no necesito IPsec",
"con 200 me basta"); si no hay sustituto, **negocia**: dice qué se podría vender quitando un requisito (p. ej. A100 →
H100 si se acepta SXM5); responde **preguntas técnicas** con specs y citas ("¿cuánto consume la H100?"); y cuando
falta información pregunta lo que más reduce las opciones, con botones. Diseño: `docs/AGENT_DESIGN.md` (ADR-014).

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

Los PDFs vienen versionados en `data/raw/`. Si los recibiste con la estructura del enunciado (`datos/pdfs/`),
cópialos a `data/raw/` (lo que usa el job de Databricks) o, solo en local, `ADVISOR_PDF_DIR=datos/pdfs make app`.
`make setup` también funciona desde un ZIP sin `.git` (omite los hooks).

### Todo en Databricks (de cero a demo)

```bash
databricks auth login --host https://<tu-workspace>.cloud.databricks.com   # una vez (perfil por defecto)
databricks bundle deploy -t dev
databricks bundle run run_all -t dev   # 00 → 07: bronze, silver, gold, grafo, matriz, AI Search (~6 min; +~20 la 1.ª vez)
make app-databricks                    # datos en vivo de emerson_hw.gold.* (SQL warehouse) + AI Search + Llama
make eval-databricks                   # la misma evaluación, todo pasando por Databricks
```

Con un perfil con nombre: `--profile <perfil>` en los comandos `databricks` y `PROFILE=<perfil>` en `make`.
Si el workspace tiene más de un SQL warehouse: `ADVISOR_DATABRICKS_WAREHOUSE_ID=<id>`. Si ya existe otro endpoint
de AI Search (Free Edition permite uno): `databricks bundle run run_all -t dev --params ai_search=false`; la app
degrada a BM25 y lo indica.

Cómo comprobar que se usa Databricks: menú **⋮ → Herramientas del agente** muestra el origen real de los datos
(`Databricks en vivo: emerson_hw.gold.* vía SQL warehouse …`), el estado comprobado de AI Search y la cadena de LLM;
cada respuesta indica qué motor aportó la evidencia (`bm25 N, ai_search N`) y quién redactó (`databricks` = Llama).
En Databricks: Query History del warehouse, peticiones del serving endpoint de Llama, métricas del endpoint
`emerson-vs` y `system.billing.usage`.

Búsqueda híbrida con AI Search (requiere `databricks auth login`):
`ADVISOR_RETRIEVAL_BACKEND=hybrid ADVISOR_DATABRICKS_PROFILE=<perfil> make app` · comparar motores:
`uv run python -m evaluation.run_eval --retriever bm25|ai_search|hybrid`.

## Despliegue en Databricks

Requisitos: Databricks CLI autenticada (`databricks auth login`), `uv` en el PATH (el deploy construye el wheel de
`advisor`) y permiso `CREATE CATALOG` en el metastore (en Free Edition, el dueño del workspace lo tiene). El
catálogo es `emerson_hw` (los notebooks instalan el wheel desde `/Volumes/emerson_hw/bronze/libs`).

```bash
databricks auth login --host https://<tu-workspace>.cloud.databricks.com
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
