# Team Workflow

## Ramas
- `main`: demo estable. Solo merge desde `develop` con `make check` verde.
- `develop`: integración.
- `feat/<dev>-<tema>`, `fix/...`, `contract/...` → PR a `develop`.

## Commits
Conventional Commits: `feat(compatibility): ...`, `fix(parsing): ...`, `chore`, `docs`, `test`, `build`.

## Dueños (ver `.github/CODEOWNERS`)
- **Dev1 — datos:** ingestion, parsing, extraction, enrichment, chunking, kg/build, notebooks, spec_registry.
- **Dev2 — inteligencia:** kg/query, retrieval, commercial, compatibility, recommendation, llm, agent, compat_rules.
- **Dev3 — producto:** models, app, repository, evaluation, fixtures, scripts, cost, CLAUDE.md.

## Reglas
- Cambios en `src/advisor/models/` ⇒ PR `contract-change` aprobado por los 3.
- No tocar módulos ajenos sin avisar al dueño.
- `make check` antes de cada PR; `scripts/smoke_tests.md` antes de merge a `main`.
