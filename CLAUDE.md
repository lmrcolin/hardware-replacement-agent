# CLAUDE.md — Emerson Replacement Advisor

Asistente agéntico (Datathon MICAI 2026, Reto 1 Emerson) que, ante una pieza DISCONTINUED/EOL/NRND, recomienda
sustitutos ACTIVE del catálogo con compatibilidad, precio, stock y evidencia. Equipo de 3, hackathon de 24 h.

@docs/ARCHITECTURE.md
@docs/MODULE_CONTRACTS.md
@docs/COMPATIBILITY_ENGINE_DESIGN.md
@docs/TEAM_WORKFLOW.md

## 10 reglas duras

1. **El catálogo es la verdad** para estado, precio y stock. Los datasheets nunca lo sobrescriben.
2. **El LLM no decide ni inventa.** Solo NLU (JSON validado por Pydantic) y NLG con cifras ya presentes en la respuesta estructurada.
3. **Regla crítica fallida ⇒ INCOMPATIBLE.** Dato faltante ⇒ UNKNOWN, nunca COMPATIBLE.
4. **Solo ACTIVE se recomienda.** NRND va a `risky_options`; DISCONTINUED/EOL nunca son sustitutos.
5. **0 USD en APIs.** Llama vía Databricks FMAPI, Ollama local o plantillas. Sin claves de pago.
6. **Contratos** (`src/advisor/models/`, firmas en MODULE_CONTRACTS) solo cambian con acuerdo del equipo, vía PR con etiqueta `contract-change`.
7. **Sin dueños por módulo:** cualquiera puede editar cualquier archivo; avisar en el chat del equipo antes de tocar un archivo que otro esté editando.
8. **Dependencias sin ciclos** y en la dirección de capas (import-linter + `tests/contracts/test_imports.py`).
9. **Databricks Free Edition:** consultas acotadas (`LIMIT`, filtros) e idempotentes (`IF NOT EXISTS`, `MERGE`, `CREATE OR REPLACE`); respetar la cuota diaria.
10. **Sin secretos** en código, notebooks, commits ni chat. Autenticación con `databricks auth login --profile emerson`.

No inventar specs, estados ni precios. Los fixtures son sintéticos y están marcados como tales.

## Flujo Git

`feat/<dev>-<tema>` → PR a `develop` → `main` solo con `make check` verde. Conventional Commits
(`feat(compatibility): ...`). Sin líneas de atribución a herramientas de IA en commits ni PRs.

## Comandos

| Comando | Qué hace |
|---|---|
| `make setup` | `.venv` (Python 3.12, uv) + dependencias + hooks pre-commit |
| `make check` | ruff + import-linter + pytest (contratos verdes, stubs xfail) |
| `make test` / `make test-contracts` | pytest completo / solo contratos |
| `make pipeline-local` | construye `artifacts/` desde `datos/pdfs/` |
| `make eval` | evaluación sobre `evaluation/gold_set.yaml` |
| `make app` | Streamlit (MockAdvisorAgent hasta que exista el agente) |
| `make excel` | Excel TCO en `cost/` |

## Mapa rápido

`datos/pdfs/` (no modificar) · `src/advisor/*` (módulos por capa) · `config/*.yaml` (settings, spec_registry, compat_rules) ·
`notebooks/00–07` (Databricks) · `scripts/` · `evaluation/` · `tests/{contracts,unit,data,integration,fixtures}` · `app/` · `cost/` · `artifacts/` (generado).

Skills en `.claude/skills/`: databricks-data-pipeline, pdf-spec-extraction, knowledge-graph, compatibility-matching,
agentic-rag, streamlit-product, integration-check.
