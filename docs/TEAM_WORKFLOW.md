# Team Workflow

## Ramas
- `main`: demo estable. Solo merge desde `develop` con `make check` verde.
- `develop`: integración.
- `feat/<tema>`, `fix/...`, `contract/...` → PR a `develop`.

## Commits
Conventional Commits con descripción en español en imperativo: `feat(compatibility): agrega regla R-CAT`, `fix(parsing): ...`, `chore`, `docs`, `test`, `build`.

## Organización
- **Sin dueños por módulo:** cualquiera de los 3 puede editar cualquier archivo del repo.
- **Avisar antes de tocar** un archivo que otra persona esté editando (chat del equipo), para evitar conflictos.
- **Tareas sin responsable fijo:** quien empieza una tarea del backlog (B-xx) la anuncia en el chat.

## Reglas que se mantienen
- Contratos en `src/advisor/models/` y firmas públicas de MODULE_CONTRACTS.md: solo con acuerdo del equipo, vía PR con etiqueta `contract-change`.
- Reglas duras de CLAUDE.md: catálogo = verdad; el LLM no decide compatibilidad; crítica ⇒ INCOMPATIBLE; solo ACTIVE recomendado; sin secretos.
- `make check` antes de cada PR; `scripts/smoke_tests.md` antes de merge a `main`.
